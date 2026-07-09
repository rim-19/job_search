"""Tiny Gemini REST client (no SDK — just `requests`).

Reads the API key from the environment. The user's .env uses `gemini_key`; the
plan/README use `GEMINI_API_KEY`. We accept either so both work.

Model is configurable via GEMINI_MODEL (default: gemini-2.0-flash, which is on
the free tier). We call the REST endpoint directly for resilience against SDK
version churn.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time

import requests

log = logging.getLogger("gemini")

_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("gemini_key") or ""
# gemini-2.5-flash-lite has the most generous free-tier limits available on this
# key (others return 429 once their small daily quota is spent).
_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# Free tier is ~15 requests/min; space calls ~4s apart to stay under it.
_MIN_INTERVAL = float(os.getenv("GEMINI_MIN_INTERVAL", "4.2"))
_last_call = [0.0]

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class GeminiError(RuntimeError):
    pass


def available() -> bool:
    return bool(_KEY)


def _throttle() -> None:
    elapsed = time.time() - _last_call[0]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call[0] = time.time()


def generate(prompt: str, *, temperature: float = 0.4, max_retries: int = 3) -> str:
    """Return raw model text for a prompt. Retries on 429/5xx with backoff."""
    if not _KEY:
        raise GeminiError("No Gemini API key set (GEMINI_API_KEY or gemini_key).")

    url = _ENDPOINT.format(model=_MODEL)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 1024},
    }
    params = {"key": _KEY}

    backoff = 2.0
    for attempt in range(1, max_retries + 1):
        _throttle()
        try:
            resp = requests.post(url, params=params, json=payload, timeout=60)
        except requests.RequestException as exc:
            log.warning("Gemini network error (attempt %d): %s", attempt, exc)
            if attempt == max_retries:
                raise GeminiError(str(exc)) from exc
            time.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code == 200:
            data = resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as exc:
                raise GeminiError(f"Unexpected Gemini response: {data}") from exc

        if resp.status_code in (429, 500, 503) and attempt < max_retries:
            log.warning("Gemini %d — backing off %.1fs (attempt %d)",
                        resp.status_code, backoff, attempt)
            time.sleep(backoff)
            backoff *= 2
            continue

        raise GeminiError(f"Gemini HTTP {resp.status_code}: {resp.text[:300]}")

    raise GeminiError("Gemini failed after retries.")


def generate_json(prompt: str, *, temperature: float = 0.3) -> dict:
    """Call generate() and parse a JSON object out of the reply.

    Handles ```json fenced blocks and stray prose around the object. Retries the
    whole call once if the first reply can't be parsed, then raises.
    """
    for attempt in range(2):
        text = generate(prompt, temperature=temperature)
        cleaned = text.strip()
        # Strip markdown fences if present.
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
        log.warning("Gemini returned non-JSON (attempt %d): %.120s", attempt + 1, text)
    raise GeminiError("Could not parse JSON from Gemini after retry.")
