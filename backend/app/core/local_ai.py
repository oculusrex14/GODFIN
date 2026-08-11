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
import signal
import shutil
import subprocess
import sys
import threading
import time
import uuid
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
DOWNLOAD_STATE_KEY = "local_ai_download_job"
BENCHMARK_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MIN_BENCHMARK_TOKENS_PER_SECOND = 1.0
MAX_GODFIN_CONTEXT_TOKENS = 8192
MIN_GODFIN_CONTEXT_TOKENS = 2048
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
_download_cancel = threading.Event()
_download_shutdown = threading.Event()
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
    "job_id": None,
    "pid": None,
    "started_at": None,
    "updated_at": None,
    "finished_at": None,
    "retryable": False,
}


class LocalAIActionConflict(RuntimeError):
    """A mutually exclusive local-model action is already active."""


class LocalAIResourceError(RuntimeError):
    """The current measured device headroom cannot safely run an action."""


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


def _darwin_memory_bytes() -> tuple[int, int]:
    total = int(
        subprocess.check_output(
            ["sysctl", "-n", "hw.memsize"],
            text=True,
            timeout=2,
        ).strip()
    )
    page_size = int(
        subprocess.check_output(
            ["sysctl", "-n", "hw.pagesize"],
            text=True,
            timeout=2,
        ).strip()
    )
    output = subprocess.check_output(["vm_stat"], text=True, timeout=2)
    pages: dict[str, int] = {}
    for line in output.splitlines():
        match = re.match(r"([^:]+):\s+([0-9.]+)\.?$", line.strip())
        if match:
            pages[match.group(1)] = int(float(match.group(2)))
    available_names = (
        "Pages free",
        "Pages inactive",
        "Pages speculative",
        "Pages purgeable",
    )
    available = sum(pages.get(name, 0) for name in available_names) * page_size
    if available <= 0:
        raise ValueError("vm_stat did not report available pages")
    return total, min(total, available)


