"""Bounded, aggregate-only local service metrics with no remote telemetry."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

_BUCKETS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000)
_MAX_OPERATION_KEYS = 128
_lock = threading.Lock()
_requests: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "count": 0,
        "errors": 0,
        "total_ms": 0.0,
        "max_ms": 0.0,
        "buckets": [0] * (len(_BUCKETS_MS) + 1),
    }
)


def _operation_key(method: str, operation: str) -> str:
    normalized_method = str(method or "UNKNOWN").upper()[:10]
    normalized_operation = "_".join(str(operation or "unmatched").split())[:100]
    return f"{normalized_method} {normalized_operation}"


def record_request(
    method: str,
    operation: str,
    status_code: int,
    duration_ms: float,
) -> None:
    key = _operation_key(method, operation)
    duration = max(0.0, min(float(duration_ms), 300_000.0))
    with _lock:
        if key not in _requests and len(_requests) >= _MAX_OPERATION_KEYS:
            key = "OTHER bounded_operations"
        item = _requests[key]
        item["count"] += 1
        item["errors"] += int(status_code >= 500)
        item["total_ms"] += duration
        item["max_ms"] = max(item["max_ms"], duration)
        bucket_index = next(
            (
                index
                for index, upper in enumerate(_BUCKETS_MS)
                if duration <= upper
            ),
            len(_BUCKETS_MS),
        )
        item["buckets"][bucket_index] += 1


def _percentile_upper_bound(item: dict[str, Any], percentile: float) -> int | None:
    count = int(item["count"])
    if count <= 0:
        return None
    target = max(1, int((count * percentile) + 0.999999))
    cumulative = 0
    for index, bucket_count in enumerate(item["buckets"]):
        cumulative += bucket_count
        if cumulative >= target:
            return _BUCKETS_MS[index] if index < len(_BUCKETS_MS) else 300_000
    return 300_000


def request_metrics_snapshot() -> dict[str, Any]:
    with _lock:
        copied = {
            key: {
                **value,
                "buckets": list(value["buckets"]),
            }
            for key, value in _requests.items()
        }
    operations = {}
    total_count = 0
    total_errors = 0
    total_duration = 0.0
    for key, item in sorted(copied.items()):
        count = int(item["count"])
        total_count += count
        total_errors += int(item["errors"])
        total_duration += float(item["total_ms"])
        operations[key] = {
            "count": count,
            "server_errors": int(item["errors"]),
            "average_ms": round(float(item["total_ms"]) / count, 1) if count else 0,
            "p95_upper_bound_ms": _percentile_upper_bound(item, 0.95),
            "max_ms": round(float(item["max_ms"]), 1),
        }
    return {
        "request_count": total_count,
        "server_error_count": total_errors,
        "server_error_rate": (
            round(total_errors / total_count, 4) if total_count else 0
        ),
        "average_ms": round(total_duration / total_count, 1) if total_count else 0,
        "operation_count": len(operations),
        "operations": operations,
        "retention": "process_lifetime_aggregate_only",
        "remote_telemetry": False,
    }


def reset_request_metrics_for_test() -> None:
    with _lock:
        _requests.clear()
