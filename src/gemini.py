"""LLM client with automatic Gemini -> Groq fallback (no SDKs, just `requests`).

Primary: Google Gemini (free tier). When Gemini's quota is exhausted (HTTP 429),
the client transparently switches to Groq (OpenAI-compatible API) for the rest of
the run, so a spent Gemini quota no longer stalls scoring.

Keys are read from the environment:
- Gemini: GEMINI_API_KEY or gemini_key
- Groq:   GROQ_API_KEY or groq_key

The module keeps its historical name/API (`available`, `generate`,
`generate_json`, `GeminiError`) so callers don't change.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger("llm")

# --- Gemini ---
_GEMINI_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_key") or ""
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
_GEMINI_INTERVAL = float(os.getenv("GEMINI_MIN_INTERVAL", "4.2"))  # ~15 RPM free

# --- Groq (fallback) ---
_GROQ_KEY = os.getenv("GROQ_API_KEY") or os.getenv("groq_key") or ""
# 70b gives noticeably better judgment (esp. seniority/geo nuance) than 8b. Its
# tokens-per-minute limit is tighter, but the retry-after handling below drains
# it reliably. Override with GROQ_MODEL=llama-3.1-8b-instant for more speed.
_GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_INTERVAL = float(os.getenv("GROQ_MIN_INTERVAL", "2.1"))  # ~30 RPM free

# Once Gemini returns a quota error we stop hammering it and use Groq for the
# rest of the process run.
_gemini_exhausted = [False]
_last_call = {"gemini": 0.0, "groq": 0.0}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class GeminiError(RuntimeError):
    """Kept for backward-compat; raised for any LLM failure."""


def available() -> bool:
    return bool(_GEMINI_KEY or _GROQ_KEY)


def active_provider() -> str:
    if _GEMINI_KEY and not _gemini_exhausted[0]:
        return f"gemini:{_GEMINI_MODEL}"
    if _GROQ_KEY:
        return f"groq:{_GROQ_MODEL}"
    return "none"


def _throttle(provider: str, interval: float) -> None:
    elapsed = time.time() - _last_call[provider]
    if elapsed < interval:
        time.sleep(interval - elapsed)
    _last_call[provider] = time.time()


# --- Provider calls ----------------------------------------------------------

def _gemini_call(prompt: str, temperature: float) -> tuple[int, str]:
    """Return (status_code, text). status_code 200 => text is the reply."""
    _throttle("gemini", _GEMINI_INTERVAL)
    url = _GEMINI_ENDPOINT.format(model=_GEMINI_MODEL)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024},
    }
    resp = requests.post(url, params={"key": _GEMINI_KEY}, json=payload, timeout=60)
    if resp.status_code == 200:
        data = resp.json()
        try:
            return 200, data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise GeminiError(f"Unexpected Gemini response: {data}") from exc
    return resp.status_code, resp.text


class _RateLimited(GeminiError):
    def __init__(self, retry_after: float):
        super().__init__(f"Groq rate limited; retry after {retry_after:.1f}s")
        self.retry_after = retry_after


_RETRY_RE = re.compile(r"try again in ([\d.]+)s")


def _groq_call(prompt: str, temperature: float) -> str:
    _throttle("groq", _GROQ_INTERVAL)
    payload = {
        "model": _GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 1024,
    }
    headers = {"Authorization": f"Bearer {_GROQ_KEY}", "Content-Type": "application/json"}
    resp = requests.post(_GROQ_ENDPOINT, json=payload, headers=headers, timeout=60)
    if resp.status_code == 200:
        try:
            return resp.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise GeminiError(f"Unexpected Groq response: {resp.text[:200]}") from exc
    if resp.status_code == 429:
        # Honor the precise wait the API tells us (header or message hint).
        wait = resp.headers.get("retry-after")
        try:
            wait = float(wait) if wait else None
        except ValueError:
            wait = None
        if wait is None:
            m = _RETRY_RE.search(resp.text)
            wait = float(m.group(1)) if m else 5.0
        raise _RateLimited(min(wait + 0.5, 30.0))
    raise GeminiError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")


# --- Public API --------------------------------------------------------------

def generate(prompt: str, *, temperature: float = 0.4, max_retries: int = 3) -> str:
    """Return model text, transparently falling back Gemini -> Groq on quota."""
    if not available():
        raise GeminiError("No LLM key set (GEMINI_API_KEY / gemini_key or GROQ_API_KEY).")

    # If Gemini is already known-exhausted (or absent), go straight to Groq.
    if (_gemini_exhausted[0] or not _GEMINI_KEY) and _GROQ_KEY:
        return _groq_with_retries(prompt, temperature)

    backoff = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            status, text = _gemini_call(prompt, temperature)
        except requests.RequestException as exc:
            log.warning("Gemini network error (attempt %d): %s", attempt, exc)
            if attempt == max_retries:
                if _GROQ_KEY:
                    log.info("Falling back to Groq after Gemini network failure.")
                    return _groq_with_retries(prompt, temperature)
                raise GeminiError(str(exc)) from exc
            time.sleep(backoff); backoff *= 2
            continue

        if status == 200:
            return text

        # Quota exhausted -> switch to Groq for the rest of the run.
        if status == 429:
            if _GROQ_KEY:
                if not _gemini_exhausted[0]:
                    log.warning("Gemini quota exhausted (429) — switching to Groq (%s) for the rest of this run.", _GROQ_MODEL)
                    _gemini_exhausted[0] = True
                return _groq_with_retries(prompt, temperature)
            # No Groq: keep the old backoff-then-raise behaviour.
            if attempt < max_retries:
                log.warning("Gemini 429 — backing off %.1fs (attempt %d)", backoff, attempt)
                time.sleep(backoff); backoff *= 2
                continue
            raise GeminiError(f"Gemini HTTP 429: {text[:300]}")

        # Other transient server errors.
        if status in (500, 503) and attempt < max_retries:
            log.warning("Gemini %d — backing off %.1fs (attempt %d)", status, backoff, attempt)
            time.sleep(backoff); backoff *= 2
            continue

        # Hard error — try Groq once if available, else raise.
        if _GROQ_KEY:
            log.warning("Gemini HTTP %d — falling back to Groq.", status)
            return _groq_with_retries(prompt, temperature)
        raise GeminiError(f"Gemini HTTP {status}: {text[:300]}")

    raise GeminiError("Gemini failed after retries.")


def _groq_with_retries(prompt: str, temperature: float, max_retries: int = 5) -> str:
    backoff = 2.0
    for attempt in range(1, max_retries + 1):
        try:
            return _groq_call(prompt, temperature)
        except _RateLimited as exc:
            if attempt == max_retries:
                raise
            log.warning("Groq rate limited — waiting %.1fs (attempt %d/%d)",
                        exc.retry_after, attempt, max_retries)
            time.sleep(exc.retry_after)
        except GeminiError:
            if attempt == max_retries:
                raise
            time.sleep(backoff); backoff *= 2
        except requests.RequestException as exc:
            if attempt == max_retries:
                raise GeminiError(str(exc)) from exc
            time.sleep(backoff); backoff *= 2
    raise GeminiError("Groq failed after retries.")


def generate_json(prompt: str, *, temperature: float = 0.3) -> dict:
    """Call generate() and parse a JSON object out of the reply (fences tolerated)."""
    for attempt in range(2):
        text = generate(prompt, temperature=temperature)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            cleaned = re.sub(r"```$", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = _JSON_BLOCK_RE.search(cleaned)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        log.warning("LLM returned non-JSON (attempt %d): %.120s", attempt + 1, text)
    raise GeminiError("Could not parse JSON from LLM after retry.")