def _linux_memory_bytes() -> tuple[int, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        if ":" not in line:
            continue
        name, raw = line.split(":", 1)
        parts = raw.split()
        if parts:
            values[name] = int(parts[0]) * 1024
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", 0)
    if total <= 0 or available <= 0:
        raise ValueError("/proc/meminfo did not report current memory")
    return total, min(total, available)


def _windows_memory_bytes() -> tuple[int, int]:
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
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError("GlobalMemoryStatusEx failed")
    return int(status.total_physical), int(status.available_physical)


def _fallback_memory_bytes() -> tuple[int, int]:
    page_size = int(os.sysconf("SC_PAGE_SIZE"))
    total = int(os.sysconf("SC_PHYS_PAGES")) * page_size
    available = int(os.sysconf("SC_AVPHYS_PAGES")) * page_size
    if total <= 0 or available <= 0:
        raise ValueError("POSIX memory counters were unavailable")
    return total, min(total, available)


def _system_memory_bytes() -> tuple[int, int, str]:
    system = platform.system()
    readers = {
        "Darwin": (_darwin_memory_bytes, "macos_vm_stat"),
        "Linux": (_linux_memory_bytes, "linux_memavailable"),
        "Windows": (_windows_memory_bytes, "windows_global_memory_status"),
    }
    reader, source = readers.get(system, (_fallback_memory_bytes, "posix_available_pages"))
    try:
        total, available = reader()
        return total, available, source
    except (AttributeError, OSError, ValueError, subprocess.SubprocessError):
        try:
            total, available = _fallback_memory_bytes()
            return total, available, "posix_available_pages"
        except (AttributeError, OSError, ValueError):
            return 0, 0, "unavailable"


def _total_memory_bytes() -> int:
    """Compatibility wrapper for callers/tests that need only total RAM."""
    return _system_memory_bytes()[0]


def _available_memory_bytes(total: int | None = None) -> int:
    """Return measured currently available RAM; never synthesize a percentage."""
    del total
    return _system_memory_bytes()[1]


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


def _resource_requirements(
    metadata: dict[str, Any],
    total_ram_gb: float,
) -> dict[str, float]:
    os_headroom_gb = max(2.0, round(total_ram_gb * 0.125, 1))
    return {
        "required_available_ram_gb": round(
            float(metadata["memory_gb"]) + os_headroom_gb,
            1,
        ),
        "required_disk_free_gb": round(float(metadata["size_gb"]) * 1.15 + 2.0, 1),
        "os_headroom_gb": os_headroom_gb,
    }


def _resource_fit(
    metadata: dict[str, Any],
    total_ram_gb: float,
    available_ram_gb: float,
    disk_free_gb: float,
) -> tuple[bool, dict[str, float]]:
    requirements = _resource_requirements(metadata, total_ram_gb)
    fits = bool(
        total_ram_gb >= float(metadata["minimum_ram_gb"])
        and available_ram_gb >= requirements["required_available_ram_gb"]
        and disk_free_gb >= requirements["required_disk_free_gb"]
    )
    return fits, requirements


def _runtime_context_tokens(
    metadata: dict[str, Any],
    available_ram_gb: float,
    installed_maximum: int | None = None,
) -> int:
    remaining = available_ram_gb - float(metadata["memory_gb"])
    if remaining >= 8:
        selected = MAX_GODFIN_CONTEXT_TOKENS
    elif remaining >= 4:
        selected = 4096
    else:
        selected = MIN_GODFIN_CONTEXT_TOKENS
    if installed_maximum and installed_maximum > 0:
        selected = min(selected, installed_maximum)
    return max(512, selected)


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
        fits, requirements = _resource_fit(
            metadata,
            total_ram_gb,
            available_ram_gb,
            disk_free_gb,
        )
        if fits:
            return {
                "model": model,
                "status": "candidate",
                "reason": (
                    "Best validated candidate for the memory and disk currently available. "
                    "Run the short benchmark before activation."
                ),
                "expected_speed": _expected_speed(
                    float(metadata["memory_gb"]),
                    available_ram_gb,
                    acceleration,
                ),
                **requirements,
                **metadata,
            }

    return {
        "model": None,
        "status": "not_recommended",
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
                        "size_gb": round(float(item.get("size") or 0) / (1024**3), 2),
                        "digest": _normalize_digest(item.get("digest")),
                        "modified_at": str(item.get("modified_at") or "")[:64] or None,
                    }
                )
        except (httpx.HTTPError, ValueError):
            pass
    return {
        "installed": bool(executable),
        "running": running,
        "models": models,
    }


def _ollama_model_metadata(model: str) -> dict[str, Any] | None:
    try:
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/show",
            json={"model": model, "verbose": False},
            timeout=3,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    model_info = payload.get("model_info")
    if not isinstance(model_info, dict):
        model_info = {}
    context_values: list[int] = []
    for key, value in model_info.items():
        if str(key).endswith(".context_length"):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if 512 <= parsed <= 2_000_000:
                context_values.append(parsed)
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    return {
        "maximum_context_tokens": max(context_values) if context_values else None,
        "family": str(details.get("family") or "")[:64] or None,
        "parameter_size": str(details.get("parameter_size") or "")[:32] or None,
        "quantization_level": str(details.get("quantization_level") or "")[:32] or None,
    }


