"""
LLM Provider implementations for various AI services.
Each provider implements the LLMProvider base class.
"""
from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

import requests

from app.core.llm_service import LLMClassificationResult

logger = logging.getLogger(__name__)


class LLMProvider(ABC):
    """Base class for LLM providers."""

    def __init__(self, model: str, **kwargs):
        self.model = model
        self.config = kwargs

    @abstractmethod
    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        """Call the LLM with a prompt. Returns the response content or None on error."""
        pass

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        """Test if the provider is configured correctly."""
        pass


# ============================================================================
# Ollama Providers
# ============================================================================

class OllamaLocalProvider(LLMProvider):
    """Local Ollama instance."""

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, model: str, base_url: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.base_url = base_url or self.DEFAULT_BASE_URL

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except requests.exceptions.ConnectionError:
            logger.warning("Ollama connection failed")
            return None
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.warning(f"Ollama request failed: {e}")
            return None

    def test_connection(self) -> tuple[bool, str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m["name"] for m in models]
                if self.model in model_names:
                    return True, f"Connected. Model '{self.model}' is available."
                else:
                    return False, f"Connected, but model '{self.model}' not found. Available: {', '.join(model_names[:5])}"
            return False, f"Unexpected response: {response.status_code}"
        except requests.exceptions.ConnectionError:
            return False, "Could not connect to Ollama at " + self.base_url
        except Exception as e:
            return False, str(e)


class OllamaCloudProvider(OllamaLocalProvider):
    """Ollama Cloud API (same interface, different base URL)."""

    DEFAULT_BASE_URL = "https://api.ollama.com"

    def __init__(self, model: str, api_key: Optional[str] = None, base_url: Optional[str] = None, **kwargs):
        # Don't pass base_url to parent - set it directly to avoid conflict
        super().__init__(model, **kwargs)
        # Use explicit class attribute reference to get cloud URL, not parent's localhost
        self.base_url = base_url or OllamaCloudProvider.DEFAULT_BASE_URL
        self.api_key = api_key

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=headers,
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature}
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        """Test connection to Ollama Cloud API."""
        # Ollama Cloud doesn't support /api/tags - use direct generate test
        return self._test_with_generate()

    def _test_with_generate(self) -> tuple[bool, str]:
        """Test connection by attempting a minimal generation."""
        try:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=headers,
                json={
                    "model": self.model,
                    "prompt": "test",
                    "stream": False,
                    "options": {"temperature": 0.1}
                },
                timeout=30
            )

            if response.status_code == 200:
                return True, f"Successfully connected to Ollama Cloud with model '{self.model}'"
            elif response.status_code == 404:
                return False, f"Model '{self.model}' not found in Ollama Cloud"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, f"Connection test failed: {str(e)}"


# ============================================================================
# Anthropic Provider
# ============================================================================

class AnthropicProvider(LLMProvider):
    """Anthropic Claude API."""

    API_BASE = "https://api.anthropic.com/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            content_blocks = data.get("content", [])
            text_content = "\n".join([
                block.get("text", "") for block in content_blocks
                if block.get("type") == "text"
            ])

            return text_content
        except requests.exceptions.HTTPError as e:
            return None
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"

        try:
            # Make a minimal request to test
            response = requests.post(
                f"{self.API_BASE}/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": self.model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "Hi"}]
                },
                timeout=10
            )

            if response.status_code == 200:
                return True, "Successfully connected to Anthropic API"
            elif response.status_code == 401:
                return False, "Invalid API key"
            elif response.status_code == 404:
                return False, f"Model '{self.model}' not found"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================================
# OpenAI Provider
# ============================================================================

