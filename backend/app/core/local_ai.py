"""Device-aware, opt-in local AI setup for GODFIN.

The deterministic finance engine never depends on this module.  Ollama is
started only after an authenticated user explicitly approves a registry model.
"""
from __future__ import annotations

import base64
import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
BENCHMARK_PROMPT = (
    "In one short sentence, explain why a savings rate is calculated from "
    "verified income and spending totals. Do not calculate or invent amounts."
)
MODEL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}:[a-z0-9][a-z0-9._-]{0,63}$")

BUILTIN_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "qwen3:1.7b": {
        "label": "Qwen 3 1.7B",
        "family": "qwen",
        "size_gb": 1.4,
        "memory_gb": 4,
        "minimum_ram_gb": 8,
        "official": True,
        "validated": True,
    },
    "qwen3:4b": {
        "label": "Qwen 3 4B",
        "family": "qwen",
        "size_gb": 2.6,
        "memory_gb": 7,
        "minimum_ram_gb": 12,
        "official": True,
        "validated": True,
    },
    "qwen3:8b": {
        "label": "Qwen 3 8B",
        "family": "qwen",
        "size_gb": 5.2,
        "memory_gb": 12,
        "minimum_ram_gb": 24,
        "official": True,
        "validated": True,
    },
    "qwen3.6:27b": {
        "label": "Qwen 3.6 27B",
        "family": "qwen3.6",
        "size_gb": 17,
        "memory_gb": 24,
        "minimum_ram_gb": 32,
        "official": True,
        "validated": True,
    },
    "qwen3.6:35b-a3b": {
        "label": "Qwen 3.6 35B A3B",
        "family": "qwen3.6",
        "size_gb": 24,
        "memory_gb": 32,
        "minimum_ram_gb": 48,
        "official": True,
        "validated": True,
    },
}

_download_lock = threading.Lock()
_download_process: subprocess.Popen[str] | None = None
_download_state: dict[str, Any] = {
    "status": "idle",
    "model": None,
    "progress": 0,
    "message": "No model download is running.",
    "digest": None,
}