def device_profile(db: Any | None = None) -> dict[str, Any]:
    total, available, memory_source = _system_memory_bytes()
    disk = shutil.disk_usage(Path.home())
    total_gb = round(total / (1024**3), 1) if total else 0
    available_gb = round(available / (1024**3), 1) if available else 0
    disk_free_gb = round(disk.free / (1024**3), 1)
    acceleration = _acceleration()
    ollama = ollama_status()
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
    installed_metadata = None
    runtime_context = MIN_GODFIN_CONTEXT_TOKENS
    readiness = None
    if recommendation.get("model"):
        installed_tag = next(
            (
                item
                for item in ollama["models"]
                if item.get("name") == recommendation["model"]
            ),
            None,
        )
        installed_metadata = (
            _ollama_model_metadata(str(recommendation["model"]))
            if installed_tag is not None
            else None
        )
        if installed_metadata is not None and installed_tag is not None:
            installed_metadata = {
                **installed_metadata,
                "installed_size_gb": installed_tag.get("size_gb"),
                "digest": installed_tag.get("digest"),
                "modified_at": installed_tag.get("modified_at"),
            }
        runtime_context = _runtime_context_tokens(
            recommendation,
            available_gb,
            (installed_metadata or {}).get("maximum_context_tokens"),
        )
        readiness = (
            local_model_readiness(
                str(recommendation["model"]),
                db=db,
                verify_runtime=True,
                total_ram_gb=total_gb,
                available_ram_gb=available_gb,
                disk_free_gb=disk_free_gb,
            )
            if installed_tag is not None
            else {"ready": False, "reason": "model_not_installed"}
        )
        if readiness["ready"]:
            recommendation["status"] = "benchmarked"
            recommendation["reason"] = (
                "This signed model fits current headroom and passed GODFIN's recent "
                "local finance benchmark."
            )
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor() or platform.machine(),
        "total_ram_gb": total_gb,
        "available_ram_gb": available_gb,
        "memory_measurement": memory_source,
        "memory_measured_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "disk_free_gb": disk_free_gb,
        "acceleration": acceleration,
        "ollama": ollama,
        "recommendation": recommendation,
        "installed_model_metadata": installed_metadata,
        "readiness": readiness,
        "registry": {
            **registry_status,
            "models": registry,
        },
        "privacy": (
            "Local prompts stay on this computer. GODFIN sends nothing to "
            "Ollama Cloud unless you separately configure a cloud provider."
        ),
        "installer_url": "https://ollama.com/download",
        "context_tokens": runtime_context,
        "context_policy": (
            "GODFIN uses a bounded working context based on current free memory and "
            "the installed model's reported maximum."
        ),
    }


def _write_json_setting(key: str, record: dict[str, Any]) -> None:
    from app.core.database import SessionLocal
    from app.models.app_setting import AppSetting

    encoded = json.dumps(record, separators=(",", ":"), sort_keys=True)
    db = SessionLocal()
    try:
        setting = db.query(AppSetting).filter_by(key=key).first()
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


def _read_json_setting(db: Any, key: str) -> dict[str, Any] | None:
    from app.models.app_setting import AppSetting

    setting = db.query(AppSetting).filter_by(key=key).first()
    if setting is None:
        return None
    try:
        value = json.loads(setting.value)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _benchmark_key(model: str) -> str:
    if not MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError("Invalid model name")
    return f"local_ai_benchmark:{model}"[:100]


def _load_benchmark_record(model: str, db: Any | None = None) -> dict[str, Any] | None:
    owns_session = db is None
    if owns_session:
        from app.core.database import SessionLocal

        db = SessionLocal()
    try:
        return _read_json_setting(db, _benchmark_key(model))
    finally:
        if owns_session:
            db.close()


