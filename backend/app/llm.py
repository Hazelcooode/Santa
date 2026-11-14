"""Optional language model (Gemini REST) for casual chat wording, request parsing
and on-request image feature extraction. It is never a search source: facts,
prices and links come from Exa. Every caller has a deterministic fallback, so
the backend works with no model key."""
import base64
import json
import logging
import re

import httpx

from .config import settings

log = logging.getLogger("taimi.llm")


def available():
    return bool(settings.gemini_api_key)


def complete(system, turns, want_json=False, image_data_url=None, max_tokens=400, temperature=0.8):
    """turns: [(role, text)] with role in user|model. Returns str/dict or None on any failure."""
    if not available():
        return None
    contents = []
    for role, text in turns[-12:]:
        contents.append({"role": "model" if role in ("model", "bot", "assistant") else "user", "parts": [{"text": text[:2000]}]})
    if image_data_url and contents:
        m = re.match(r"data:(image/[\w.+-]+);base64,(.+)", image_data_url, re.S)
        if m:
            try:
                base64.b64decode(m.group(2)[:64] + "==", validate=False)
                contents[-1]["parts"].append({"inline_data": {"mime_type": m.group(1), "data": m.group(2)}})
            except ValueError:
                pass
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
    }
    if want_json:
        body["generationConfig"]["responseMimeType"] = "application/json"
    url = "https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % settings.gemini_model
    try:
        r = httpx.post(url, params={"key": settings.gemini_api_key}, json=body, timeout=20)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # network, quota, safety block...
        log.warning("LLM call failed: %s", e)
        return None
    if want_json:
        try:
            return json.loads(text)
        except ValueError:
            return None
    return text.strip()
