"""Budgeted, cached gateway to Exa (the agents' only web search source).

Cost-control practices (we have one $50 credit):
  * One Exa call per research step: `search` with contents inlined (highlights +
    an optional JSON-schema summary). No separate /contents round-trips, no
    "deep" search, small `num_results`.
  * Shared SQLite cache keyed by the normalised request, with a TTL per kind
    (prices hours, events half a day, evergreen advice a week). Identical
    concurrent requests are coalesced with a per-key lock.
  * Hard caps: total spend, daily spend and per-user daily requests. When a cap
    is hit the gateway returns `available=False`; callers fall back to clearly
    labelled demo data instead of failing.
  * Every call is written to a ledger with the provider-reported `costDollars`
    (or a configured estimate when absent), visible at GET /api/v1/usage.
  * Personal data never goes into queries (no names, health history, calendar
    text). Callers send public search terms only.
"""
import hashlib
import json
import logging
import re
import threading
import time
from datetime import timedelta
from urllib.parse import urlparse

from . import db
from .config import settings

log = logging.getLogger("taimi.exa")

TTL_HOURS = {
    "prices": 6,
    "products": 12,
    "events": 12,
    "travel": 6,
    "social": 12,
    "medicine": 72,
    "wellbeing": 24 * 7,
    "interests": 12,
    "places": 24 * 7,
    "answer": 24,
    "watch": 3,
}

_key_locks = {}
_key_locks_guard = threading.Lock()
_client = None


def _lock_for(key):
    with _key_locks_guard:
        lk = _key_locks.get(key)
        if lk is None:
            lk = _key_locks[key] = threading.Lock()
        return lk


def _get_client():
    global _client
    if _client is None:
        from exa_py import Exa  # imported lazily so tests run without network

        _client = Exa(api_key=settings.exa_api_key)
    return _client


def domain_of(url):
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def safe_url(url):
    try:
        p = urlparse(url or "")
    except ValueError:
        return None
    return url if p.scheme in ("http", "https") and p.hostname else None


class Unavailable(Exception):
    pass


def spend_summary():
    total = db.q1("SELECT COALESCE(SUM(cost_usd),0) AS s, COUNT(*) AS n FROM exa_ledger WHERE cached=0 AND status='ok'")
    day = db.iso(db.now() - timedelta(days=1))
    today = db.q1("SELECT COALESCE(SUM(cost_usd),0) AS s, COUNT(*) AS n FROM exa_ledger WHERE cached=0 AND status='ok' AND at>=?", (day,))
    cached = db.q1("SELECT COUNT(*) AS n FROM exa_ledger WHERE cached=1")
    return {
        "mode": effective_mode(),
        "totalUsd": round(total["s"], 4),
        "totalCalls": total["n"],
        "last24hUsd": round(today["s"], 4),
        "last24hCalls": today["n"],
        "cacheHits": cached["n"],
        "totalBudgetUsd": settings.exa_total_budget_usd,
        "dailyBudgetUsd": settings.exa_daily_budget_usd,
        "userDailyRequests": settings.exa_user_daily_requests,
    }


def effective_mode():
    if settings.exa_mode == "mock":
        return "mock"
    if not settings.exa_api_key:
        return "demo (no EXA_API_KEY)"
    return settings.exa_mode


def _budget_ok(user_id):
    s = spend_summary()
    if s["totalUsd"] >= settings.exa_total_budget_usd:
        return "total Exa budget reached"
    if s["last24hUsd"] >= settings.exa_daily_budget_usd:
        return "daily Exa budget reached"
    if user_id:
        day = db.iso(db.now() - timedelta(days=1))
        n = db.q1("SELECT COUNT(*) AS n FROM exa_ledger WHERE user_id=? AND cached=0 AND at>=?", (user_id, day))["n"]
        if n >= settings.exa_user_daily_requests:
            return "your daily research quota is used up"
    return None


def _ledger(user_id, kind, query, cost, estimated, cached, status="ok"):
    db.run(
        "INSERT INTO exa_ledger(id,user_id,at,kind,query,cost_usd,estimated,cached,status) VALUES(?,?,?,?,?,?,?,?,?)",
        (db.new_id("x_"), user_id, db.iso(), kind, (query or "")[:300], cost, int(estimated), int(cached), status),
    )