def local_model_readiness(
    model: str,
    *,
    db: Any | None = None,
    verify_runtime: bool = True,
    total_ram_gb: float | None = None,
    available_ram_gb: float | None = None,
    disk_free_gb: float | None = None,
) -> dict[str, Any]:
    registry, registry_status = load_model_registry()
    metadata = registry.get(model)
    if not registry_status["signature_verified"] or metadata is None:
        return {"ready": False, "reason": "signed_registry_unavailable"}

    if total_ram_gb is None or available_ram_gb is None:
        total, available, _source = _system_memory_bytes()
        total_ram_gb = round(total / (1024**3), 1) if total else 0
        available_ram_gb = round(available / (1024**3), 1) if available else 0
    if disk_free_gb is None:
        disk_free_gb = round(shutil.disk_usage(Path.home()).free / (1024**3), 1)
    fits, requirements = _resource_fit(
        metadata,
        total_ram_gb,
        available_ram_gb,
        disk_free_gb,
    )
    if not fits:
        return {
            "ready": False,
            "reason": "insufficient_current_headroom",
            **requirements,
        }

    verification = None
    if verify_runtime:
        verification = verify_installed_model(model, remove_on_mismatch=True)
        if not verification["verified"]:
            return {
                "ready": False,
                "reason": "installed_digest_not_verified",
                **requirements,
            }

    benchmark = _load_benchmark_record(model, db=db)
    if not benchmark:
        return {"ready": False, "reason": "benchmark_required", **requirements}
    try:
        completed_at = datetime.fromisoformat(
            str(benchmark["completed_at"]).replace("Z", "+00:00")
        )
        if completed_at.tzinfo is None:
            raise ValueError("benchmark time must include a timezone")
        completed_at = completed_at.astimezone(UTC)
        age_seconds = max(0, (datetime.now(UTC) - completed_at).total_seconds())
        speed = float(benchmark["tokens_per_second"])
    except (KeyError, TypeError, ValueError):
        return {"ready": False, "reason": "benchmark_invalid", **requirements}
    expected_digest = _normalize_digest(metadata.get("expected_digest"))
    benchmark_digest = _normalize_digest(benchmark.get("digest"))
    runtime_digest = _normalize_digest((verification or {}).get("digest"))
    digest_matches = bool(
        expected_digest
        and benchmark_digest
        and hmac.compare_digest(expected_digest, benchmark_digest)
        and (
            runtime_digest is None
            or hmac.compare_digest(expected_digest, runtime_digest)
        )
    )
    if not digest_matches:
        return {"ready": False, "reason": "benchmark_digest_stale", **requirements}
    if age_seconds > BENCHMARK_MAX_AGE_SECONDS:
        return {"ready": False, "reason": "benchmark_expired", **requirements}
    if not benchmark.get("success") or speed < MIN_BENCHMARK_TOKENS_PER_SECOND:
        return {"ready": False, "reason": "benchmark_too_slow", **requirements}
    return {
        "ready": True,
        "reason": "verified_and_benchmarked",
        "benchmark": {
            "tokens_per_second": round(speed, 1),
            "completed_at": completed_at.isoformat(),
            "context_tokens": int(benchmark.get("context_tokens") or 0),
        },
        **requirements,
    }


def assert_local_model_ready(model: str, db: Any | None = None) -> None:
    readiness = local_model_readiness(model, db=db)
    if not readiness["ready"]:
        raise LocalAIResourceError(
            "The selected local model must fit current headroom and pass a recent "
            "GODFIN benchmark before activation."
        )


def benchmark_model(model: str) -> dict[str, Any]:
    if not _benchmark_lock.acquire(blocking=False):
        raise RuntimeError("A local benchmark is already running")
    try:
        verification = verify_installed_model(model, remove_on_mismatch=True)
        if not verification["verified"]:
            raise ValueError(verification["message"])
        registry, _registry_status = load_model_registry()
        metadata = registry[model]
        total, available, memory_source = _system_memory_bytes()
        total_gb = round(total / (1024**3), 1) if total else 0
        available_gb = round(available / (1024**3), 1) if available else 0
        disk_free_gb = round(shutil.disk_usage(Path.home()).free / (1024**3), 1)
        fits, requirements = _resource_fit(
            metadata,
            total_gb,
            available_gb,
            disk_free_gb,
        )
        if not fits:
            raise LocalAIResourceError(
                "Current free memory or disk space is below the safe benchmark headroom."
            )
        installed_metadata = _ollama_model_metadata(model) or {}
        context_tokens = _runtime_context_tokens(
            metadata,
            available_gb,
            installed_metadata.get("maximum_context_tokens"),
        )
        started = time.monotonic()
        response = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": model,
                "prompt": BENCHMARK_PROMPT,
                "stream": False,
                "options": {"num_ctx": context_tokens, "temperature": 0},
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
        successful = bool(
            str(payload.get("response") or "").strip()
            and tokens_per_second >= MIN_BENCHMARK_TOKENS_PER_SECOND
        )
        result = {
            "success": successful,
            "model": model,
            "tokens_per_second": round(tokens_per_second, 1),
            "elapsed_seconds": round(elapsed, 2),
            "response_preview": str(payload.get("response") or "")[:300],
            "prompt_kind": "fixed_godfin_finance_explanation",
            "authoritative_totals": False,
            "activation_ready": successful,
            "context_tokens": context_tokens,
            "digest": verification["digest"],
            "completed_at": datetime.now(UTC).isoformat(),
            "memory_measurement": memory_source,
            "available_ram_gb": available_gb,
            "disk_free_gb": disk_free_gb,
            **requirements,
        }
        _write_json_setting(_benchmark_key(model), result)
        return result
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
    model = str(record.get("model") or "")
    if not MODEL_NAME_PATTERN.fullmatch(model):
        raise ValueError("Cannot persist an invalid model acceptance record")
    _write_json_setting(f"local_ai_acceptance:{model}"[:100], record)


