import os
from typing import Dict, List, Optional

from ..config import ENV_KEY_BY_PROVIDER
from .anthropic import AnthropicProvider
from .base import ModelProvider
from .gemini import GeminiProvider
from .openai_compatible import openai_provider, openrouter_provider, tinker_provider


PROVIDER_DETAILS = {
    "openai": {
        "label": "OpenAI",
        "default_model": os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        "capabilities": ["generate", "stream_generate", "generate_structured", "tool_call"],
    },
    "anthropic": {
        "label": "Claude",
        "default_model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
        "capabilities": ["generate", "stream_generate", "generate_structured", "tool_call"],
    },
    "gemini": {
        "label": "Gemini",
        "default_model": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "capabilities": ["generate", "stream_generate", "generate_structured", "embed", "tool_call"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "default_model": os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini"),
        "capabilities": ["generate", "stream_generate", "generate_structured", "logprobs", "tool_call"],
    },
    "tinker": {
        "label": "Tinker",
        "default_model": os.getenv("TINKER_MODEL", None),
        "capabilities": ["generate", "stream_generate", "generate_structured", "logprobs", "causal_probe"],
    },
}


def build_provider(provider: str, api_key: str) -> ModelProvider:
    if provider == "openai":
        return openai_provider(api_key)
    if provider == "anthropic":
        return AnthropicProvider(api_key)
    if provider == "gemini":
        return GeminiProvider(api_key)
    if provider == "openrouter":
        return openrouter_provider(api_key)
    if provider == "tinker":
        return tinker_provider(api_key)
    raise ValueError("unsupported provider")


def list_provider_metadata(saved_providers: List[str], env_key_providers: Optional[List[str]] = None) -> List[Dict[str, object]]:
    env_key_providers = env_key_providers or []
    rows: List[Dict[str, object]] = [
        {
            "provider": "preview",
            "label": "Preview Engine",
            "default_model": None,
            "key_env_var": None,
            "key_state": "not_required",
            "capabilities": ["generate", "report"],
        }
    ]
    for provider, details in PROVIDER_DETAILS.items():
        if provider in saved_providers:
            state = "saved"
        elif provider in env_key_providers:
            state = "env"
        else:
            state = "missing"
        rows.append(
            {
                "provider": provider,
                "label": details["label"],
                "default_model": details["default_model"],
                "key_env_var": ENV_KEY_BY_PROVIDER.get(provider),
                "key_state": state,
                "capabilities": details["capabilities"],
            }
        )
    return rows
