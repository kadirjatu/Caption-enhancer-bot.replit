"""
Reusable, provider-independent AI client.

Telegram handlers must NEVER contain AI logic — they should only ever call
`generate_ai_response()` from this module.

    reply = await generate_ai_response(
        user_message=user_message,
        history=history,
        system_prompt=system_prompt,
    )

Works with any OpenAI-compatible Chat Completions endpoint: OpenRouter,
HuggingFace Router, vLLM, RunPod, Ollama, or a local OpenAI-compatible
server. Which provider/model is used is controlled ENTIRELY by the
AI_BASE_URL / AI_API_KEY / AI_MODEL environment variables — no code changes
are ever needed to switch providers or models.

If AI_BASE_URL or AI_MODEL is not set, `generate_ai_response()` returns a
friendly "not configured yet" message immediately, without making any HTTP
request, throwing, or crashing. The rest of the bot keeps working normally.
"""

import time
import logging
import asyncio
from typing import Optional, List, Dict, Any

import httpx

from config import get_ai_config

logger = logging.getLogger("ai_client")

NOT_CONFIGURED_MESSAGE = (
    "🚧 AI Assistant is currently unavailable.\n\n"
    "The bot owner has not deployed the AI model yet.\n"
    "This feature will be available soon.\n\n"
    "Please try again later."
)

GENERIC_ERROR_MESSAGE = (
    "⚠️ AI Assistant is temporarily unavailable. Please try again in a moment."
)

RATE_LIMIT_MESSAGE = (
    "⏳ AI Assistant is a bit busy right now. Please try again shortly."
)

# Reused across calls for connection pooling. Created lazily so importing
# this module never opens a socket or requires AI_* env vars to be set.
_client: Optional[httpx.AsyncClient] = None
_client_lock = asyncio.Lock()


async def _get_http_client(timeout: float) -> httpx.AsyncClient:
    global _client
    async with _client_lock:
        if _client is None or _client.is_closed:
            _client = httpx.AsyncClient(
                timeout=httpx.Timeout(timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            )
        return _client


def _build_messages(
    user_message: str,
    history: Optional[List[Dict[str, str]]],
    system_prompt: Optional[str],
) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if history:
        for turn in history:
            role = turn.get("role")
            content = turn.get("content")
            if role in ("user", "assistant", "system") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _extract_reply_text(payload: Dict[str, Any]) -> Optional[str]:
    try:
        choices = payload.get("choices") or []
        if not choices:
            return None
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
        return None
    except (AttributeError, IndexError, TypeError):
        return None


async def generate_ai_response(
    user_message: str,
    history: Optional[List[Dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
) -> str:
    """Generate an AI chat response. Returns only the generated text (or a
    friendly error/unavailable message) — never raises.

    Args:
        user_message: The latest message from the user.
        history: Optional prior conversation turns, each
            {"role": "user"|"assistant"|"system", "content": str}.
        system_prompt: Optional system prompt to steer the assistant.
    """
    config = get_ai_config()

    if not config.is_configured:
        logger.info("AI request skipped: AI_BASE_URL/AI_MODEL not configured.")
        return NOT_CONFIGURED_MESSAGE

    base_url = config.base_url.rstrip("/")
    url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    body = {
        "model": config.model,
        "messages": _build_messages(user_message, history, system_prompt),
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
    }

    client = await _get_http_client(config.timeout)

    last_error_message = GENERIC_ERROR_MESSAGE
    attempts = max(1, config.max_retries)

    for attempt in range(1, attempts + 1):
        start = time.monotonic()
        try:
            response = await client.post(url, headers=headers, json=body)
            latency_ms = round((time.monotonic() - start) * 1000)
            status = response.status_code

            if status == 200:
                try:
                    payload = response.json()
                except ValueError:
                    logger.error(
                        "AI response was not valid JSON (provider=%s model=%s status=%s)",
                        config.provider, config.model, status,
                    )
                    return GENERIC_ERROR_MESSAGE

                reply = _extract_reply_text(payload)
                usage = payload.get("usage") or {}
                logger.info(
                    "AI request ok (provider=%s model=%s status=%s latency_ms=%s tokens=%s)",
                    config.provider, config.model, status, latency_ms,
                    usage.get("total_tokens", "n/a"),
                )
                if reply:
                    return reply
                logger.error(
                    "AI response had no usable content (provider=%s model=%s)",
                    config.provider, config.model,
                )
                return GENERIC_ERROR_MESSAGE

            # Non-200 responses. Do NOT log the raw response body — it's an
            # untrusted upstream payload that may echo back sensitive request
            # data (e.g. auth context via some proxies); log only metadata.
            logger.error(
                "AI request failed (provider=%s model=%s status=%s latency_ms=%s attempt=%s/%s)",
                config.provider, config.model, status, latency_ms, attempt, attempts,
            )

            if status in (401, 403):
                return "⚠️ AI Assistant is misconfigured (authentication error). Please contact the bot owner."
            if status == 404:
                return "⚠️ AI Assistant model/endpoint not found. Please contact the bot owner."
            if status == 429:
                last_error_message = RATE_LIMIT_MESSAGE
            elif status in (500, 502, 503, 504):
                last_error_message = GENERIC_ERROR_MESSAGE
            else:
                # Other 4xx errors are not worth retrying.
                return GENERIC_ERROR_MESSAGE

        except httpx.TimeoutException:
            latency_ms = round((time.monotonic() - start) * 1000)
            logger.error(
                "AI request timed out (provider=%s model=%s latency_ms=%s attempt=%s/%s)",
                config.provider, config.model, latency_ms, attempt, attempts,
            )
            last_error_message = GENERIC_ERROR_MESSAGE

        except httpx.ConnectError as e:
            logger.error(
                "AI request connection/DNS failure (provider=%s model=%s attempt=%s/%s): %s",
                config.provider, config.model, attempt, attempts, e,
            )
            last_error_message = GENERIC_ERROR_MESSAGE

        except httpx.RequestError as e:
            # Covers SSL errors, network disconnects, and any other transport-level issue.
            logger.error(
                "AI request transport error (provider=%s model=%s attempt=%s/%s): %s",
                config.provider, config.model, attempt, attempts, e,
            )
            last_error_message = GENERIC_ERROR_MESSAGE

        except Exception as e:  # noqa: BLE001 - never let AI failures crash the bot
            logger.exception(
                "Unexpected AI client error (provider=%s model=%s attempt=%s/%s): %s",
                config.provider, config.model, attempt, attempts, e,
            )
            return GENERIC_ERROR_MESSAGE

        if attempt < attempts:
            await asyncio.sleep(min(2 ** (attempt - 1), 8))

    return last_error_message


async def close_ai_client() -> None:
    """Close the pooled HTTP client. Optional — call on process shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