def _persist_download_state(record: dict[str, Any], *, strict: bool = False) -> None:
    try:
        _write_json_setting(DOWNLOAD_STATE_KEY, record)
    except Exception:
        logger.exception("Could not persist local-model download state")
        if strict:
            raise


def _set_download_state(*, persist: bool = True, **values: Any) -> None:
    values.setdefault("updated_at", datetime.now(UTC).isoformat())
    with _download_lock:
        _download_state.update(values)
        snapshot = dict(_download_state)
    if persist:
        _persist_download_state(snapshot)


def _process_command_matches(pid: int, model: str) -> bool:
    if pid <= 0 or not MODEL_NAME_PATTERN.fullmatch(model):
        return False
    try:
        if os.name == "nt":
            command = subprocess.check_output(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    (
                        "(Get-CimInstance Win32_Process -Filter "
                        f"'ProcessId = {pid}').CommandLine"
                    ),
                ],
                text=True,
                timeout=3,
            )
        else:
            command = subprocess.check_output(
                ["ps", "-p", str(pid), "-o", "command="],
                text=True,
                timeout=3,
            )
    except (OSError, subprocess.SubprocessError):
        return False
    normalized = " ".join(command.lower().split())
    return bool("ollama" in normalized and " pull " in f" {normalized} " and model in normalized)


def _terminate_persisted_process(record: dict[str, Any]) -> bool:
    try:
        pid = int(record.get("pid") or 0)
    except (TypeError, ValueError):
        return False
    model = str(record.get("model") or "")
    if not _process_command_matches(pid, model):
        return False
    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
            return result.returncode == 0
        os.killpg(pid, signal.SIGTERM)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _terminate_current_process(process: subprocess.Popen[str]) -> None:
    try:
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    except OSError:
        return


