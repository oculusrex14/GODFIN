"""Device-aware, opt-in local AI setup for GODFIN.

The deterministic finance engine never depends on this module.  Ollama is
started only after an authenticated user explicitly approves a registry model.
"""
from __future__ import annotations

import base64
import hmac
import json
import logging
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


logger = logging.getLogger(__name__)


OLLAMA_BASE_URL = "http://127.0.0.1:11434"
BENCHMARK_PROMPT = (
    "In one short sentence, explain why a savings rate is calculated from "
    "verified income and spending totals. Do not calculate or invent amounts."
)
MODEL_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}:[a-z0-9][a-z0-9._-]{0,63}$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
MINIMUM_REGISTRY_VERSION = "2026-08-02.1"
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
BUNDLED_REGISTRY_PATH = RESOURCE_ROOT / "shared" / "model-registry.json"
BUNDLED_REGISTRY_SIGNATURE_PATH = RESOURCE_ROOT / "shared" / "model-registry.json.sig"
BUNDLED_REGISTRY_PUBLIC_KEY_PATH = RESOURCE_ROOT / "shared" / "model-registry-public-key.txt"

BUILTIN_MODEL_REGISTRY: dict[str, dict[str, Any]] = {
    "qwen3:1.7b": {
        "label": "Qwen 3 1.7B",
        "family": "qwen",
        "size_gb": 1.4,
        "memory_gb": 4,
        "minimum_ram_gb": 8,
        "official": True,
        "validated": True,
        "expected_digest": "sha256:8f68893c685c3ddff2aa3fffce2aa60a30bb2da65ca488b61fff134a4d1730e7",
    },
    "qwen3:4b": {
        "label": "Qwen 3 4B",
        "family": "qwen",
        "size_gb": 2.6,
        "memory_gb": 7,
        "minimum_ram_gb": 12,
        "official": True,
        "validated": True,
        "expected_digest": "sha256:359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7",
    },
    "qwen3:8b": {
        "label": "Qwen 3 8B",
        "family": "qwen",
        "size_gb": 5.2,
        "memory_gb": 12,
        "minimum_ram_gb": 24,
        "official": True,
        "validated": True,
        "expected_digest": "sha256:500a1f067a9f782620b40bee6f7b0c89e17ae61f686b92c24933e4ca4b2b8b41",
    },
    "qwen3.6:27b": {
        "label": "Qwen 3.6 27B",
        "family": "qwen3.6",
        "size_gb": 17,
        "memory_gb": 24,
        "minimum_ram_gb": 32,
        "official": True,
        "validated": True,
        "expected_digest": "sha256:a50eda8ed977ab48a12431878896b27ffd5cef552c17af3317d9623b939a7f1e",
    },
    "qwen3.6:35b-a3b": {
        "label": "Qwen 3.6 35B A3B",
        "family": "qwen3.6",
        "size_gb": 24,
        "memory_gb": 32,
        "minimum_ram_gb": 48,
        "official": True,
        "validated": True,
        "expected_digest": "sha256:07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522",
    },
}

_download_lock = threading.Lock()
_benchmark_lock = threading.Lock()
_download_process: subprocess.Popen[str] | None = None
_download_state: dict[str, Any] = {
    "status": "idle",
    "model": None,
    "progress": 0,
    "message": "No model download is running.",
    "digest": None,
    "expected_digest": None,
    "signature_verified": False,
    "digest_verified": False,
    "registry_version": None,
    "registry_source": None,
    "ollama_version": None,
    "approved_at": None,
    "accepted_at": None,
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
        numeric_values = {
            "size_gb": float(metadata["size_gb"]),
            "memory_gb": float(metadata["memory_gb"]),
            "minimum_ram_gb": float(metadata["minimum_ram_gb"]),
        }
        if any(not math.isfinite(value) or value <= 0 for value in numeric_values.values()):
            raise ValueError("Model registry contains invalid resource requirements")
        expected_digest = str(metadata.get("expected_digest") or "").lower()
        if not DIGEST_PATTERN.fullmatch(expected_digest):
            raise ValueError(f"Model registry is missing a pinned digest for {model}")
        validated[model] = {
            "label": str(metadata.get("label") or model)[:100],
            "family": str(metadata.get("family") or "qwen")[:50],
            **numeric_values,
            "official": True,
            "validated": True,
            "expected_digest": expected_digest,
        }
    if not validated:
        raise ValueError("Model registry has no validated official models")
    return validated


def _parse_registry_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Model registry {field} must be an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Model registry {field} is invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"Model registry {field} must include a timezone")
    return parsed.astimezone(UTC)