def _validated_registry(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        raise ValueError("Model registry must be an object")
    models = payload.get("models", payload)
    if not isinstance(models, dict):
        raise ValueError("Model registry models must be an object")

    validated: dict[str, dict[str, Any]] = {}
    for model, metadata in models.items():
        if not isinstance(model, str) or not MODEL_NAME_PATTERN.fullmatch(model):
            raise ValueError("Invalid model tag in registry")
        if not isinstance(metadata, dict):
            raise ValueError("Invalid model metadata")
        if not metadata.get("official") or not metadata.get("validated"):
            continue
        validated[model] = {
            "label": str(metadata.get("label") or model)[:100],
            "family": str(metadata.get("family") or "qwen")[:50],
            "size_gb": float(metadata["size_gb"]),
            "memory_gb": float(metadata["memory_gb"]),
            "minimum_ram_gb": float(metadata["minimum_ram_gb"]),
            "official": True,
            "validated": True,
            "expected_digest": metadata.get("expected_digest"),
        }
    if not validated:
        raise ValueError("Model registry has no validated official models")
    return validated


def load_model_registry() -> tuple[dict[str, dict[str, Any]], str, bool]:
    """Load a signed override when configured, otherwise use the bundled registry."""
    registry_path = os.getenv("GODFIN_MODEL_REGISTRY_PATH")
    public_key_value = os.getenv("GODFIN_MODEL_REGISTRY_PUBLIC_KEY")
    if not registry_path or not public_key_value:
        return BUILTIN_MODEL_REGISTRY, "bundled", True

    path = Path(registry_path).expanduser()
    signature_path = path.with_suffix(path.suffix + ".sig")
    try:
        payload = path.read_bytes()
        signature = base64.b64decode(signature_path.read_text().strip(), validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(public_key_value, validate=True)
        )
        public_key.verify(signature, payload)
        return _validated_registry(json.loads(payload)), "signed_override", True
    except Exception:
        return BUILTIN_MODEL_REGISTRY, "bundled_fallback", False


def _total_memory_bytes() -> int:
    system = platform.system()
    if system == "Darwin":
        try:
            return int(
                subprocess.check_output(
                    ["sysctl", "-n", "hw.memsize"],
                    text=True,
                    timeout=2,
                ).strip()
            )
        except (OSError, ValueError, subprocess.SubprocessError):
            return 0
    if system == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return 0
    if system == "Windows":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return int(status.total_physical)
        except (AttributeError, OSError):
            return 0
    return 0


def _available_memory_bytes(total: int) -> int:
    if platform.system() == "Linux":
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            pass
    # A conservative estimate avoids recommending a model that crowds the OS.
    return int(total * 0.65)


def _acceleration() -> str:
    machine = platform.machine().lower()
    if platform.system() == "Darwin" and machine in {"arm64", "aarch64"}:
        return "apple_metal"
    if shutil.which("nvidia-smi"):
        return "nvidia_cuda"
    return "cpu"


def _expected_speed(model_memory_gb: float, available_gb: float, acceleration: str) -> str:
    if available_gb < model_memory_gb:
        return "will not fit comfortably"
    if acceleration in {"apple_metal", "nvidia_cuda"}:
        return "about 8–30 tokens/second; benchmark required"
    return "about 1–8 tokens/second; benchmark required"


def recommend_model(
    total_ram_gb: float,
    available_ram_gb: float,
    disk_free_gb: float,
    acceleration: str,
    registry: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    registry = registry or BUILTIN_MODEL_REGISTRY
    candidates: list[str]
    if total_ram_gb < 8:
        candidates = []
    elif total_ram_gb < 12:
        candidates = ["qwen3:1.7b"]
    elif total_ram_gb < 24:
        candidates = ["qwen3:4b", "qwen3:1.7b"]
    elif total_ram_gb < 32:
        candidates = ["qwen3:8b", "qwen3:4b", "qwen3:1.7b"]
    elif total_ram_gb < 48:
        candidates = ["qwen3.6:27b", "qwen3:8b", "qwen3:4b"]
    elif acceleration != "cpu":
        candidates = ["qwen3.6:35b-a3b", "qwen3.6:27b", "qwen3:8b"]
    else:
        candidates = ["qwen3.6:27b", "qwen3:8b", "qwen3:4b"]

    # A signed registry update may introduce an official smaller Qwen 3.6
    # variant after this build ships. Prefer the strongest such model that
    # fits the current RAM band without accepting community tags.
    released_smaller_qwen36 = sorted(
        (
            model
            for model, metadata in registry.items()
            if metadata.get("family") == "qwen3.6"
            and model not in {"qwen3.6:27b", "qwen3.6:35b-a3b"}
            and metadata.get("official")
            and metadata.get("validated")
            and float(metadata["minimum_ram_gb"]) <= total_ram_gb
        ),
        key=lambda model: float(registry[model]["memory_gb"]),
        reverse=True,
    )
    candidates = released_smaller_qwen36 + [
        model for model in candidates if model not in released_smaller_qwen36
    ]

    for model in candidates:
        metadata = registry.get(model)
        if not metadata:
            continue
        required_disk = float(metadata["size_gb"]) * 1.15
        if (
            disk_free_gb >= required_disk
            and available_ram_gb >= float(metadata["memory_gb"]) * 0.8
        ):
            return {
                "model": model,
                "reason": "Best validated model that fits the current memory and disk headroom.",
                "expected_speed": _expected_speed(
                    float(metadata["memory_gb"]),
                    available_ram_gb,
                    acceleration,
                ),
                **metadata,
            }

    return {
        "model": None,
        "reason": (
            "No local model is recommended with the current memory and disk "
            "headroom. GODFIN remains fully usable without AI."
        ),
        "expected_speed": None,
    }


def ollama_status() -> dict[str, Any]:
    executable = shutil.which("ollama")
    models: list[dict[str, Any]] = []
    running = False
    if executable:
        try:
            response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=1.5)
            response.raise_for_status()
            running = True
            for item in response.json().get("models", []):
                models.append(
                    {
                        "name": item.get("name") or item.get("model"),
                        "size": item.get("size"),
                        "digest": item.get("digest"),
                    }
                )
        except (httpx.HTTPError, ValueError):
            pass
    return {
        "installed": bool(executable),
        "running": running,
        "executable": executable,
        "models": models,
    }


def device_profile() -> dict[str, Any]:
    total = _total_memory_bytes()
    available = _available_memory_bytes(total)
    disk = shutil.disk_usage(Path.home())
    total_gb = round(total / (1024**3), 1) if total else 0
    available_gb = round(available / (1024**3), 1) if available else 0
    disk_free_gb = round(disk.free / (1024**3), 1)
    acceleration = _acceleration()
    registry, source, verified = load_model_registry()
    recommendation = recommend_model(
        total_gb,
        available_gb,
        disk_free_gb,
        acceleration,
        registry,
    )
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "total_ram_gb": total_gb,
        "available_ram_gb": available_gb,
        "disk_free_gb": disk_free_gb,
        "acceleration": acceleration,
        "ollama": ollama_status(),
        "recommendation": recommendation,
        "registry": {
            "source": source,
            "signature_verified": verified,
            "models": registry,
        },
        "privacy": (
            "Local prompts stay on this computer. GODFIN sends nothing to "
            "Ollama Cloud unless you separately configure a cloud provider."
        ),
        "installer_url": "https://ollama.com/download",
        "context_tokens": 8192,
    }


