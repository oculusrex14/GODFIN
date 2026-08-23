from __future__ import annotations

import json

import pytest
import requests

from app.core import llm_runtime
from app.core.llm_privacy import record_hosted_data_consent
from app.core.llm_providers import (
    LLMProviderProbeError,
    PROVIDER_SMOKE_PROMPT,
    probe_selected_model,
)
from app.models.llm_config import LLMConfiguration
from tests.license_helpers import install_test_license


class ProbeProvider:
    is_local = False
    hosted_data_consent = True

    def __init__(self, response="GODFIN ready", error: Exception | None = None):
        self.response = response
        self.error = error
        self.prompts: list[tuple[str, float]] = []

    def call(self, prompt: str, temperature: float = 0.1):
        self.prompts.append((prompt, temperature))
        if self.error:
            raise self.error
        return self.response


def test_provider_probe_uses_only_fixed_synthetic_text():
    provider = ProbeProvider()

    result = probe_selected_model(provider)

    assert result.success is True
    assert result.error_code is None
    assert provider.prompts == [(PROVIDER_SMOKE_PROMPT, 0.0)]
    assert "transaction" not in PROVIDER_SMOKE_PROMPT.lower()
    assert result.latency_bucket in {
        "under_1s",
        "1_to_5s",
        "5_to_15s",
        "15s_or_more",
    }


@pytest.mark.parametrize(
    ("response", "error", "expected_code"),
    [
        (None, None, "no_response"),
        ("   ", None, "empty_response"),
        ({"text": "wrong type"}, None, "malformed_response"),
        (None, requests.Timeout("private-provider-detail"), "timeout"),
        (None, requests.ConnectionError("private-provider-detail"), "provider_unreachable"),
        (None, RuntimeError("private-provider-detail"), "provider_error"),
    ],
)
def test_provider_probe_normalizes_failures(response, error, expected_code):
    result = probe_selected_model(ProbeProvider(response=response, error=error))

    assert result.success is False
    assert result.error_code == expected_code
    assert "private-provider-detail" not in str(result)


def _hosted_config() -> LLMConfiguration:
    config = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="synthetic-model",
        api_key="encrypted-test-key",
        is_active=True,
    )
    record_hosted_data_consent(config, True)
    return config


def test_activation_records_exact_model_probe_before_swapping_provider(monkeypatch):
    config = _hosted_config()
    provider = ProbeProvider()
    activated = []
    monkeypatch.setattr(llm_runtime, "provider_from_config", lambda _config: provider)
    monkeypatch.setattr(llm_runtime, "set_llm_provider", activated.append)

    assert llm_runtime.activate_configuration(config) is provider

    assert activated == [provider]
    settings = json.loads(config.settings_json)
    probe = settings["last_model_probe"]
    assert probe["provider"] == "openai"
    assert probe["model"] == "synthetic-model"
    assert probe["success"] is True
    assert probe["error_code"] is None
    assert probe["tested_at"]
    assert settings["hosted_data_consent"]["accepted"] is True


def test_failed_activation_keeps_current_runtime_provider(monkeypatch):
    config = _hosted_config()
    candidate = ProbeProvider(response=None)
    activated = []
    monkeypatch.setattr(llm_runtime, "provider_from_config", lambda _config: candidate)
    monkeypatch.setattr(llm_runtime, "set_llm_provider", activated.append)

    with pytest.raises(LLMProviderProbeError) as error:
        llm_runtime.activate_configuration(config)

    assert error.value.code == "no_response"
    assert activated == []
    probe = json.loads(config.settings_json)["last_model_probe"]
    assert probe["success"] is False
    assert probe["error_code"] == "no_response"


def test_startup_can_reuse_previously_accepted_provider_without_network_probe(
    monkeypatch,
):
    config = _hosted_config()
    provider = ProbeProvider(error=AssertionError("startup must not call provider"))
    activated = []
    monkeypatch.setattr(llm_runtime, "provider_from_config", lambda _config: provider)
    monkeypatch.setattr(llm_runtime, "set_llm_provider", activated.append)

    assert (
        llm_runtime.activate_configuration(config, verify_selected_model=False)
        is provider
    )
    assert provider.prompts == []
    assert activated == [provider]


def test_failed_candidate_keeps_previous_database_configuration_active(
    auth_client,
    db_session,
    monkeypatch,
):
    install_test_license(db_session, "max")
    previous = _hosted_config()
    previous.model = "previous-working-model"
    db_session.add(previous)
    db_session.commit()
    activated = []
    monkeypatch.setattr(
        llm_runtime,
        "provider_from_config",
        lambda _config: ProbeProvider(response=None),
    )
    monkeypatch.setattr(llm_runtime, "set_llm_provider", activated.append)

    response = auth_client.post(
        "/api/v1/llm/config",
        json={
            "provider": "openai",
            "auth_method": "openapi",
            "model": "candidate-model",
            "api_key": "synthetic-test-key",
            "hosted_data_consent": True,
        },
    )

    assert response.status_code == 502
    assert response.json()["code"] == "LLM_MODEL_PROBE_FAILED"
    assert "synthetic-test-key" not in response.text
    assert activated == []
    db_session.expire_all()
    configs = db_session.query(LLMConfiguration).all()
    assert [(item.model, item.is_active) for item in configs] == [
        ("previous-working-model", True)
    ]
