from __future__ import annotations

import pytest

from app.core.local_ai import (
    BUILTIN_MODEL_REGISTRY,
    recommend_model,
    start_model_pull,
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