def _run_model_pull(
    executable: str,
    model: str,
    approval: dict[str, Any],
) -> None:
    global _download_process
    try:
        popen_options: dict[str, Any] = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        process = subprocess.Popen(
            [executable, "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            **popen_options,
        )
        with _download_lock:
            _download_process = process
        process_pid = getattr(process, "pid", None)
        if isinstance(process_pid, int) and process_pid > 0:
            _set_download_state(pid=process_pid)
        if _download_cancel.is_set():
            _terminate_current_process(process)
        output_tail = ""
        assert process.stdout is not None
        for chunk in iter(process.stdout.readline, ""):
            output_tail = (output_tail + chunk)[-500:]
            percentages = re.findall(r"(\d{1,3})%", output_tail)
            if percentages:
                progress = min(99, int(percentages[-1]))
                _set_download_state(
                    progress=progress,
                    message=f"Downloading {model}… {progress}%",
                )
        return_code = process.wait()
        with _download_lock:
            cancelled = _download_state["status"] == "cancelling"
        if _download_shutdown.is_set():
            _set_download_state(
                status="interrupted",
                message=(
                    "The app closed before the model download finished. "
                    "Retry to resume safely."
                ),
                pid=None,
                finished_at=datetime.now(UTC).isoformat(),
                retryable=True,
            )
        elif cancelled or _download_cancel.is_set():
            _set_download_state(
                status="cancelled",
                message="Model download cancelled.",
                pid=None,
                finished_at=datetime.now(UTC).isoformat(),
                retryable=True,
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
                    pid=None,
                    finished_at=datetime.now(UTC).isoformat(),
                    retryable=True,
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
                    pid=None,
                    finished_at=accepted_at,
                    retryable=False,
                )
        else:
            logger.warning("Ollama model pull exited with code %s", return_code)
            _set_download_state(
                status="failed",
                message=(
                    "Ollama could not download the selected model. Check your "
                    "connection, available disk space, and Ollama status, then try again."
                ),
                pid=None,
                finished_at=datetime.now(UTC).isoformat(),
                retryable=True,
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
            pid=None,
            finished_at=datetime.now(UTC).isoformat(),
            retryable=True,
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

    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        recovered = restore_download_status(db)
    finally:
        db.close()
    if recovered["status"] in {"queued", "downloading", "cancelling"}:
        raise LocalAIActionConflict("Another model download is already running")

    total, available, _memory_source = _system_memory_bytes()
    total_gb = round(total / (1024**3), 1) if total else 0
    available_gb = round(available / (1024**3), 1) if available else 0
    disk_free_gb = round(shutil.disk_usage(Path.home()).free / (1024**3), 1)
    fits, requirements = _resource_fit(
        registry[model],
        total_gb,
        available_gb,
        disk_free_gb,
    )
    if not fits:
        raise LocalAIResourceError(
            "Current free memory or disk space is below the selected model's safe headroom."
        )

    with _download_lock:
        if _download_state["status"] in {"queued", "downloading", "cancelling"}:
            raise LocalAIActionConflict("Another model download is already running")
        previous_state = dict(_download_state)
        _download_cancel.clear()
        _download_shutdown.clear()
        approved_at = datetime.now(UTC).isoformat()
        job_id = str(uuid.uuid4())
        approval = {
            "model": model,
            "expected_digest": expected_digest,
            "registry_version": registry_status["registry_version"],
            "registry_source": registry_status["source"],
            "issued_at": registry_status["issued_at"],
            "expires_at": registry_status["expires_at"],
            "approved_at": approved_at,
            "ollama_version": _ollama_version(executable),
            "job_id": job_id,
            **requirements,
        }
        initial_state = {
            **_download_state,
            "status": "queued",
            "model": model,
            "progress": 0,
            "message": f"Preparing download for {model}…",
            "digest": None,
            "expected_digest": expected_digest,
            "signature_verified": True,
            "digest_verified": False,
            "registry_version": registry_status["registry_version"],
            "registry_source": registry_status["source"],
            "ollama_version": approval["ollama_version"],
            "approved_at": approved_at,
            "accepted_at": None,
            "job_id": job_id,
            "pid": None,
            "started_at": approved_at,
            "updated_at": approved_at,
            "finished_at": None,
            "retryable": False,
            **requirements,
        }
        # Reserve the single-flight slot before durable persistence. A second
        # request must observe this queued state while the first write is in
        # progress, otherwise two Ollama pulls could be launched concurrently.
        _download_state.update(initial_state)
    try:
        _persist_download_state(initial_state, strict=True)
    except Exception as exc:
        with _download_lock:
            if _download_state.get("job_id") == job_id:
                _download_state.clear()
                _download_state.update(previous_state)
        raise RuntimeError("The download job could not be saved safely") from exc
    with _download_lock:
        cancelled_before_start = (
            _download_state.get("job_id") == job_id
            and (
                _download_state.get("status") == "cancelling"
                or _download_cancel.is_set()
            )
        )
        if cancelled_before_start:
            _download_state.update(
                {
                    "status": "cancelled",
                    "message": "Model download cancelled before it started.",
                    "finished_at": datetime.now(UTC).isoformat(),
                    "retryable": True,
                }
            )
        else:
            _download_state["status"] = "downloading"
            _download_state["message"] = f"Starting download for {model}…"
    if cancelled_before_start:
        _set_download_state()
        return get_download_status()
    _set_download_state(status="downloading", message=f"Starting download for {model}…")
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
        if _download_state["status"] not in {"queued", "downloading"}:
            return dict(_download_state)
        _download_cancel.set()
        _download_state.update(
            {
                "status": "cancelling",
                "message": "Cancelling model download…",
                "retryable": True,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        snapshot = dict(_download_state)
    _persist_download_state(snapshot)
    if process:
        _terminate_current_process(process)
    return get_download_status()


def shutdown_model_pull() -> None:
    """Stop an owned pull during normal shutdown and persist restart guidance."""
    with _download_lock:
        process = _download_process
        active = _download_state["status"] in {"queued", "downloading", "cancelling"}
    if not active:
        return
    _download_shutdown.set()
    _download_cancel.set()
    if process:
        _terminate_current_process(process)
    _set_download_state(
        status="interrupted",
        message="The app closed before the model download finished. Retry to resume safely.",
        pid=None,
        finished_at=datetime.now(UTC).isoformat(),
        retryable=True,
    )


def get_download_status() -> dict[str, Any]:
    with _download_lock:
        return dict(_download_state)


def restore_download_status(db: Any) -> dict[str, Any]:
    """Reconcile durable pull state and re-verify accepted models after restart."""
    from app.models.app_setting import AppSetting

    current = get_download_status()
    if current["status"] in {"downloading", "cancelling", "complete"}:
        return current
    persisted = _read_json_setting(db, DOWNLOAD_STATE_KEY)
    if persisted:
        status = str(persisted.get("status") or "")
        model = str(persisted.get("model") or "")
        if (
            status in {"queued", "downloading", "cancelling"}
            and MODEL_NAME_PATTERN.fullmatch(model)
        ):
            verification = verify_installed_model(model, remove_on_mismatch=True)
            if verification["verified"]:
                accepted_at = datetime.now(UTC).isoformat()
                acceptance = {
                    key: persisted.get(key)
                    for key in (
                        "model",
                        "expected_digest",
                        "registry_version",
                        "registry_source",
                        "issued_at",
                        "expires_at",
                        "approved_at",
                        "ollama_version",
                        "job_id",
                    )
                }
                acceptance.update(
                    {
                        "digest": verification["digest"],
                        "accepted_at": accepted_at,
                        "signature_verified": True,
                    }
                )
                _persist_model_acceptance(acceptance)
                _set_download_state(**{
                    **persisted,
                    "status": "complete",
                    "progress": 100,
                    "message": "Completed download was verified after the app restarted.",
                    "digest": verification["digest"],
                    "signature_verified": True,
                    "digest_verified": True,
                    "accepted_at": accepted_at,
                    "pid": None,
                    "finished_at": accepted_at,
                    "retryable": False,
                })
                return get_download_status()
            orphan_terminated = _terminate_persisted_process(persisted)
            _set_download_state(**{
                **persisted,
                "status": "interrupted",
                "progress": min(99, max(0, int(persisted.get("progress") or 0))),
                "message": "The previous model download was interrupted. Retry to resume safely.",
                "pid": None,
                "finished_at": datetime.now(UTC).isoformat(),
                "retryable": True,
                "orphan_process_terminated": orphan_terminated,
            })
            return get_download_status()
        if status in {"failed", "cancelled", "interrupted"}:
            _set_download_state(**persisted)
            return get_download_status()
        if status == "complete" and MODEL_NAME_PATTERN.fullmatch(model):
            verification = verify_installed_model(model, remove_on_mismatch=True)
            if verification["verified"]:
                _set_download_state(**{
                    **persisted,
                    "status": "complete",
                    "progress": 100,
                    "digest": verification["digest"],
                    "signature_verified": True,
                    "digest_verified": True,
                    "retryable": False,
                })
                return get_download_status()
            _set_download_state(**{
                **persisted,
                **verification,
                "status": "failed",
                "progress": 0,
                "signature_verified": bool(
                    verification.get("registry", {}).get("signature_verified")
                ),
                "digest_verified": False,
                "retryable": True,
            })
            return get_download_status()
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
