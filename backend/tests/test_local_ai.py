from __future__ import annotations

import base64
import io
import json
import threading
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import local_ai
from app.core.local_ai import (
    DOWNLOAD_STATE_KEY,
    BUILTIN_MODEL_REGISTRY,
    MINIMUM_REGISTRY_VERSION,
    _load_signed_registry,
    _validated_registry,
    load_model_registry,
    local_model_readiness,
    recommend_model,
    restore_download_status,
    start_model_pull,
    verify_installed_model,
)
from app.models.app_setting import AppSetting


def _write_signed_registry(tmp_path, document):
    registry_path = tmp_path / "registry.json"
    signature_path = tmp_path / "registry.json.sig"
    public_key_path = tmp_path / "public-key.txt"
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    private_key = Ed25519PrivateKey.generate()
    registry_path.write_bytes(payload)
    signature_path.write_text(base64.b64encode(private_key.sign(payload)).decode())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    public_key_path.write_text(base64.b64encode(public_key).decode())
    return registry_path, signature_path, public_key_path


def _registry_document(*, version=MINIMUM_REGISTRY_VERSION, issued_at=None, expires_at=None):
    now = datetime.now(UTC)
    return {
        "schema_version": 1,
        "registry_version": version,
        "issued_at": (issued_at or now - timedelta(days=1)).isoformat(),
        "expires_at": (expires_at or now + timedelta(days=1)).isoformat(),
        "models": BUILTIN_MODEL_REGISTRY,
    }


def test_bundled_registry_signature_and_digests_are_valid(monkeypatch):
    monkeypatch.delenv("GODFIN_MODEL_REGISTRY_PATH", raising=False)
    models, status = load_model_registry()
    assert status["signature_verified"] is True
    assert status["registry_version"] == MINIMUM_REGISTRY_VERSION
    assert models == BUILTIN_MODEL_REGISTRY


def test_registry_requires_an_exact_pinned_digest():
    metadata = {**BUILTIN_MODEL_REGISTRY["qwen3:4b"]}
    metadata.pop("expected_digest")
    with pytest.raises(ValueError, match="missing a pinned digest"):
        _validated_registry({"qwen3:4b": metadata})


def test_invalid_override_signature_fails_closed(tmp_path, monkeypatch):
    registry_path, signature_path, _ = _write_signed_registry(
        tmp_path,
        _registry_document(),
    )
    signature_path.write_text(base64.b64encode(b"x" * 64).decode())
    monkeypatch.setenv("GODFIN_MODEL_REGISTRY_PATH", str(registry_path))
    models, status = load_model_registry()
    assert models == {}
    assert status["signature_verified"] is False
    assert status["source"] == "signed_override"


def test_expired_signed_registry_is_rejected(tmp_path):
    now = datetime.now(UTC)
    paths = _write_signed_registry(
        tmp_path,
        _registry_document(
            issued_at=now - timedelta(days=2),
            expires_at=now - timedelta(days=1),
        ),
    )
    with pytest.raises(ValueError, match="expired"):
        _load_signed_registry(
            paths[0],
            paths[1],
            source="test",
            public_key_path=paths[2],
            now=now,
        )


def test_signed_registry_rollback_is_rejected(tmp_path):
    paths = _write_signed_registry(
        tmp_path,
        _registry_document(version="2026-08-01.9"),
    )
    with pytest.raises(ValueError, match="rollback"):
        _load_signed_registry(
            paths[0],
            paths[1],
            source="test",
            public_key_path=paths[2],
        )


@pytest.mark.parametrize(
    ("ram", "available", "disk", "acceleration", "expected"),
    [
        (6, 4, 100, "cpu", None),
        (8, 6, 100, "cpu", "qwen3:1.7b"),
        (16, 11, 100, "cpu", "qwen3:4b"),
        (24, 18, 100, "apple_metal", "qwen3:8b"),
        (32, 28, 100, "apple_metal", "qwen3.6:27b"),
        (64, 52, 100, "apple_metal", "qwen3.6:35b-a3b"),
    ],
)
def test_model_recommendation_matrix(
    ram,
    available,
    disk,
    acceleration,
    expected,
):
    recommendation = recommend_model(
        ram,
        available,
        disk,
        acceleration,
        BUILTIN_MODEL_REGISTRY,
    )
    assert recommendation["model"] == expected