def _cache_get(key):
    row = db.q1("SELECT response, expires_at FROM exa_cache WHERE key=?", (key,))
    if row and db.parse_iso(row["expires_at"]) > db.now():
        return db.loads(row["response"])
    return None


def _cache_put(key, kind, payload):
    exp = db.now() + timedelta(hours=TTL_HOURS.get(kind, 12))
    db.run(
        "INSERT INTO exa_cache(key,kind,response,created_at,expires_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET response=excluded.response, created_at=excluded.created_at, expires_at=excluded.expires_at",
        (key, kind, db.dumps(payload), db.iso(), db.iso(exp)),
    )


def _provider_status(error):
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None) or getattr(error, "status_code", None)
    if status is not None:
        return int(status)
    match = re.search(r"(?:status code|HTTP)\s*[:=]?\s*(\d{3})\b", str(error), re.I)
    return int(match.group(1)) if match else None


def _provider_failure(error):
    status = _provider_status(error)
    if status == 400:
        return "EXA_INVALID_REQUEST", "Exa rejected the search request (HTTP 400). The request/schema needs correcting; existing prices were not changed.", False
    if status in (401, 403):
        return "EXA_AUTH_FAILED", "Exa authentication or account access failed. Check the configured API key and permissions.", False
    if status == 429:
        return "EXA_RATE_LIMITED", "Exa rate limit reached. Wait before updating prices again.", True
    return "LIVE_RESEARCH_UNAVAILABLE", "Exa could not complete this search. Existing quotes were retained; retry later.", True


def _with_retries(fn):
    delay = 0.8
    for attempt in range(3):
        try:
            return fn()
        except Exception as e:  # SDK raises ValueError / httpx errors with status in text
            status = _provider_status(e)
            msg = str(e).lower()
            retryable = status in (429, 500, 502, 503, 504) if status else any(t in msg for t in ("timed out", "timeout"))
            if not retryable or attempt == 2:
                raise
            time.sleep(delay)
            delay *= 2


def _parse_summary(raw):
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {"text": raw}


def _normalise_result(r):
    url = safe_url(getattr(r, "url", None))
    if not url:
        return None
    return {
        "url": url,
        "title": (getattr(r, "title", None) or domain_of(url))[:200],
        "domain": domain_of(url),
        "publishedDate": getattr(r, "published_date", None),
        "image": safe_url(getattr(r, "image", None)),
        "favicon": safe_url(getattr(r, "favicon", None)),
        "highlights": [h[:500] for h in (getattr(r, "highlights", None) or [])][:3],
        "summary": _parse_summary(getattr(r, "summary", None)),
    }


