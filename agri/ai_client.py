"""Sarvam-105B chat client.

Wraps the Sarvam reasoning-model endpoint with two practical workarounds:

  1. Tier-cap retry — starter tier rejects max_tokens > N with a 400 telling
     us N in the error body. We parse it and re-POST once.
  2. Reasoning-content salvage — sarvam-105b is a CoT reasoning model that
     often spends its full 4096-token budget on reasoning_content and
     returns content="". When that happens we extract the final user-facing
     answer from the reasoning trace so the UI is never empty for a
     successful 200.

All failures are silent: caller gets "" and the system falls back to the
climate-only ranking. Debug info is stashed on st.session_state so it can
be surfaced on demand without spamming the UI.
"""

from __future__ import annotations

import re
from typing import Any

import requests

try:
    import streamlit as st
except ImportError:  # tests / non-Streamlit contexts
    st = None  # type: ignore


SARVAM_URL = "https://api.sarvam.ai/v1/chat/completions"
_DEFAULT_MODEL = "sarvam-105b"
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _api_key() -> str:
    if st is None:
        return ""
    try:
        return str(st.secrets.get("SARVAM_API_KEY", ""))
    except Exception:
        return ""


def _record_ai_debug(payload: dict[str, Any]) -> None:
    if st is None:
        return
    try:
        log = st.session_state.setdefault("_ai_debug", [])
        log.append(payload)
        if len(log) > 20:
            del log[:-20]
    except Exception:
        pass


def _strip_think(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def _extract_user_answer(reasoning: str) -> str:
    """When sarvam-105b exhausts its budget on CoT, the user-facing portion
    is typically the last fenced/JSON block. Try to recover that."""
    if not reasoning:
        return ""
    fence = re.findall(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", reasoning, re.DOTALL)
    if fence:
        return fence[-1].strip()
    blocks = re.findall(r"(\{[^{}]*\}|\[[^\[\]]*\])", reasoning, re.DOTALL)
    if blocks:
        return blocks[-1].strip()
    return ""


def call_ai(prompt: str, system: str = "", max_tokens: int = 4096) -> str:
    """Call Sarvam chat completion using sarvam-105b. Returns "" on any failure."""
    key = _api_key()
    if not key:
        return ""

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    model = _DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "top_p": 1,
    }

    def _post(p: dict[str, Any]) -> requests.Response:
        return requests.post(SARVAM_URL, headers=headers, json=p, timeout=240)

    try:
        r = _post(payload)
        if r.status_code == 400 and "exceeds the maximum allowed" in r.text:
            m = re.search(r"subscription tier \([^)]+\):\s*(\d+)", r.text)
            if m:
                cap = int(m.group(1))
                payload["max_tokens"] = min(max_tokens, cap)
                _record_ai_debug({
                    "model": model, "status": 400,
                    "note": f"max_tokens capped to tier limit {cap}",
                    "body": r.text[:600],
                })
                r = _post(payload)

        debug: dict[str, Any] = {"model": model, "status": r.status_code, "body": r.text[:1200]}

        if r.status_code == 200:
            choices = r.json().get("choices", [])
            if choices:
                ch = choices[0] or {}
                msg = ch.get("message", {}) or {}
                content = str(msg.get("content") or "")
                reasoning = str(msg.get("reasoning_content") or "")
                debug.update({
                    "finish_reason": ch.get("finish_reason"),
                    "content_len": len(content),
                    "reasoning_len": len(reasoning),
                })

                stripped = _strip_think(content)
                if stripped:
                    debug["fallback_used"] = False
                    _record_ai_debug(debug)
                    return stripped

                salvaged = _extract_user_answer(reasoning)
                if salvaged:
                    debug["fallback_used"] = True
                    _record_ai_debug(debug)
                    return salvaged

        _record_ai_debug(debug)
    except requests.exceptions.Timeout:
        _record_ai_debug({"model": model, "error": "Timed out after 240s"})
    except Exception as exc:  # noqa: BLE001 — caller gets "" and falls back
        _record_ai_debug({"model": model, "error": str(exc)})

    return ""
