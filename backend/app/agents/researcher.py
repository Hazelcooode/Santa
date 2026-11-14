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
            "price": {"type": "number", "description": "Current package price, not per kg/litre, no currency symbol. Omit this optional field when the price is not shown; never invent a price."},
            "currency": {"type": "string", "description": "ISO currency code, e.g. EUR"},
            "package_size": {"type": "string"},
            "store": {"type": "string", "description": "Retailer or store name"},
        },
        "required": ["product"],
    },
    "event": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "event_page_type": {"type":"string","enum":["single_event","activity","event_listing","article","unknown"],"description":"single_event for a page dedicated to ONE named event/edition, including workshops and learning meetups. activity for ONE specific sourced attraction, experience or ongoing activity at a named place. Directories, calendars and top-N collections are event_listing. Never merge unrelated events."},
            "event_evidence": {"type":"string","description":"Verbatim source text identifying this one event, venue and schedule. Empty when unsupported."},
            "location_match": {"type": "boolean", "description": "True ONLY if this event is in the destination requested in the query. Do not substitute the user's home city."},
            "end_date": {"type": "string", "description": "Event end date YYYY-MM-DD, not article publication date; empty if unknown"},
            "start_time": {"type": "string", "description": "Local event start time including timezone if stated; empty if unknown"},
            "end_time": {"type": "string", "description": "Local event end time; empty if unknown"},
            "country": {"type": "string"},
            "date_text": {"type": "string", "description": "Human readable date/time, e.g. 'Fri 20 Nov, 22:00'"},
            "start_date": {"type": "string", "description": "ISO date YYYY-MM-DD of the next occurrence, empty if unknown"},
            "venue": {"type": "string"},
            "city": {"type": "string"},
            "price_text": {"type": "string", "description": "Ticket price or 'Free'; empty if unknown"},
            "category": {"type": "string", "description": "One or two words, e.g. jazz, market, sport"},
            "summary": {"type": "string", "description": "A useful 3-5 sentence description (roughly 70-140 words): what visitors can actually do/learn, atmosphere or audience, relevant dates/venue and admission when evidenced. Use source facts only; do not repeat generic filler or invent availability."},
            "activity_idea": {"type": "string", "description": "One concrete thing the user can do at this event/activity, grounded in the source."},
            "admission": {"type":"string","enum":["free","paid","unknown"],"description":"free only when admission is explicitly free; paid when an entrance ticket is required; unknown otherwise."},
            "group_suitable": {"type":"boolean","description":"False only if the stated group size is explicitly incompatible with source rules. Do not infer ticket capacity or availability."},
        },
        "required": ["title", "location_match", "event_page_type"],
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

# The schema summary is evaluated against this query's complete requirements,
# not a generic description. Unknown evidence must never be reported as a match.
for _key in ('price', 'product'):
    SCHEMAS[_key]['properties'].update({
        'attribute_checks': {'type':'array','items':{'type':'object','properties':{'key':{'type':'string'},'value':{'type':'string'},'exact_match':{'type':'boolean'},'evidence':{'type':'string'}},'required':['key','value','exact_match','evidence']},'description':'One check for EACH requested attribute. Copy its exact requested key/value. exact_match true only when this product-specific evidence verifies the requested attribute without substitutions; otherwise false.'},
        'item_type_match': {'type':'boolean','description':'True only for the requested actual item, not seasoning, accessories, sauces or substitutes intended for it.'},
        'category_match': {'type':'boolean','description':'Does the actual product belong to the requested category/aisle? Infer from product identity, not intended use.'},
        'price_text': {'type': 'string', 'description': 'Verbatim current full package/item price including decimal separator/currency, for example 2,49 €. Never kg/l price, old price, installment, membership-only or multi-buy price. Empty if unavailable.'},
        'price_basis': {'type': 'string', 'enum': ['package', 'item', 'unit_weight', 'unknown']},
        'availability': {'type': 'string', 'enum': ['in_stock', 'out_of_stock', 'preorder', 'unknown'], 'description': 'in_stock only with explicit current evidence that this exact variant can be purchased now.'},
        'availability_evidence': {'type': 'string', 'description': 'Verbatim availability text; empty if unknown.'},
        'image_urls': {'type': 'array', 'items': {'type': 'string'}, 'description': 'Actual product image URLs from this page; never invent URLs.'},
        'page_type': {'type': 'string', 'enum': ['product', 'category', 'search', 'article', 'unknown']},
        'request_match': {'type': 'string', 'enum': ['matches', 'mismatch', 'unknown'],
                          'description': 'Does this ONE product satisfy ALL requested type, brand, variant and technical requirements? Account for translations, units and model families; unknown when not evidenced.'},
        'match_evidence': {'type': 'string', 'description': 'Verbatim product-specific page text supporting ALL requested requirements. Empty if not verifiable; never invent or combine multiple products.'},
    })


def _usable(qq, result):
    from ..services.shopping_prices import matches
    from ..services.price_evidence import quote
    s = result.get('summary') if isinstance(result.get('summary'), dict) else {}
    minor, reason = quote(s, qq.get('currency', 'EUR'), package=qq.get('schema') == 'price')
    return minor is not None and (qq.get('kind') != 'watch' or (s.get('availability') == 'in_stock' and s.get('availability_evidence'))) and matches(qq.get('requirements') or {}, result)