def search(user_id, kind, query, *, num_results=5, include_domains=None, exclude_domains=None,
           user_location=None, start_published_date=None, summary_query=None, summary_schema=None,
           category=None, search_type="auto", force_refresh=False):
    """Returns {"available": bool, "results": [...], "source": live|cache|none, "reason": str?, "costUsd": float}."""
    num_results = max(1, min(int(num_results), 10))
    body = {
        "q": " ".join(query.split())[:400], "n": num_results,
        "inc": sorted(include_domains or [])[:20], "exc": sorted(exclude_domains or [])[:20],
        "loc": (user_location or "").upper()[:2] or None, "since": start_published_date,
        "sq": summary_query, "schema": summary_schema, "cat": category, "type": search_type,
    }
    key = "search:" + hashlib.sha256(db.dumps(body).encode()).hexdigest()

    cached = None if force_refresh else _cache_get(key)
    if cached is not None:
        _ledger(user_id, kind, query, 0, False, True)
        return {"available": True, "results": cached, "source": "cache", "costUsd": 0, "fetchedAt": db.q1("SELECT created_at FROM exa_cache WHERE key=?", (key,))["created_at"]}

    mode = effective_mode()
    if mode != "live":
        return {"available": False, "results": [], "source": "none", "reason": mode, "costUsd": 0}

    with _lock_for(key):
        cached = None if force_refresh else _cache_get(key)  # another request may have filled it while we waited
        if cached is not None:
            _ledger(user_id, kind, query, 0, False, True)
            return {"available": True, "results": cached, "source": "cache", "costUsd": 0, "fetchedAt": db.q1("SELECT created_at FROM exa_cache WHERE key=?", (key,))["created_at"]}
        reason = _budget_ok(user_id)
        if reason:
            return {"available": False, "results": [], "source": "none", "reason": reason, "costUsd": 0}

        contents = {"highlights": True}
        if force_refresh:
            contents["max_age_hours"] = 0
        if summary_query or summary_schema:
            contents["summary"] = {k: v for k, v in (("query", summary_query), ("schema", summary_schema)) if v}
        kwargs = dict(num_results=num_results, contents=contents, type=search_type,
                      timeout=settings.exa_timeout_s)
        if include_domains:
            kwargs["include_domains"] = list(include_domains)[:20]
        if exclude_domains:
            kwargs["exclude_domains"] = list(exclude_domains)[:20]
        if body["loc"]:
            kwargs["user_location"] = body["loc"]
        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        if category:
            kwargs["category"] = category
        try:
            resp = _with_retries(lambda: _get_client().search(body["q"], **kwargs))
        except Exception as e:
            log.warning("Exa search failed (%s): %s", kind, e)
            _ledger(user_id, kind, query, 0, True, False, status="error")
            code, reason, retryable = _provider_failure(e)
            return {"available": False, "results": [], "source": "none", "reason": reason, "errorCode": code, "retryable": retryable, "costUsd": 0}

        results = [x for x in (_normalise_result(r) for r in resp.results) if x]
        cost = getattr(getattr(resp, "cost_dollars", None), "total", None)
        estimated = cost is None
        if estimated:
            cost = settings.exa_est_search_usd + settings.exa_est_page_usd * len(results) * (2 if "summary" in contents else 1)
        _ledger(user_id, kind, query, float(cost), estimated, False)
        _cache_put(key, kind, results)
        return {"available": True, "results": results, "source": "live", "costUsd": float(cost), "fetchedAt": db.iso()}


def answer(user_id, query, user_location=None):
    """Exa /answer: a short grounded answer with citations (used by chat for factual questions)."""
    q = " ".join(query.split())[:300]
    key = "answer:" + hashlib.sha256((q + "|" + (user_location or "")).encode()).hexdigest()
    cached = _cache_get(key)
    if cached is not None:
        _ledger(user_id, "answer", q, 0, False, True)
        return dict(cached, available=True, source="cache")
    if effective_mode() != "live":
        return {"available": False, "reason": effective_mode()}
    with _lock_for(key):
        reason = _budget_ok(user_id)
        if reason:
            return {"available": False, "reason": reason}
        try:
            kwargs = {"text": False, "timeout": settings.exa_timeout_s}
            if user_location:
                kwargs["user_location"] = user_location.upper()[:2]
            resp = _with_retries(lambda: _get_client().answer(q, **kwargs))
        except Exception as e:
            log.warning("Exa answer failed: %s", e)
            _ledger(user_id, "answer", q, 0, True, False, status="error")
            return {"available": False, "reason": "search provider error"}
        cites = []
        for c in (getattr(resp, "citations", None) or [])[:4]:
            url = safe_url(getattr(c, "url", None))
            if url:
                cites.append({"title": (getattr(c, "title", None) or domain_of(url))[:160], "url": url})
        cost = getattr(getattr(resp, "cost_dollars", None), "total", None)
        _ledger(user_id, "answer", q, float(cost if cost is not None else 0.005), cost is None, False)
        payload = {"answer": str(getattr(resp, "answer", "") or "")[:1200], "citations": cites}
        _cache_put(key, "answer", payload)
        return dict(payload, available=True, source="live")


def sources_from(results, limit=4):
    out, seen = [], set()
    for r in results:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append({"title": r["title"], "url": r["url"]})
        if len(out) >= limit:
            break
    return out