def _registry_version_key(value: str) -> tuple[int, int, int, int]:
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})\.(\d+)", value)
    if not match:
        raise ValueError("Model registry version format is invalid")
    return tuple(int(part) for part in match.groups())


def _load_signed_registry(
    path: Path,
    signature_path: Path,
    *,
    source: str,
    public_key_path: Path = BUNDLED_REGISTRY_PUBLIC_KEY_PATH,
    now: datetime | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    payload = path.read_bytes()
    signature = base64.b64decode(signature_path.read_text().strip(), validate=True)
    public_key_bytes = base64.b64decode(public_key_path.read_text().strip(), validate=True)
    if len(public_key_bytes) != 32:
        raise ValueError("Model registry public key is invalid")
    Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(signature, payload)

    document = json.loads(payload)
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise ValueError("Unsupported model registry schema")
    version = str(document.get("registry_version") or "")[:100]
    if not version:
        raise ValueError("Model registry version is missing")
    if _registry_version_key(version) < _registry_version_key(MINIMUM_REGISTRY_VERSION):
        raise ValueError("Model registry rollback was rejected")
    issued_at = _parse_registry_time(document.get("issued_at"), "issued_at")
    expires_at = _parse_registry_time(document.get("expires_at"), "expires_at")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if issued_at > current:
        raise ValueError("Model registry is not active yet")
    if expires_at <= current:
        raise ValueError("Model registry has expired")

    return _validated_registry(document), {
        "source": source,
        "signature_verified": True,
        "registry_version": version,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "error": None,
    }


def load_model_registry(
    *,
    now: datetime | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Load one authenticated registry. Invalid overrides fail closed."""
    override = os.getenv("GODFIN_MODEL_REGISTRY_PATH")
    path = Path(override).expanduser() if override else BUNDLED_REGISTRY_PATH
    signature_path = path.with_suffix(path.suffix + ".sig")
    source = "signed_override" if override else "bundled_signed"
    try:
        return _load_signed_registry(
            path,
            signature_path,
            source=source,
            now=now,
        )
    except Exception as exc:
        return {}, {
            "source": source,
            "signature_verified": False,
            "registry_version": None,
            "issued_at": None,
            "expires_at": None,
            "error": (
                "Signed model registry verification failed "
                f"({type(exc).__name__})."
            ),
        }


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
    registry: dict[str, dict[str, Any]],
) -> dict[str, Any]:
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
    registry, registry_status = load_model_registry()
    recommendation = (
        recommend_model(
            total_gb,
            available_gb,
            disk_free_gb,
            acceleration,
            registry,
        )
        if registry_status["signature_verified"]
        else {
            "model": None,
            "reason": (
                "GODFIN could not verify its signed model registry. Local model "
                "downloads are disabled until the registry is repaired or updated."
            ),
            "expected_speed": None,
        }
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
            **registry_status,
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
    if not _benchmark_lock.acquire(blocking=False):
        raise RuntimeError("A local benchmark is already running")
    try:
        verification = verify_installed_model(model, remove_on_mismatch=True)
        if not verification["verified"]:
            raise ValueError(verification["message"])
        started = time.monotonic()
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": BENCHMARK_PROMPT,
                "stream": False,
                "options": {"num_ctx": 8192, "temperature": 0},
            },
            timeout=60,
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
    finally:
        _benchmark_lock.release()


def _model_digest(model: str) -> str | None:
    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)
        response.raise_for_status()
        for item in response.json().get("models", []):
            if (item.get("name") or item.get("model")) == model:
                return _normalize_digest(item.get("digest"))
    except (httpx.HTTPError, ValueError):
        return None
    return None


def _normalize_digest(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", normalized):
        normalized = f"sha256:{normalized}"
    return normalized if DIGEST_PATTERN.fullmatch(normalized) else None


def _ollama_version(executable: str) -> str:
    try:
        return subprocess.check_output(
            [executable, "--version"],
            text=True,
            stderr=subprocess.STDOUT,
            timeout=5,
        ).strip()[:120]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _remove_untrusted_model(executable: str, model: str) -> bool:
    try:
        result = subprocess.run(
            [executable, "rm", model],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_installed_model(
    model: str,
    *,
    remove_on_mismatch: bool = False,
) -> dict[str, Any]:
    registry, registry_status = load_model_registry()
    if not registry_status["signature_verified"]:
        return {
            "verified": False,
            "model": model,
            "message": "The signed GODFIN model registry could not be verified.",
            "registry": registry_status,
        }
    metadata = registry.get(model)
    if not metadata:
        return {
            "verified": False,
            "model": model,
            "message": "Model is not in GODFIN's signed registry.",
            "registry": registry_status,
        }

    expected = _normalize_digest(metadata.get("expected_digest"))
    actual = _model_digest(model)
    verified = bool(expected and actual and hmac.compare_digest(expected, actual))
    removed = False
    if not verified and actual and remove_on_mismatch:
        executable = shutil.which("ollama")
        if executable:
            removed = _remove_untrusted_model(executable, model)
    if verified:
        message = "Model digest matches the signed GODFIN registry."
    elif actual:
        message = (
            "Installed model digest does not match the signed GODFIN registry; "
            + ("the untrusted model was removed." if removed else "remove it before retrying.")
        )
    else:
        message = "The installed model digest could not be read."
    return {
        "verified": verified,
        "model": model,
        "expected_digest": expected,
        "digest": actual,
        "removed": removed,
        "message": message,
        "registry": registry_status,
    }


def _persist_model_acceptance(record: dict[str, Any]) -> None:
    from app.core.database import SessionLocal
    from app.models.app_setting import AppSetting

    model = str(record.get("model") or "")
    if not MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError("Cannot persist an invalid model acceptance record")
    key = f"local_ai_acceptance:{model}"[:100]
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter_by(key=key).first()
        encoded = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if setting is None:
            db.add(AppSetting(key=key, value=encoded))
        else:
            setting.value = encoded
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _set_download_state(**values: Any) -> None:
    with _download_lock:
        _download_state.update(values)


def _run_model_pull(
    executable: str,
    model: str,
    approval: dict[str, Any],
) -> None:
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
            expected_digest = _normalize_digest(approval.get("expected_digest"))
            expires_at = _parse_registry_time(approval.get("expires_at"), "expires_at")
            registry_current = datetime.now(UTC) < expires_at
            matches = bool(
                digest
                and expected_digest
                and registry_current
                and hmac.compare_digest(digest, expected_digest)
            )
            if not matches:
                removed = _remove_untrusted_model(executable, model) if digest else False
                _set_download_state(
                    status="failed",
                    message=(
                        "Downloaded model did not match the signed GODFIN registry"
                        + (" and was removed." if removed else ".")
                    ),
                    digest=digest,
                    expected_digest=expected_digest,
                    signature_verified=True,
                    digest_verified=False,
                )
            else:
                accepted_at = datetime.now(UTC).isoformat()
                acceptance = {
                    **approval,
                    "model": model,
                    "digest": digest,
                    "accepted_at": accepted_at,
                    "signature_verified": True,
                }
                _persist_model_acceptance(acceptance)
                _set_download_state(
                    status="complete",
                    progress=100,
                    message="Model matches the signed GODFIN registry.",
                    digest=digest,
                    expected_digest=expected_digest,
                    signature_verified=True,
                    digest_verified=True,
                    accepted_at=accepted_at,
                )
        else:
            logger.warning("Ollama model pull exited with code %s", return_code)
            _set_download_state(
                status="failed",
                message=(
                    "Ollama could not download the selected model. Check your "
                    "connection, available disk space, and Ollama status, then try again."
                ),
            )
    except Exception:
        logger.exception("Local model setup failed")
        _set_download_state(
            status="failed",
            message=(
                "Local model setup could not finish. Check that Ollama is running "
                "and try again."
            ),
            digest_verified=False,
        )
    finally:
        with _download_lock:
            _download_process = None


def start_model_pull(model: str, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise ValueError("Explicit download approval is required")
    registry, registry_status = load_model_registry()
    if not registry_status["signature_verified"]:
        raise RuntimeError("GODFIN's signed model registry could not be verified")
    if model not in registry:
        raise ValueError("Model is not in GODFIN's signed validated registry")
    expected_digest = _normalize_digest(registry[model].get("expected_digest"))
    if not expected_digest:
        raise RuntimeError("The selected model has no pinned registry digest")
    executable = shutil.which("ollama")
    if not executable:
        raise RuntimeError("Ollama is not installed")

    with _download_lock:
        if _download_state["status"] in {"queued", "downloading", "cancelling"}:
            raise RuntimeError("Another model download is already running")
        approved_at = datetime.now(UTC).isoformat()
        approval = {
            "model": model,
            "expected_digest": expected_digest,
            "registry_version": registry_status["registry_version"],
            "registry_source": registry_status["source"],
            "issued_at": registry_status["issued_at"],
            "expires_at": registry_status["expires_at"],
            "approved_at": approved_at,
            "ollama_version": _ollama_version(executable),
        }
        _download_state.update(
            {
                "status": "downloading",
                "model": model,
                "progress": 0,
                "message": f"Starting download for {model}…",
                "digest": None,
                "expected_digest": expected_digest,
                "signature_verified": True,
                "digest_verified": False,
                "registry_version": registry_status["registry_version"],
                "registry_source": registry_status["source"],
                "ollama_version": approval["ollama_version"],
                "approved_at": approved_at,
                "accepted_at": None,
            }
        )
    thread = threading.Thread(
        target=_run_model_pull,
        args=(executable, model, approval),
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


def restore_download_status(db: Any) -> dict[str, Any]:
    """Re-verify the most recent accepted model after an application restart."""
    from app.models.app_setting import AppSetting

    current = get_download_status()
    if current["status"] in {"downloading", "cancelling", "complete"}:
        return current
    rows = (
        db.query(AppSetting)
        .filter(AppSetting.key.like("local_ai_acceptance:%"))
        .all()
    )
    records: list[dict[str, Any]] = []
    for row in rows:
        try:
            record = json.loads(row.value)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(record, dict) and MODEL_NAME_PATTERN.fullmatch(
            str(record.get("model") or "")
        ):
            records.append(record)
    records.sort(key=lambda record: str(record.get("accepted_at") or ""), reverse=True)
    for record in records:
        verification = verify_installed_model(
            str(record["model"]),
            remove_on_mismatch=True,
        )
        if verification["verified"]:
            restored = {
                **current,
                **record,
                "status": "complete",
                "progress": 100,
                "message": "Installed model still matches the signed GODFIN registry.",
                "signature_verified": True,
                "digest_verified": True,
            }
            _set_download_state(**restored)
            return get_download_status()
        failed = {
            **current,
            **verification,
            "status": "failed",
            "progress": 0,
            "signature_verified": bool(
                verification.get("registry", {}).get("signature_verified")
            ),
            "digest_verified": False,
        }
        _set_download_state(**failed)
        return get_download_status()
    return current
