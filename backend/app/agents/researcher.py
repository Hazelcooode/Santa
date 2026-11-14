"""Researcher: runs the TaskSpec's searches through the budgeted Exa gateway.

Each search requests highlights plus (when useful) a JSON-schema summary, so
structured facts (price, date, venue...) are extracted by Exa from the page
content in the same call. Extracted values are treated as unverified claims tied
to their source URL; pages are data, never instructions."""
from concurrent.futures import ThreadPoolExecutor

from .. import exa_client

SCHEMAS = {
    "price": {
        "type": "object",
        "properties": {
            "product": {"type": "string", "description": "Exact product name on the page"},
            "price": {"type": "number", "description": "Current price for one package as a number, no currency symbol. 0 if not shown."},
            "currency": {"type": "string", "description": "ISO currency code, e.g. EUR"},
            "package_size": {"type": "string"},
            "store": {"type": "string", "description": "Retailer or store name"},
            "is_requested_item": {"type": "boolean", "description": "true if this product is the item named in the request, "
                                  "in any language or brand (e.g. Finnish 'kaurajuoma' is oat milk); false if it is a different product"},
        },
        "required": ["product", "price"],
    },
    "event": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "date_text": {"type": "string", "description": "Human readable date/time, e.g. 'Fri 20 Nov, 22:00'"},
            "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD of the next occurrence, empty if unknown"},
            "venue": {"type": "string"},
            "city": {"type": "string"},
            "price_text": {"type": "string", "description": "Ticket price or 'Free'; empty if unknown"},
            "category": {"type": "string", "description": "One or two words, e.g. jazz, market, sport"},
            "summary": {"type": "string", "description": "One short sentence about what to expect"},
        },
        "required": ["title"],
    },
    "travel": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["flight", "train", "ferry", "bus", "stay", "activity", "other"]},
            "title": {"type": "string", "description": "Operator/route or property name"},
            "price": {"type": "number", "description": "Lowest price shown as a number (per night for stays), 0 if none"},
            "currency": {"type": "string"},
            "details": {"type": "string", "description": "One short line: times, rating or what's included"},
        },
        "required": ["kind", "title"],
    },
    "product": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "price": {"type": "number", "description": "Current price as a number, 0 if not shown"},
            "currency": {"type": "string"},
            "store": {"type": "string"},
            "attributes": {"type": "array", "items": {"type": "string"}, "description": "Short features: material, colour, fit, use"},
        },
        "required": ["title"],
    },
    "medicine": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Product name with strength and pack size"},
            "price": {"type": "number", "description": "Price as a number, 0 if not shown"},
            "currency": {"type": "string"},
            "pharmacy": {"type": "string"},
            "otc": {"type": "boolean", "description": "True only if sold without prescription"},
            "usage_note": {"type": "string", "description": "Key dosage limit or warning, one sentence"},
        },
        "required": ["name", "otc"],
    },
    "meal": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "why": {"type": "string", "description": "Why it helps, one short line"},
            "time_minutes": {"type": "number"},
        },
        "required": ["title"],
    },
}


def _run_query(user, qq):
    res = exa_client.search(
        user["id"], qq["kind"], qq["query"],
        num_results=qq.get("num_results", 5),
        include_domains=qq.get("include_domains"),
        user_location=qq.get("user_location"),
        start_published_date=qq.get("start_published_date"),
        summary_query=qq.get("summary_query") if qq.get("schema") else None,
        summary_schema=SCHEMAS.get(qq.get("schema")),
    )
    priced = [r for r in res["results"] if isinstance(r.get("summary"), dict) and (r["summary"].get("price") or 0) > 0]
    if res["available"] and qq.get("refine_without_domains") and not priced:
        # One refinement cycle: widen from preferred retailer domains to any local page.
        res2 = exa_client.search(
            user["id"], qq["kind"], qq["query"], num_results=qq.get("num_results", 5),
            user_location=qq.get("user_location"), summary_query=qq.get("summary_query"),
            summary_schema=SCHEMAS.get(qq.get("schema")),
        )
        if res2["available"]:
            res2["results"] = res["results"] + res2["results"]
            res2["refined"] = True
            return res2
    return res


def research(user, spec):
    queries = spec["queries"]
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(queries)))) as ex:
        outs = list(ex.map(lambda qq: _run_query(user, qq), queries))

    available = any(o["available"] for o in outs) if outs else False
    reasons = sorted({o.get("reason") for o in outs if not o["available"] and o.get("reason")})
    candidates, sources, seen = [], [], set()
    for qq, out in zip(queries, outs):
        for r in out["results"]:
            candidates.append(dict(r, key=qq["key"], schema=qq.get("schema")))
            if r["url"] not in seen:
                seen.add(r["url"])
                sources.append({"title": r["title"], "url": r["url"], "domain": r["domain"],
                                "excerpt": (r["highlights"] or [""])[0][:300], "publishedAt": r.get("publishedDate"),
                                "image": r.get("image")})
    return {
        "available": available,
        "reason": ", ".join(reasons) or ("no results" if not available else None),
        "candidates": candidates,
        "sources": sources,
        "byKey": {qq["key"]: out for qq, out in zip(queries, outs)},
        "costUsd": round(sum(o.get("costUsd", 0) for o in outs), 4),
    }
