from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.llm_privacy import (
    HOSTED_DATA_CONSENT_VERSION,
    has_hosted_data_consent,
    record_hosted_data_consent,
)
from app.core.llm_runtime import (
    activate_configuration,
    initialize_active_llm,
    provider_from_config,
)
from app.core.llm_service import StubLLMProvider, call_llm, set_llm_provider
from app.core.llm_providers import OllamaCloudProvider, OllamaLocalProvider, create_provider
from app.models.app_setting import AppSetting
from app.models.llm_config import LLMConfiguration
from tests.license_helpers import install_test_license


def _enable_max(db_session):
    install_test_license(db_session, "max")


def test_hosted_consent_is_versioned_and_local_provider_needs_none():
    hosted = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="gpt-test",
    )
    local = LLMConfiguration(
        provider="ollama_local",
        auth_method="none",
        model="qwen-test",
    )
    assert has_hosted_data_consent(hosted) is False
    assert has_hosted_data_consent(local) is True
    record_hosted_data_consent(hosted, True)
    assert has_hosted_data_consent(hosted) is True
    assert HOSTED_DATA_CONSENT_VERSION in hosted.settings_json


def test_ollama_cloud_cannot_inherit_the_local_privacy_boundary():
    assert OllamaLocalProvider.is_local is True
    assert OllamaCloudProvider.is_local is False


@pytest.mark.parametrize(
    ("provider", "url"),
    [
        ("ollama_local", "https://example.invalid"),
        ("ollama_local", "http://192.0.2.1:11434"),
        ("ollama_cloud", "https://example.invalid"),
    ],
)
def test_ollama_provider_urls_cannot_redirect_financial_prompts(provider, url):
    with pytest.raises(ValueError):
        create_provider(provider=provider, model="synthetic", base_url=url)


def test_ollama_local_accepts_only_loopback_http():
    provider = create_provider(
        provider="ollama_local",
        model="synthetic",
        base_url="http://127.0.0.1:11434",
    )
    assert provider.is_local is True


def test_hosted_configuration_cannot_activate_without_consent():
    config = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="gpt-test",
    )
    with pytest.raises(ValueError, match="data disclosure"):
        activate_configuration(config)


def test_startup_disables_legacy_hosted_configuration_without_consent(db_session):
    config = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="gpt-test",
        is_active=True,
    )
    db_session.add(config)
    db_session.commit()
    set_llm_provider(StubLLMProvider())

    initialized = initialize_active_llm(db_session)

    assert initialized.id == config.id
    assert call_llm("Income Rs 50,000", purpose="report") is None


def test_runtime_provider_inherits_only_a_versioned_consent_record(monkeypatch):
    config = LLMConfiguration(
        provider="openai",
        auth_method="openapi",
        model="gpt-test",
    )
    record_hosted_data_consent(config, True)

    class Provider:
        pass

    monkeypatch.setattr(
        "app.core.llm_runtime.create_provider",
        lambda **_kwargs: Provider(),
    )
    provider = provider_from_config(config)
    assert provider.is_local is False
    assert provider.hosted_data_consent is True


def test_hosted_configuration_api_requires_explicit_consent(
    auth_client,
    db_session,
    monkeypatch,
):
    _enable_max(db_session)
    monkeypatch.setattr(
        "app.api.v1.endpoints.llm.activate_configuration",
        lambda config: config,
    )
    rejected = auth_client.post(
        "/api/v1/llm/config",
        json={
            "provider": "openai",
            "auth_method": "openapi",
            "model": "gpt-test",
            "api_key": "synthetic-test-key",
            "hosted_data_consent": False,
        },
    )
    assert rejected.status_code == 400

    accepted = auth_client.post(
        "/api/v1/llm/config",
        json={
            "provider": "openai",
            "auth_method": "openapi",
            "model": "gpt-test",
            "api_key": "synthetic-test-key",
            "hosted_data_consent": True,
        },
    )
    assert accepted.status_code == 200, accepted.text
    payload = accepted.json()
    assert payload["is_local"] is False
    assert payload["hosted_data_consent"] is True
    assert payload["consent_version"] == HOSTED_DATA_CONSENT_VERSION


def test_local_configuration_api_does_not_require_hosted_consent(
    auth_client,
    db_session,
    monkeypatch,
):
    _enable_max(db_session)
    monkeypatch.setattr(
        "app.api.v1.endpoints.llm.activate_configuration",
        lambda config: config,
    )
    response = auth_client.post(
        "/api/v1/llm/config",
        json={
            "provider": "ollama_local",
            "auth_method": "none",
            "model": "qwen-test",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["is_local"] is True