def _run_query(user, qq):
    res = exa_client.search(
        user["id"], qq["kind"], qq["query"],
        force_refresh=qq.get("forceRefresh", False),
        num_results=qq.get("num_results", 5),
        include_domains=qq.get("include_domains"),
        user_location=qq.get("user_location"),
        start_published_date=qq.get("start_published_date"),
        summary_query=qq.get("summary_query") if qq.get("schema") else None,
        summary_schema=SCHEMAS.get(qq.get("schema")),
    )
    if (res['available'] and qq.get('product_refinement') and
            not any(_usable(qq, r) for r in res['results'])):
        # One bounded refinement, always retaining the user's chosen websites.
        # Cached requests reuse both steps; provider failures are not widened.
        refined = exa_client.search(
            user['id'], qq['kind'], qq['product_refinement'],
            force_refresh=qq.get('forceRefresh', False), num_results=6,
            include_domains=qq.get('include_domains'), user_location=qq.get('user_location'),
            summary_query=qq.get('summary_query'), summary_schema=SCHEMAS.get(qq.get('schema')),
        )
        if refined['available']:
            # Keep result-level freshness so a cached first step cannot make a
            # live refinement look cached (or the reverse).
            combined = []
            seen = set()
            for out in (refined, res):
                for r in out['results']:
                    if r['url'] not in seen:
                        seen.add(r['url'])
                        combined.append(dict(r, fetchedAt=out.get('fetchedAt'), cached=out.get('source') == 'cache'))
            return dict(refined, results=combined, costUsd=res.get('costUsd', 0)+refined.get('costUsd', 0))
        res['refinementReason'] = refined.get('reason')
    if (res['available'] and qq.get('event_refinement') and sum(
            isinstance(r.get('summary'),dict) and r['summary'].get('event_page_type') in ('single_event', 'activity')
            and r['summary'].get('location_match') is True for r in res['results']) < qq.get('event_min_results', 1)):
        extra=exa_client.search(user['id'],qq['kind'],qq['event_refinement'],num_results=10,force_refresh=qq.get('forceRefresh',False),
            user_location=qq.get('user_location'),include_domains=qq.get('include_domains'),
            summary_query=qq.get('summary_query'),summary_schema=SCHEMAS.get(qq.get('schema')))
        if extra['available']:
            merged=[]; seen=set()
            for out in (extra,res):
                for row in out['results']:
                    if row['url'] not in seen:
                        seen.add(row['url'])
                        merged.append(dict(row,fetchedAt=out.get('fetchedAt'),cached=out.get('source')=='cache'))
            return dict(extra,results=merged,costUsd=res.get('costUsd',0)+extra.get('costUsd',0))
        res['refinementReason']=extra.get('reason')
    priced = [r for r in res["results"] if isinstance(r.get("summary"), dict) and (r["summary"].get("price") or 0) > 0]
    if res["available"] and qq.get("refine_without_domains") and not priced:
        # One refinement cycle: widen from preferred retailer domains to any local page.
        res2 = exa_client.search(
            user["id"], qq["kind"], qq["query"], num_results=qq.get("num_results", 5),
            force_refresh=qq.get("forceRefresh", False),
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
    candidates, sources, seen, candidate_seen = [], [], set(), set()
    ordered = [(qq, out, row) for qq, out in zip(queries, outs) for row in out['results']]
    if spec.get('intent') == 'events':
        # Interleave batches: one broad query must not crowd workshops/Luma out of the top twenty.
        ordered = [(qq, out, out['results'][index])
                   for index in range(max((len(out['results']) for out in outs), default=0))
                   for qq, out in zip(queries, outs) if index < len(out['results'])]
    for qq, out, r in ordered:
        if (qq['key'], r['url']) in candidate_seen:
            continue
        candidate_seen.add((qq['key'], r['url']))
        candidates.append(dict(r, key=qq['key'], schema=qq.get('schema'), fetchedAt=r.get('fetchedAt') or out.get('fetchedAt'), cached=r.get('cached', out.get('source') == 'cache')))
        if r['url'] not in seen:
            seen.add(r['url'])
            sources.append({'title': r['title'], 'url': r['url'], 'domain': r['domain'],
                            'excerpt': (r['highlights'] or [''])[0][:300], 'publishedAt': r.get('publishedDate'),
                            'image': r.get('image')})

    return {
        "available": available,
        "reason": ", ".join(reasons) or ("no results" if not available else None),
        "errors": [{"code": o.get("errorCode"), "message": o.get("reason"), "retryable": o.get("retryable", True)} for o in outs if o.get("errorCode")],
        "candidates": candidates,
        "sources": sources,
        "lookups": [{'itemId': qq['key'], 'domains': qq.get('include_domains') or [], 'status': 'searched' if out['available'] else 'failed', 'pages': len(out['results']), 'reason': out.get('reason') or out.get('refinementReason')} for qq,out in zip(queries,outs)],
        "byKey": {qq["key"]: out for qq, out in zip(queries, outs)},
        "costUsd": round(sum(o.get("costUsd", 0) for o in outs), 4),
    }
