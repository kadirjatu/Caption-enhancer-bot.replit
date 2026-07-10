"""
Reusable AI configuration module.

Reads AI provider settings ONLY from environment variables (.env).
No other module should read AI_* variables directly — always go through
this module so there is a single source of truth.

To switch AI providers/models later (OpenRouter, HuggingFace Router, vLLM,
RunPod, Ollama, or any other OpenAI-compatible server), change the .env
values only. No Python code needs to change.
"""

import os
import logging

logger = logging.getLogger("ai_config")


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float for %s=%r, using default %s", name, value, default)
        return default


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid int for %s=%r, using default %s", name, value, default)
        return default


class AIConfig:
    """Snapshot of AI-related environment variables, read once at access time."""

    def __init__(self):
        self.base_url = (os.getenv("AI_BASE_URL") or "").strip()
        self.api_key = (os.getenv("AI_API_KEY") or "").strip()
        self.model = (os.getenv("AI_MODEL") or "").strip()

        self.timeout = _get_float("AI_TIMEOUT", 120.0)
        self.max_retries = _get_int("AI_MAX_RETRIES", 3)
        self.temperature = _get_float("AI_TEMPERATURE", 0.7)
        self.top_p = _get_float("AI_TOP_P", 0.9)
        self.max_tokens = _get_int("AI_MAX_TOKENS", 2048)

    @property
    def is_configured(self) -> bool:
        """AI is usable only when both AI_BASE_URL and AI_MODEL are set.
        AI_API_KEY is optional (many local/self-hosted servers don't need one)."""
        return bool(self.base_url) and bool(self.model)

    @property
    def provider(self) -> str:
        """Best-effort provider name, detected only from AI_BASE_URL, for logging."""
        url = self.base_url.lower()
        if not url:
            return "unconfigured"
        if "openrouter" in url:
            return "openrouter"
        if "huggingface" in url or "hf.co" in url:
            return "huggingface"
        if "runpod" in url:
            return "runpod"
        if "ollama" in url or ":11434" in url:
            return "ollama"
        if "localhost" in url or "127.0.0.1" in url:
            return "local"
        return "openai-compatible"


def get_ai_config() -> AIConfig:
    """Return a fresh AIConfig snapshot read from the current environment.

    Called fresh each time (rather than cached at import time) so that
    updating .env + restarting the process is always enough to pick up
    changes — no code changes required.
    """
    return AIConfig()