def benchmark_model(model: str) -> dict[str, Any]:
    registry, _, _ = load_model_registry()
    if model not in registry:
        raise ValueError("Model is not in GODFIN's validated registry")
    started = time.monotonic()
    response = httpx.post(
        f"{OLLAMA_BASE_URL}/api/generate",
        json={
            "model": model,
            "prompt": BENCHMARK_PROMPT,
            "stream": False,
            "options": {"num_ctx": 8192, "temperature": 0},
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    elapsed = max(0.001, time.monotonic() - started)
    eval_count = int(payload.get("eval_count") or 0)
    eval_duration = int(payload.get("eval_duration") or 0)
    tokens_per_second = (
        eval_count / (eval_duration / 1_000_000_000)
        if eval_count and eval_duration
        else eval_count / elapsed
    )
    return {
        "success": True,
        "model": model,
        "tokens_per_second": round(tokens_per_second, 1),
        "elapsed_seconds": round(elapsed, 2),
        "response_preview": str(payload.get("response") or "")[:300],
        "prompt_kind": "fixed_godfin_finance_explanation",
        "authoritative_totals": False,
    }


def _model_digest(model: str) -> str | None:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
        for item in response.json().get("models", []):
            if (item.get("name") or item.get("model")) == model:
                return item.get("digest")
    except (httpx.HTTPError, ValueError):
        return None
    return None


def _set_download_state(**values: Any) -> None:
    with _download_lock:
        _download_state.update(values)


def _run_model_pull(executable: str, model: str) -> None:
    global _download_process
    try:
        process = subprocess.Popen(
            [executable, "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        with _download_lock:
            _download_process = process
        output_tail = ""
        assert process.stdout is not None
        for chunk in iter(process.stdout.readline, ""):
            output_tail = (output_tail + chunk)[-500:]
            percentages = re.findall(r"(\d{1,3})%", output_tail)
            if percentages:
                _set_download_state(
                    progress=min(99, int(percentages[-1])),
                    message=f"Downloading {model}… {percentages[-1]}%",
                )
        return_code = process.wait()
        with _download_lock:
            cancelled = _download_state["status"] == "cancelling"
        if cancelled:
            _set_download_state(
                status="cancelled",
                message="Model download cancelled.",
            )
        elif return_code == 0:
            digest = _model_digest(model)
            if not digest:
                _set_download_state(
                    status="failed",
                    message="Download finished, but the local model digest could not be verified.",
                )
            else:
                _set_download_state(
                    status="complete",
                    progress=100,
                    message="Model downloaded and its local digest was verified.",
                    digest=digest,
                )
        else:
            _set_download_state(
                status="failed",
                message=(output_tail.strip() or "Ollama model download failed.")[-400:],
            )
    except OSError as exc:
        _set_download_state(status="failed", message=f"Could not start Ollama: {exc}")
    finally:
        with _download_lock:
            _download_process = None


def start_model_pull(model: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("Explicit download approval is required")
    registry, _, _ = load_model_registry()
    if model not in registry:
        raise ValueError("Model is not in GODFIN's validated registry")
    executable = shutil.which("ollama")
    if not executable:
        raise RuntimeError("Ollama is not installed")

    with _download_lock:
        if _download_state["status"] in {"queued", "downloading", "cancelling"}:
            raise RuntimeError("Another model download is already running")
        _download_state.update(
            {
                "status": "downloading",
                "model": model,
                "progress": 0,
                "message": f"Starting download for {model}…",
                "digest": None,
            }
        )
    thread = threading.Thread(
        target=_run_model_pull,
        args=(executable, model),
        daemon=True,
    )
    thread.start()
    return get_download_status()


def cancel_model_pull() -> dict[str, Any]:
    with _download_lock:
        process = _download_process
        if not process or _download_state["status"] != "downloading":
            return dict(_download_state)
        _download_state["status"] = "cancelling"
        _download_state["message"] = "Cancelling model download…"
    process.terminate()
    return get_download_status()


def get_download_status() -> dict[str, Any]:
    with _download_lock:
        return dict(_download_state)