def test_model_recommendation_respects_disk_headroom():
    recommendation = recommend_model(
        64,
        52,
        1,
        "apple_metal",
        BUILTIN_MODEL_REGISTRY,
    )
    assert recommendation["model"] is None


def test_model_recommendation_requires_measured_os_and_disk_headroom():
    recommendation = recommend_model(
        32,
        27.9,
        100,
        "apple_metal",
        BUILTIN_MODEL_REGISTRY,
    )
    assert recommendation["model"] == "qwen3:8b"
    assert recommendation["required_available_ram_gb"] == 16.0
    assert recommendation["required_disk_free_gb"] > recommendation["size_gb"]


def test_macos_memory_reader_uses_current_vm_counters(monkeypatch):
    responses = {
        ("sysctl", "-n", "hw.memsize"): str(16 * 1024**3),
        ("sysctl", "-n", "hw.pagesize"): "4096",
        ("vm_stat",): (
            "Mach Virtual Memory Statistics: (page size of 4096 bytes)\n"
            "Pages free: 100000.\n"
            "Pages inactive: 200000.\n"
            "Pages speculative: 50000.\n"
            "Pages purgeable: 25000.\n"
        ),
    }
    monkeypatch.setattr(
        local_ai.subprocess,
        "check_output",
        lambda command, **_kwargs: responses[tuple(command)],
    )
    total, available = local_ai._darwin_memory_bytes()
    assert total == 16 * 1024**3
    assert available == 375000 * 4096


def test_runtime_context_is_bounded_by_headroom_and_installed_maximum():
    metadata = BUILTIN_MODEL_REGISTRY["qwen3:4b"]
    assert local_ai._runtime_context_tokens(metadata, 15, 32768) == 8192
    assert local_ai._runtime_context_tokens(metadata, 11, 32768) == 4096
    assert local_ai._runtime_context_tokens(metadata, 9, 1024) == 1024


def test_signed_registry_can_prefer_new_smaller_qwen36():
    registry = {
        **BUILTIN_MODEL_REGISTRY,
        "qwen3.6:4b": {
            "label": "Qwen 3.6 4B",
            "family": "qwen3.6",
            "size_gb": 3,
            "memory_gb": 7,
            "minimum_ram_gb": 12,
            "official": True,
            "validated": True,
        },
    }
    recommendation = recommend_model(16, 12, 100, "apple_metal", registry)
    assert recommendation["model"] == "qwen3.6:4b"


def test_model_download_requires_explicit_approval():
    with pytest.raises(ValueError, match="Explicit download approval"):
        start_model_pull("qwen3:4b", confirmed=False)


def test_model_download_rejects_unverified_variant():
    with pytest.raises(ValueError, match="validated registry"):
        start_model_pull("community:uncensored", confirmed=True)


def test_model_download_reserves_single_flight_before_durable_write(monkeypatch):
    model = "qwen3:4b"
    status = {
        "signature_verified": True,
        "registry_version": MINIMUM_REGISTRY_VERSION,
        "source": "bundled_signed",
        "issued_at": "2026-08-01T00:00:00+00:00",
        "expires_at": "2099-01-01T00:00:00+00:00",
    }
    write_started = threading.Event()
    allow_write = threading.Event()
    errors = []
    original = local_ai.get_download_status()

    def persist(record, *, strict=False):
        if strict:
            write_started.set()
            assert allow_write.wait(timeout=5)

    monkeypatch.setattr(
        local_ai,
        "load_model_registry",
        lambda: (BUILTIN_MODEL_REGISTRY, status),
    )
    monkeypatch.setattr(local_ai.shutil, "which", lambda _name: "/usr/local/bin/ollama")
    monkeypatch.setattr(local_ai, "restore_download_status", lambda _db: {"status": "idle"})
    monkeypatch.setattr(
        local_ai,
        "_system_memory_bytes",
        lambda: (16 * 1024**3, 11 * 1024**3, "test_measured"),
    )
    monkeypatch.setattr(
        local_ai.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": 100 * 1024**3})(),
    )
    monkeypatch.setattr(local_ai, "_ollama_version", lambda _path: "ollama test")
    monkeypatch.setattr(local_ai, "_persist_download_state", persist)
    monkeypatch.setattr(local_ai, "_run_model_pull", lambda *_args: None)

    def first_request():
        try:
            start_model_pull(model, confirmed=True)
        except Exception as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    local_ai._set_download_state(persist=False, status="idle", model=None)
    try:
        first = threading.Thread(target=first_request)
        first.start()
        assert write_started.wait(timeout=5)
        with pytest.raises(local_ai.LocalAIActionConflict):
            start_model_pull(model, confirmed=True)
        allow_write.set()
        first.join(timeout=5)
        assert not first.is_alive()
        assert errors == []
    finally:
        allow_write.set()
        local_ai._set_download_state(persist=False, **original)


