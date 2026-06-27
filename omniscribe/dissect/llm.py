"""Multi-provider LLM layer for content extraction.

A resilient fallback chain so the Dissect engine produces high-quality study materials
regardless of which (if any) API the user has configured:

    1. Gemini        (GEMINI_API_KEY / GOOGLE_API_KEY)      - free tier, high quality
    2. Anthropic     (ANTHROPIC_API_KEY)                    - via SDK
    3. Groq          (GROQ_API_KEY)                         - OpenAI-compatible, fast & free
    4. OpenAI        (OPENAI_API_KEY [+ OPENAI_BASE_URL])   - OpenAI-compatible
    5. OpenRouter    (OPENROUTER_API_KEY)                   - many free models
    6. Pollinations  (no key required)                      - keyless free fallback
    -> if every provider fails, the caller uses the offline heuristic extractor.

Each provider returns raw model text; the caller parses + normalises it. Providers that
fail permanently (auth/billing/quota/unknown-model) are disabled for the process so we
don't waste time retrying them on every request.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

from .. import config

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OmniScribe/1.0"


class LLMUnavailable(Exception):
    """Provider is not configured — skip it silently."""


class LLMCallError(Exception):
    """Provider is configured but the call failed."""

    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


# --------------------------------------------------------------------------- http
def _http_json(url: str, payload: dict, headers: dict, timeout: int | None = None) -> dict:
    timeout = timeout or config.LLM_TIMEOUT
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "ignore"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:300]
        except Exception:
            pass
        permanent = e.code in (401, 402, 403, 404) or "credit" in body.lower() or "quota" in body.lower()
        raise LLMCallError(f"HTTP {e.code}: {body}", permanent=permanent)
    except Exception as e:
        raise LLMCallError(f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- providers
class Provider:
    name = "base"
    needs_key = True

    def configured(self) -> bool:
        raise NotImplementedError

    def complete(self, system: str, user: str, max_tokens: int) -> str:
        raise NotImplementedError


class GeminiProvider(Provider):
    name = "gemini"

    def _key(self):
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    def configured(self) -> bool:
        return bool(self._key())

    def complete(self, system, user, max_tokens):
        model = config.GEMINI_MODEL
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
               f"?key={self._key()}")
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.4,
                                 "responseMimeType": "application/json"},
        }
        data = _http_json(url, payload, headers={})
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise LLMCallError(f"Unexpected Gemini response: {str(data)[:200]}")


class AnthropicProvider(Provider):
    name = "anthropic"

    def configured(self) -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY"))

    def complete(self, system, user, max_tokens):
        import anthropic

        try:
            client = anthropic.Anthropic(max_retries=0)  # fail fast; chain handles fallback
            msg = client.messages.create(
                model=config.ANTHROPIC_MODEL, max_tokens=max_tokens,
                system=system, messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        except Exception as e:
            txt = str(e).lower()
            permanent = any(k in txt for k in ("credit", "authentication", "401", "403", "permission", "not_found"))
            raise LLMCallError(f"{type(e).__name__}: {e}", permanent=permanent)


class _OpenAICompatible(Provider):
    """Generic OpenAI-compatible chat-completions provider."""
    name = "openai-compatible"
    env_key = "OPENAI_API_KEY"
    base_url = "https://api.openai.com/v1"
    model = "gpt-4o-mini"
    extra_headers: dict = {}

    def _key(self):
        return os.environ.get(self.env_key)

    def configured(self) -> bool:
        return bool(self._key())

    def complete(self, system, user, max_tokens):
        url = self.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        headers = {"Authorization": f"Bearer {self._key()}", **self.extra_headers}
        data = _http_json(url, payload, headers=headers)
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raise LLMCallError(f"Unexpected response: {str(data)[:200]}")


class GroqProvider(_OpenAICompatible):
    name = "groq"
    env_key = "GROQ_API_KEY"
    base_url = "https://api.groq.com/openai/v1"

    @property
    def model(self):  # type: ignore[override]
        return config.GROQ_MODEL


class OpenAIProvider(_OpenAICompatible):
    name = "openai"
    env_key = "OPENAI_API_KEY"

    @property
    def base_url(self):  # type: ignore[override]
        return os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")

    @property
    def model(self):  # type: ignore[override]
        return os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


class OpenRouterProvider(_OpenAICompatible):
    name = "openrouter"
    env_key = "OPENROUTER_API_KEY"
    base_url = "https://openrouter.ai/api/v1"
    extra_headers = {"HTTP-Referer": "https://omniscribe.local", "X-Title": "OmniScribe"}

    @property
    def model(self):  # type: ignore[override]
        return config.OPENROUTER_MODEL


class PollinationsProvider(Provider):
    """Keyless free provider — the default when no API key is configured."""
    name = "pollinations"
    needs_key = False

    def configured(self) -> bool:
        return config.POLLINATIONS_ENABLED

    def complete(self, system, user, max_tokens):
        payload = {
            "model": config.POLLINATIONS_MODEL,
            "referrer": "omniscribe",
            "jsonMode": True,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        data = _http_json("https://text.pollinations.ai/openai", payload, headers={})
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            # Some responses come back as a bare string.
            if isinstance(data, str):
                return data
            raise LLMCallError(f"Unexpected Pollinations response: {str(data)[:200]}")


# Priority order: keyed/high-quality first, keyless free last.
_REGISTRY = [
    GeminiProvider(), AnthropicProvider(), GroqProvider(),
    OpenAIProvider(), OpenRouterProvider(), PollinationsProvider(),
]
_DISABLED: set[str] = set()
_PREFERRED: list[str] = []  # provider names that have succeeded, tried first next time


def _ordered() -> list[Provider]:
    pref = [p for name in _PREFERRED for p in _REGISTRY if p.name == name]
    rest = [p for p in _REGISTRY if p.name not in _PREFERRED]
    return pref + rest


def available_providers() -> list[str]:
    return [p.name for p in _REGISTRY if p.configured() and p.name not in _DISABLED]


def primary_provider() -> str | None:
    avail = available_providers()
    return avail[0] if avail else None


def complete(system: str, user: str, max_tokens: int = None) -> tuple[str, str]:
    """Try each configured provider (with retries for transient errors); return (text, name)."""
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    errors = []
    for p in _ordered():
        if p.name in _DISABLED or not p.configured():
            continue
        # Keyless free providers are flakier (rate limits, connection resets) -> retry more.
        attempts = 3 if not p.needs_key else 2
        for a in range(attempts):
            try:
                text = p.complete(system, user, max_tokens)
                if not text or not text.strip():
                    raise LLMCallError("empty response")
                if p.name in _PREFERRED:
                    _PREFERRED.remove(p.name)
                _PREFERRED.insert(0, p.name)
                return text, p.name
            except LLMCallError as e:
                errors.append(f"{p.name}: {e}")
                if e.permanent:
                    _DISABLED.add(p.name)
                    break
                if a < attempts - 1:
                    time.sleep(1.5 * (a + 1))  # backoff before retrying this provider
                    continue
                break
            except Exception as e:  # defensive — never let a provider crash the chain
                errors.append(f"{p.name}: {type(e).__name__}: {e}")
                break
    raise LLMCallError("all providers failed -> " + " | ".join(errors[-4:]))