class OpenAIProvider(LLMProvider):
    """OpenAI GPT API."""

    API_BASE = "https://api.openai.com/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            if choices:
                content = choices[0].get("message", {}).get("content", "")
            else:
                content = ""

            return content
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return None
            return None
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"

        try:
            response = requests.get(
                f"{self.API_BASE}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )

            if response.status_code == 200:
                return True, "Successfully connected to OpenAI API"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================================
# Google Gemini Provider
# ============================================================================

class GeminiProvider(LLMProvider):
    """Google Gemini API."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("GOOGLE_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/models/{self.model}:generateContent",
                params={"key": self.api_key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                    }
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text = "\n".join([p.get("text", "") for p in parts])
            else:
                text = ""

            return text
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 400 and "API key not valid" in e.response.text:
                return None
            return None
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"

        try:
            # List models to test
            response = requests.get(
                f"{self.API_BASE}/models",
                params={"key": self.api_key},
                timeout=10
            )

            if response.status_code == 200:
                return True, "Successfully connected to Gemini API"
            elif response.status_code == 400:
                return False, "Invalid API key"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================================
# Moonshot (Kimi) Provider
# ============================================================================

class MoonshotProvider(LLMProvider):
    """Moonshot AI (Kimi) API."""

    API_BASE = "https://api.moonshot.cn/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("MOONSHOT_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""

            return content
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"

        try:
            response = requests.get(
                f"{self.API_BASE}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )

            if response.status_code == 200:
                return True, "Successfully connected to Moonshot API"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================================
# Z.AI (GLM) Provider
# ============================================================================

class ZAIProvider(LLMProvider):
    """Z.AI (GLM) API."""

    API_BASE = "https://api.z.ai/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("ZAI_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""

            return content
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"
        return True, "Z.AI provider configured (test not implemented)"


# ============================================================================
# Deepseek Provider
# ============================================================================

class DeepseekProvider(LLMProvider):
    """Deepseek API."""

    API_BASE = "https://api.deepseek.com/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""

            return content
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"

        try:
            response = requests.get(
                f"{self.API_BASE}/models",
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=10
            )

            if response.status_code == 200:
                return True, "Successfully connected to Deepseek API"
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API error: {response.status_code}"
        except Exception as e:
            return False, str(e)


# ============================================================================
# Qwen Provider
# ============================================================================

class QwenProvider(LLMProvider):
    """Qwen (Alibaba) API."""

    API_BASE = "https://dashscope.aliyuncs.com/api/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/services/aigc/text-generation/generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": {"messages": [{"role": "user", "content": prompt}]},
                    "parameters": {"temperature": temperature}
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            output = data.get("output", {})
            if not isinstance(output, dict):
                return None
            text = output.get("text")
            if not isinstance(text, str):
                choices = output.get("choices", [])
                if isinstance(choices, list) and choices:
                    first = choices[0] if isinstance(choices[0], dict) else {}
                    message = first.get("message", {})
                    text = message.get("content") if isinstance(message, dict) else None
            if not isinstance(text, str):
                return None
            text = text.strip()
            return text or None
        except Exception as e:
            logger.warning("Qwen request failed: %s", e)
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"
        return True, "Qwen provider configured (test not implemented)"


# ============================================================================
# Minimax Provider
# ============================================================================

class MinimaxProvider(LLMProvider):
    """Minimax API."""

    API_BASE = "https://api.minimax.chat/v1"

    def __init__(self, model: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.environ.get("MINIMAX_API_KEY")

    def call(self, prompt: str, temperature: float = 0.1) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            response = requests.post(
                f"{self.API_BASE}/text/chatcompletion_v2",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            choices = data.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""

            return content
        except Exception as e:
            return None

    def test_connection(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "No API key configured"
        return True, "Minimax provider configured (test not implemented)"


# ============================================================================
# Provider Factory
# ============================================================================

PROVIDER_MAP = {
    "ollama_local": OllamaLocalProvider,
    "ollama_cloud": OllamaCloudProvider,
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
    "moonshot": MoonshotProvider,
    "zai": ZAIProvider,
    "deepseek": DeepseekProvider,
    "qwen": QwenProvider,
    "minimax": MinimaxProvider,
}


def create_provider(
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """Factory function to create LLM provider instances."""
    provider_class = PROVIDER_MAP.get(provider)
    if not provider_class:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(PROVIDER_MAP.keys())}")

    return provider_class(
        model=model,
        api_key=api_key,
        base_url=base_url,
        **kwargs
    )


def get_available_providers() -> Dict[str, Dict[str, Any]]:
    """Get list of available providers with their supported models."""
    return {
        "ollama_local": {
            "name": "Ollama (Local)",
            "auth_methods": ["none"],
            "requires_auth": False,
            "models": {
                "manual": True,
                "suggestions": [
                    "qwen3:1.7b",
                    "qwen3:4b",
                    "qwen3:8b",
                    "qwen3.6:27b",
                    "qwen3.6:35b-a3b",
                ]
            },
            "description": "Run models locally on your machine"
        },
        "ollama_cloud": {
            "name": "Ollama (Cloud)",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": [
                "glm-5.2:cloud",
                "kimi-k2.6:cloud",
                "minimax-m2.5:cloud",
                "deepseek-v3.2:cloud",
                "qwen3.5:cloud",
            ],
            "description": "Ollama cloud-hosted models"
        },
        "anthropic": {
            "name": "Anthropic",
            "auth_methods": ["oauth", "openapi"],
            "requires_auth": True,
            "models": {
                "top": "claude-opus-4-6-20251101",
                "mid": "claude-sonnet-4-6-20251101",
                "light": "claude-haiku-4-5-20251001",
            },
            "description": "Claude family of models"
        },
        "openai": {
            "name": "OpenAI",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "gpt-4o",
                "mid": "gpt-4.1",
                "light": "gpt-4o-mini",
            },
            "description": "GPT family of models"
        },
        "gemini": {
            "name": "Google Gemini",
            "auth_methods": ["oauth", "openapi"],
            "requires_auth": True,
            "models": {
                "top": "gemini-1.5-pro",
                "mid": "gemini-1.5-flash",
                "light": "gemini-1.0-pro",
            },
            "description": "Google's Gemini models"
        },
        "moonshot": {
            "name": "Kimi (Moonshot)",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "kimi-k2.6",
                "mid": "kimi-k2",
                "light": "kimi-1.5",
            },
            "description": "Moonshot AI's Kimi models"
        },
        "zai": {
            "name": "GLM (Z.AI)",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "glm-5.2",
                "mid": "glm-4",
                "light": "glm-3-turbo",
            },
            "description": "Z.AI's GLM models"
        },
        "deepseek": {
            "name": "Deepseek",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "deepseek-v3.2",
                "mid": "deepseek-v3",
                "light": "deepseek-chat-7b",
            },
            "description": "Deepseek models"
        },
        "qwen": {
            "name": "Qwen",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "qwen-3.5",
                "mid": "qwen-2.5",
                "light": "qwen-2-7b",
            },
            "description": "Alibaba's Qwen models"
        },
        "minimax": {
            "name": "Minimax",
            "auth_methods": ["openapi"],
            "requires_auth": True,
            "models": {
                "top": "minimax-m2.5",
                "mid": "minimax-m2",
                "light": "minimax-m1",
            },
            "description": "Minimax models"
        },
    }