def test_installed_model_digest_match_is_accepted(monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    monkeypatch.setattr(local_ai, "_model_digest", lambda _model: expected)
    result = verify_installed_model(model)
    assert result["verified"] is True
    assert result["digest"] == expected
    assert result["removed"] is False


def test_changed_tag_digest_is_removed(monkeypatch):
    model = "qwen3:4b"
    changed = "sha256:" + "0" * 64
    removed = []
    monkeypatch.setattr(local_ai, "_model_digest", lambda _model: changed)
    monkeypatch.setattr(local_ai.shutil, "which", lambda _name: "/usr/local/bin/ollama")
    monkeypatch.setattr(
        local_ai,
        "_remove_untrusted_model",
        lambda executable, model_name: removed.append((executable, model_name)) or True,
    )
    result = verify_installed_model(model, remove_on_mismatch=True)
    assert result["verified"] is False
    assert result["removed"] is True
    assert removed == [("/usr/local/bin/ollama", model)]


class _CompletedPull:
    def __init__(self, output="pulling manifest 50%\nverifying digest 100%\n"):
        self.stdout = io.StringIO(output)

    def wait(self):
        return 0


def _pull_approval(model, expected_digest, *, expires_at=None):
    return {
        "model": model,
        "expected_digest": expected_digest,
        "registry_version": MINIMUM_REGISTRY_VERSION,
        "registry_source": "bundled_signed",
        "issued_at": "2026-08-01T00:00:00+00:00",
        "expires_at": expires_at or "2099-01-01T00:00:00+00:00",
        "approved_at": "2026-08-02T00:00:00+00:00",
        "ollama_version": "ollama version test",
    }


def test_completed_pull_accepts_and_persists_only_the_pinned_digest(monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    persisted = []
    original = local_ai.get_download_status()
    monkeypatch.setattr(
        local_ai.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _CompletedPull(),
    )
    monkeypatch.setattr(local_ai, "_model_digest", lambda _model: expected)
    monkeypatch.setattr(local_ai, "_persist_model_acceptance", persisted.append)
    local_ai._set_download_state(status="downloading", model=model)
    try:
        local_ai._run_model_pull(
            "/usr/local/bin/ollama",
            model,
            _pull_approval(model, expected),
        )
        status = local_ai.get_download_status()
    finally:
        local_ai._set_download_state(**original)

    assert status["status"] == "complete"
    assert status["digest_verified"] is True
    assert status["digest"] == expected
    assert persisted[0]["digest"] == expected
    assert persisted[0]["accepted_at"]


@pytest.mark.parametrize(
    ("actual_digest", "expires_at", "should_remove"),
    [
        ("sha256:" + "0" * 64, "2099-01-01T00:00:00+00:00", True),
        (
            BUILTIN_MODEL_REGISTRY["qwen3:4b"]["expected_digest"],
            "2000-01-01T00:00:00+00:00",
            True,
        ),
        (None, "2099-01-01T00:00:00+00:00", False),
    ],
)
def test_completed_pull_fails_closed_without_current_exact_digest(
    monkeypatch,
    actual_digest,
    expires_at,
    should_remove,
):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    removed = []
    persisted = []
    original = local_ai.get_download_status()
    monkeypatch.setattr(
        local_ai.subprocess,
        "Popen",
        lambda *_args, **_kwargs: _CompletedPull(),
    )
    monkeypatch.setattr(local_ai, "_model_digest", lambda _model: actual_digest)
    monkeypatch.setattr(
        local_ai,
        "_remove_untrusted_model",
        lambda executable, model_name: removed.append((executable, model_name)) or True,
    )
    monkeypatch.setattr(local_ai, "_persist_model_acceptance", persisted.append)
    local_ai._set_download_state(status="downloading", model=model)
    try:
        local_ai._run_model_pull(
            "/usr/local/bin/ollama",
            model,
            _pull_approval(model, expected, expires_at=expires_at),
        )
        status = local_ai.get_download_status()
    finally:
        local_ai._set_download_state(**original)

    assert status["status"] == "failed"
    assert status["digest_verified"] is False
    assert persisted == []
    assert bool(removed) is should_remove


def test_restart_reverifies_persisted_acceptance(db_session, monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    record = {
        "model": model,
        "digest": expected,
        "expected_digest": expected,
        "registry_version": MINIMUM_REGISTRY_VERSION,
        "registry_source": "bundled_signed",
        "ollama_version": "ollama version 1.2.3",
        "approved_at": "2026-08-01T10:00:00+00:00",
        "accepted_at": "2026-08-01T10:05:00+00:00",
        "signature_verified": True,
    }
    db_session.add(
        AppSetting(
            key=f"local_ai_acceptance:{model}",
            value=json.dumps(record),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": True,
            "model": model,
            "digest": expected,
            "expected_digest": expected,
            "registry": {"signature_verified": True},
        },
    )
    original = local_ai.get_download_status()
    local_ai._set_download_state(
        status="idle",
        model=None,
        progress=0,
        message="No model download is running.",
        digest=None,
        digest_verified=False,
        signature_verified=False,
    )
    try:
        restored = restore_download_status(db_session)
    finally:
        local_ai._set_download_state(**original)
    assert restored["status"] == "complete"
    assert restored["digest_verified"] is True
    assert restored["registry_version"] == MINIMUM_REGISTRY_VERSION


def test_restart_rejects_a_changed_installed_digest(db_session, monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    db_session.add(
        AppSetting(
            key=f"local_ai_acceptance:{model}",
            value=json.dumps(
                {
                    "model": model,
                    "accepted_at": "2026-08-01T10:05:00+00:00",
                    "expected_digest": expected,
                }
            ),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": False,
            "model": model,
            "digest": "sha256:" + "0" * 64,
            "expected_digest": expected,
            "message": "Installed model digest changed and was removed.",
            "registry": {"signature_verified": True},
        },
    )
    original = local_ai.get_download_status()
    local_ai._set_download_state(
        status="idle",
        model=None,
        progress=0,
        message="No model download is running.",
        digest=None,
        digest_verified=False,
        signature_verified=False,
    )
    try:
        restored = restore_download_status(db_session)
    finally:
        local_ai._set_download_state(**original)
    assert restored["status"] == "failed"
    assert restored["digest_verified"] is False


def test_restart_surfaces_a_missing_or_unreadable_model(db_session, monkeypatch):
    model = "qwen3:4b"
    db_session.add(
        AppSetting(
            key=f"local_ai_acceptance:{model}",
            value=json.dumps(
                {
                    "model": model,
                    "accepted_at": "2026-08-01T10:05:00+00:00",
                }
            ),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": False,
            "model": model,
            "digest": None,
            "message": "The installed model digest could not be read.",
            "registry": {"signature_verified": True},
        },
    )
    original = local_ai.get_download_status()
    local_ai._set_download_state(status="idle", digest_verified=False)
    try:
        restored = restore_download_status(db_session)
    finally:
        local_ai._set_download_state(**original)
    assert restored["status"] == "failed"
    assert "could not be read" in restored["message"]


def test_restart_reconciles_a_durable_interrupted_pull(db_session, monkeypatch):
    model = "qwen3:4b"
    db_session.add(
        AppSetting(
            key=DOWNLOAD_STATE_KEY,
            value=json.dumps(
                {
                    "status": "downloading",
                    "model": model,
                    "progress": 41,
                    "pid": 12345,
                    "job_id": "00000000-0000-4000-8000-000000000001",
                }
            ),
        )
    )
    db_session.commit()
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": False,
            "model": model,
            "digest": None,
            "registry": {"signature_verified": True},
        },
    )
    terminated = []
    monkeypatch.setattr(
        local_ai,
        "_terminate_persisted_process",
        lambda record: terminated.append(record["pid"]) or True,
    )
    monkeypatch.setattr(local_ai, "_persist_download_state", lambda *_args, **_kwargs: None)
    original = local_ai.get_download_status()
    local_ai._set_download_state(persist=False, status="idle", model=None)
    try:
        restored = restore_download_status(db_session)
    finally:
        local_ai._set_download_state(persist=False, **original)
    assert restored["status"] == "interrupted"
    assert restored["progress"] == 41
    assert restored["retryable"] is True
    assert restored["orphan_process_terminated"] is True
    assert terminated == [12345]


def test_recent_exact_benchmark_is_required_for_activation(monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": True,
            "model": model,
            "digest": expected,
        },
    )
    monkeypatch.setattr(
        local_ai,
        "_load_benchmark_record",
        lambda *_args, **_kwargs: {
            "success": True,
            "digest": expected,
            "tokens_per_second": 7.5,
            "context_tokens": 4096,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    readiness = local_model_readiness(
        model,
        total_ram_gb=16,
        available_ram_gb=11,
        disk_free_gb=100,
    )
    assert readiness["ready"] is True
    assert readiness["benchmark"]["tokens_per_second"] == 7.5


def test_changed_digest_invalidates_a_previous_benchmark(monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": True,
            "model": model,
            "digest": expected,
        },
    )
    monkeypatch.setattr(
        local_ai,
        "_load_benchmark_record",
        lambda *_args, **_kwargs: {
            "success": True,
            "digest": "sha256:" + "0" * 64,
            "tokens_per_second": 8,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )
    readiness = local_model_readiness(
        model,
        total_ram_gb=16,
        available_ram_gb=11,
        disk_free_gb=100,
    )
    assert readiness == {
        "ready": False,
        "reason": "benchmark_digest_stale",
        "required_available_ram_gb": 9.0,
        "required_disk_free_gb": 5.0,
        "os_headroom_gb": 2.0,
    }


def test_benchmark_uses_bounded_context_and_persists_activation_evidence(monkeypatch):
    model = "qwen3:4b"
    expected = BUILTIN_MODEL_REGISTRY[model]["expected_digest"]
    requests = []
    stored = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "response": "Savings rate compares verified income and spending.",
                "eval_count": 20,
                "eval_duration": 2_000_000_000,
            }

    monkeypatch.setattr(
        local_ai,
        "verify_installed_model",
        lambda *_args, **_kwargs: {
            "verified": True,
            "model": model,
            "digest": expected,
        },
    )
    monkeypatch.setattr(
        local_ai,
        "_system_memory_bytes",
        lambda: (16 * 1024**3, 11 * 1024**3, "test_measured"),
    )
    monkeypatch.setattr(
        local_ai.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": 100 * 1024**3})(),
    )
    monkeypatch.setattr(
        local_ai,
        "_ollama_model_metadata",
        lambda _model: {"maximum_context_tokens": 4096},
    )
    monkeypatch.setattr(
        local_ai.httpx,
        "post",
        lambda *args, **kwargs: requests.append((args, kwargs)) or Response(),
    )
    monkeypatch.setattr(
        local_ai,
        "_write_json_setting",
        lambda key, record: stored.append((key, record)),
    )
    result = local_ai.benchmark_model(model)
    assert result["success"] is True
    assert result["activation_ready"] is True
    assert result["context_tokens"] == 4096
    assert requests[0][1]["json"]["options"]["num_ctx"] == 4096
    assert stored[0][0] == "local_ai_benchmark:qwen3:4b"
    assert stored[0][1]["digest"] == expected


def test_local_ai_choice_is_persisted(auth_client):
    response = auth_client.put(
        "/api/v1/system/local-ai/choice",
        json={"choice": "none"},
    )
    assert response.status_code == 200
    assert response.json() == {"choice": "none"}

    response = auth_client.put(
        "/api/v1/system/local-ai/choice",
        json={"choice": "anything"},
    )
    assert response.status_code == 422


def test_local_ai_download_requires_confirmation(auth_client):
    response = auth_client.post(
        "/api/v1/system/local-ai/download",
        json={"model": "qwen3:4b", "confirmed": False},
    )
    assert response.status_code == 422


def test_local_ai_benchmark_allows_only_one_active_run():
    from app.core import local_ai

    assert local_ai._benchmark_lock.acquire(blocking=False) is True
    try:
        with pytest.raises(RuntimeError, match="already running"):
            local_ai.benchmark_model("qwen3:4b")
    finally:
        local_ai._benchmark_lock.release()


def test_local_ai_download_worker_does_not_surface_raw_errors(monkeypatch):
    from app.core import local_ai

    original = local_ai.get_download_status()
    monkeypatch.setattr(
        local_ai.subprocess,
        "Popen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("/Users/private/financial/ollama")
        ),
    )
    try:
        local_ai._run_model_pull("/private/bin/ollama", "qwen3:4b", {})
        status = local_ai.get_download_status()
        assert status["status"] == "failed"
        assert status["message"].startswith("Local model setup could not finish")
        assert "/Users/" not in status["message"]
        assert "/private/" not in status["message"]
    finally:
        local_ai._set_download_state(**original)
