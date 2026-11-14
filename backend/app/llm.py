"""Language model for the agents (Claude, via the official Anthropic SDK).

Used inside the agent roles for request parsing, laundry advice wording and
consented photo features, and as the chat agent (run_agent: a tool-use loop
over our own tools only). It is never a search source and no Anthropic
server-side tools are enabled: facts, prices and links come from Exa. Every
caller has a fallback, so the backend still runs with no model credentials.

Model: LLM_MODEL (default claude-haiku-5-5). Credentials are resolved by the SDK
(ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or an `ant auth login` profile)."""
import json
import logging
import os
import re
import threading
import time
from pathlib import Path

from .config import settings

log = logging.getLogger("taimi.llm")

try:
    import anthropic
except ImportError:  # the backend runs without the SDK, with deterministic fallbacks
    anthropic = None

_client = None
_lock = threading.Lock()
_disabled_until = 0.0  # short circuit-breaker after auth/permission errors


def _has_credentials():
    if settings.anthropic_api_key or os.getenv("ANTHROPIC_AUTH_TOKEN") or os.getenv("ANTHROPIC_PROFILE"):
        return True
    return (Path.home() / ".config" / "anthropic").is_dir()


def available():
    return bool(anthropic) and settings.llm_enabled and _has_credentials() and time.time() >= _disabled_until


def model_name():
    return settings.llm_model


def _get_client():
    global _client
    with _lock:
        if _client is None:
            kw = {"timeout": settings.llm_timeout_s, "max_retries": 1}
            if settings.anthropic_api_key:
                kw["api_key"] = settings.anthropic_api_key
            _client = anthropic.Anthropic(**kw)
        return _client


def nullable(t):
    """JSON-schema helper for an optional value in a structured-output schema."""
    return {"anyOf": [{"type": t}, {"type": "null"}]}


def obj(properties):
    """Strict object schema: every property required, no extras (structured outputs)."""
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def _image_block(data_url):
    m = re.match(r"data:(image/(?:png|jpeg|gif|webp));base64,(.+)", data_url or "", re.S)
    if not m:
        return None
    return {"type": "image", "source": {"type": "base64", "media_type": m.group(1), "data": m.group(2).strip()}}


def complete(system, turns, schema=None, image_data_url=None, max_tokens=None, effort="low"):
    """turns: [(role, text)] with role user|assistant (bot/model accepted).

    With `schema` the reply is constrained to that JSON schema and returned as a
    dict; otherwise the reply text. Returns None on any failure (callers fall back)."""
    global _disabled_until
    if not available():
        return None
    messages = []
    for role, text in turns[-12:]:
        r = "assistant" if role in ("model", "bot", "assistant") else "user"
        text = (text or "").strip()[:4000]
        if not text:
            continue
        if messages and messages[-1]["role"] == r:
            messages[-1]["content"][0]["text"] += "\n" + text
        else:
            messages.append({"role": r, "content": [{"type": "text", "text": text}]})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    if not messages:
        return None
    if messages[-1]["role"] != "user":  # no assistant prefill on current models
        messages.append({"role": "user", "content": [{"type": "text", "text": "(continue)"}]})
    img = _image_block(image_data_url) if image_data_url else None
    if img:
        messages[-1]["content"].insert(0, img)

    req = {
        "model": settings.llm_model,
        "max_tokens": max_tokens or (2048 if schema else 1536),
        "system": system,
        "messages": messages,
        "output_config": {"effort": effort},
    }
    if schema:
        req["output_config"]["format"] = {"type": "json_schema", "schema": schema}
    try:
        resp = _get_client().messages.create(**req)
    except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
        _disabled_until = time.time() + 300
        log.warning("LLM disabled for 5 min (%s): %s", type(e).__name__, getattr(e, "message", e))
        return None
    except anthropic.RateLimitError:
        log.warning("LLM rate limited; using fallback")
        return None
    except anthropic.APIStatusError as e:
        log.warning("LLM API error %s: %s", e.status_code, getattr(e, "message", e))
        return None
    except anthropic.APIConnectionError as e:
        log.warning("LLM connection error: %s", e)
        return None

    if resp.stop_reason == "refusal":
        log.info("LLM declined (%s)", getattr(resp.stop_details, "category", None) if resp.stop_details else None)
        return None
    if resp.stop_reason == "max_tokens" and schema:
        return None  # truncated JSON is not usable
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if not text:
        return None
    if schema:
        try:
            return json.loads(text)
        except ValueError:
            return None
    return text


def run_agent(system, messages, tools, execute, max_steps=5, max_tokens=1536, effort="low"):
    """Manual tool-use loop over client-defined tools only (no Anthropic server tools,
    so the model cannot search anywhere we did not give it).

    messages: Messages-API list ending with a user turn. execute(name, input) -> str
    (raise ValueError for a bad call; it is returned to the model as an error result).
    Returns the final reply text, or None on any failure (callers fall back)."""
    global _disabled_until
    if not available() or not messages:
        return None
    msgs = list(messages)
    nudged = False
    for step in range(max_steps):
        req = {"model": settings.llm_model, "max_tokens": max_tokens, "system": system,
               "messages": msgs, "tools": tools, "output_config": {"effort": effort}}
        if step == max_steps - 1:
            req["tool_choice"] = {"type": "none"}   # last step: answer with what it has
        try:
            resp = _get_client().messages.create(**req)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
            _disabled_until = time.time() + 300
            log.warning("LLM disabled for 5 min (%s): %s", type(e).__name__, getattr(e, "message", e))
            return None
        except anthropic.RateLimitError:
            log.warning("LLM rate limited; using fallback")
            return None
        except anthropic.APIStatusError as e:
            log.warning("LLM API error %s: %s", e.status_code, getattr(e, "message", e))
            return None
        except anthropic.APIConnectionError as e:
            log.warning("LLM connection error: %s", e)
            return None
        if resp.stop_reason == "refusal":
            log.info("LLM declined (%s)", getattr(resp.stop_details, "category", None) if getattr(resp, "stop_details", None) else None)
            return None
        calls = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason != "tool_use" or not calls:
            text = "".join(b.text for b in resp.content if b.type == "text").strip()
            if not text and not nudged and resp.stop_reason == "end_turn" and step < max_steps - 1:
                nudged = True   # ended silently after its tools: ask once for the actual reply
                msgs.append({"role": "system", "content": "Now write your reply to the user."})
                continue
            if not text:
                log.warning("Agent returned no text (stop_reason=%s)", resp.stop_reason)
            return text or None
        msgs.append({"role": "assistant", "content": resp.content})   # unchanged, thinking blocks included
        results = []
        for c in calls:   # all results go back in one user message
            try:
                out, err = execute(c.name, c.input or {}), False
            except ValueError as e:
                out, err = str(e), True
            except Exception as e:  # a tool must never break the chat
                log.warning("Tool %s failed: %s", c.name, e)
                out, err = "Tool failed.", True
            results.append({"type": "tool_result", "tool_use_id": c.id, "content": str(out)[:12000], "is_error": err})
        msgs.append({"role": "user", "content": results})
    log.info("Agent hit the step limit")
    return None
