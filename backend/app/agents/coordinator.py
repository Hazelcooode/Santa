"""Coordinator: turns a request into a validated TaskSpec.

Only public search terms go into queries: no names, health history or calendar
text. Location comes from the user's profile (city + country), so the same code
works for users anywhere; site_region / preferred_domains choose which local
websites to search."""
import re
from datetime import datetime, timezone

from .. import db, llm, regions, search_scope

STOP = set("a an the and or for to in on at of with this that next my me i want find some any please near around from "
           "trip travel weekend winter summer spring autumn fall holiday holidays visit go going cheap".split())

INTENTS = ("groceries", "events", "travel", "products", "medicine", "wellbeing", "interests", "watch")


def _month_year():
    return datetime.now(timezone.utc).strftime("%B %Y")


def _interests(user):
    rows = db.q("SELECT text, tag FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT 12", (user["id"],))
    return rows


def _clean_item_name(name):
    name = re.sub(r"\(.*?\)", " ", name or "")
    return " ".join(name.split())[:60]


def extract_destination(query):
    if llm.available():
        out = llm.complete("Extract the travel destination (city/region/country) from the request. Reply JSON "
                           '{"destination": string|null, "nights": integer|null}.', [("user", query)], want_json=True,
                           temperature=0)
        if isinstance(out, dict) and out.get("destination"):
            return out["destination"], out.get("nights")
    words = [w for w in re.findall(r"[\w'-]+", query or "") if w.lower() not in STOP and not w.isdigit()]
    return (" ".join(words[:3]) or None), None


def plan(user, intent, payload):
    if intent not in INTENTS:
        return {"intent": intent, "missingFields": ["intent"], "queries": []}
    city = regions.city(user)
    cc = regions.country(user)
    area = search_scope.area(user)
    bias = search_scope.location_bias(user)
    spec = {
        "intent": intent, "location": ", ".join([x for x in (city, user.get("country")) if x]),
        "city": city, "country": cc, "currency": regions.currency(user), "queries": [],
        "payload": payload, "missingFields": [],
    }
    q = (payload.get("query") or "").strip()

    if intent == "groceries":
        items = [i for i in payload.get("items") or [] if (i.get("name") or "").strip()]
        if not items:
            spec["missingFields"].append("items")
        domains = regions.grocery_domains(user)
        lookup_items = [it for it in items if it.get("id") not in (payload.get("cachedItemIds") or [])]
        for it in lookup_items[:8]:  # budget: at most 8 new lookups, saved quotes cover the rest
            name = " ".join([it["name"], it.get("brand") or "", it.get("details") or "", " ".join(str(k)+"="+str(v) for k,v in (it.get("attributes") or {}).items())])[:350]
            request_description=db.dumps({'item':it['name'],'brand':it.get('brand') or '', 'details':it.get('details') or '', 'attributes':it.get('attributes') or {}})
            item_query = {
                "key": it.get("id") or name, "kind": "prices", "schema": "price",
                "query": "%s price %s grocery" % (name, area), "include_domains": domains,
                "summary_query": "Every user attribute and detail is a hard constraint, without substitutions. Verify item_type_match for the ACTUAL product, not a seasoning/accessory for that product. Use the requested category as a product-type constraint and set category_match. Return attribute_checks for EVERY supplied key/value with exact_match and product-specific evidence binding that value to its attribute. Never infer a fat percentage from a protein percentage or replace a requested flavour. Quote evidence containing each exact attribute value. If unsupported omit the price. Inspect ONE product matching this full request: %s. Interpret translated product names. Extract current package price (not per kg), currency, exact product, variant and size. Return verbatim price_text and price_basis=package only for the full package price, never per kg/l. Do not convert cents yourself. Classify page_type; category/search pages are not product offers. Assess request_match against ALL requirements and quote match_evidence. Omit price if missing; do not substitute variants or invent facts." % request_description, "num_results": 6,
                "requirements": dict(it, _strict=True),
                "product_refinement": "%s %s %s %s specific product package price buy %s" % (it.get('brand') or '', ' '.join(str(v) for v in (it.get('attributes') or {}).values()), it.get('details') or '', it['name'], area),
                "refine_without_domains": False, "forceRefresh": payload.get("forceRefresh", False), "currency": regions.currency(user),
            }
            for domain in domains or [None]:
                spec["queries"].append(dict(item_query, include_domains=[domain] if domain else None))
        spec["overflowItems"] = [i.get("id") for i in lookup_items[8:]]

    elif intent == "events":
        interests = payload.get("interests") or []
        topic = q or " ".join(interests[:2]) or "things to do"
        destination = str(payload.get('destination') or payload.get('location') or '').strip()
        if not destination:
            spec['missingFields'].append('location')
        destination_country = payload.get('destinationCountry') or ''
        spec['city'] = destination
        spec['location'] = destination
        spec['eventDestination'] = destination
        spec['interests'] = interests
        date_hint = payload.get('dateFrom') or ('' if re.search(r'\b20\d{2}\b', topic) else str(datetime.now(timezone.utc).year))
        admission = payload.get('admission') or 'any'
        preferences = db.dumps({'request': topic, 'location': destination,
            'dates': [payload.get('dateFrom'), payload.get('dateTo')], 'people': payload.get('people'),
            'admission': admission, 'context': payload.get('context') or ''})
        summary = (
            'Find ONE specific event, learning session, workshop or actionable activity per page, '
            'matching this complete request: '+preferences+'. '
            'The specified location overrides any home city or unrelated location in general recommendations. '
            'Set location_match true only for the requested location. Never substitute another city. '
            'For a dedicated event/edition page set event_page_type=single_event; for one concrete ongoing '
            'experience or attraction at a named location use activity. A holiday market, museum visit, '
            'public skating session or workshop can be an activity idea when supported by its own source. '
            'Directories, calendars, category pages and lists of unrelated events are event_listing and must '
            'not become a combined event. Return coherent title, venue, city, dates/times, admission and '
            'a useful source-grounded 3-5 sentence description of what people can actually do or learn. '
            'Extract actual event dates rather than article publication dates, and note seasonal dates/opening '
            'windows when known. Preserve unknown schedules, prices and capacity as unknown. '
            'Classify admission as free, paid or unknown from explicit evidence; free-only requests need '
            'confirmed free entry, not merely a free registration link. Consider group size for suitability '
            'but never claim that enough tickets are available. Include a concrete activity_idea and '
            'quote event_evidence. Do not invent events, schedules, pricing or group discounts.')
        base = ' '.join(filter(None, [destination, topic, destination_country, date_hint, payload.get('dateTo') or '', ' '.join((payload.get('context') or '').split())[:120]]))
        if admission == 'free':
            base += ' free admission'
        elif admission == 'paid':
            base += ' entry tickets'
        # Keep location first so query length limits cannot cut it off; full preferences also guide extraction.
        batches = [
            (base+' individual events official tickets venue schedule', None),
            (base+' things to do seasonal experiences exhibitions markets tours official details', None),
            (base+' workshops learning community meetups activities registration', None),
        ]
        learning = re.search(r'learn|learning|workshop|course|class|lecture|seminar|tech|science|developer|coding|\bai\b|luma|lu\.ma',
                             ' '.join([topic, payload.get('context') or '', *interests]), re.I)
        if learning:
            batches.append((base+' learning workshop meetup registration', ['lu.ma', 'luma.com']))
        for query, domains in batches:
            spec['queries'].append({'key': 'events', 'kind': 'events', 'schema': 'event', 'num_results': 10,
                'query': query, 'include_domains': domains, 'user_location': destination_country or None,
                'forceRefresh': payload.get('forceRefresh', False), 'summary_query': summary,
                'event_min_results': 5,
                'event_refinement': base+' specific individual event or activity official detail booking page'})

    elif intent == "travel":
        dest, nights = extract_destination(q)
        if not dest:
            spec["missingFields"].append("destination")
        spec["destination"] = dest
        spec["nights"] = nights or 2
        origin = city or "my city"
        spec["queries"] += [
            {"key": "transport", "kind": "travel", "schema": "travel", "num_results": 5,
             "query": "flights or trains from %s to %s price" % (origin, dest),
             "summary_query": "Cheapest round-trip transport option and price"},
            {"key": "stay", "kind": "travel", "schema": "travel", "num_results": 5,
             "query": "best value places to stay in %s price per night" % dest,
             "summary_query": "Accommodation name, rating and price per night"},
            {"key": "do", "kind": "travel", "schema": "event", "num_results": 5,
             "query": "things to do in %s %s" % (dest, _month_year()),
             "summary_query": "Activity or event, when, where and price"},
            {"key": "social", "kind": "social", "schema": None, "num_results": 4,
             "query": "%s travel tips experience" % dest, "include_domains": regions.SOCIAL[:2]},
        ]

    elif intent == "products":
        keys = payload.get("keys") or []
        liked_attrs = payload.get("likedAttrs") or []
        terms = " ".join(dict.fromkeys([k for k in keys if not k.startswith("under ")] + liked_attrs[:3]))
        budget = next((k for k in keys if k.startswith("under ")), None)
        base = payload.get("productType") or q
        spec["queries"].append({
            "key": "products", "kind": "products", "schema": "product", "num_results": 8,
            "query": ("buy %s %s %s" % (base, terms, budget or "")).strip(),
            "summary_query": "Product name, price, store and key features",
            "include_domains": payload.get("domains") or None,
        })

    elif intent == "medicine":
        if not q:
            spec["missingFields"].append("symptom")
        spec["queries"].append({
            "key": "medicine", "kind": "medicine", "schema": "medicine", "num_results": 6,
            "query": "over the counter non-prescription medicine for %s buy online %s pharmacy price" % (q, user.get("country") or ""),
            "include_domains": regions.pharmacy_domains(user) or None,
            "summary_query": "Non-prescription product for %s: name, price, pharmacy and usage warning" % q,
        })

    elif intent == "wellbeing":
        mood = payload.get("mood") or "tired"
        spec["queries"].append({
            "key": "meals", "kind": "wellbeing", "schema": "meal", "num_results": 4,
            "query": "easy healthy recipe when feeling %s nutrition" % mood,
            "summary_query": "Recipe name, why it helps, preparation time",
        })

    elif intent == "interests":
        for topic in (payload.get("topics") or [])[:3]:
            spec["queries"].append({
                "key": topic, "kind": "interests", "schema": None, "num_results": 3,
                "query": "%s new or funny news %s" % (topic, city),
                "start_published_date": db.iso(db.now().replace(day=1)),
            })

    elif intent == "watch":
        spec["queries"].append({
            "key": "watch", "kind": "watch", "schema": "product", "num_results": 10,
            "query": "%s %s price buy %s" % (q, payload.get("details") or "", area),
            "summary_query": "Inspect ONE product for request: %s. Requirements: %s. Extract current full-item price_text, price_basis, explicit currency, exact name, technical attributes, actual image_urls and availability with availability_evidence. Exclude out-of-stock, preorder and unverified availability. Classify page_type; category/search pages are not offers. Assess request_match against ALL criteria including product type. Interpret natural language, translated names, units (16gb = 16 GB) and model families (50xx means 5000–5099). Distinguish system RAM from GPU VRAM. Quote match_evidence supporting requirements. Unknown when unsupported; omit price when absent." % (q, payload.get('details') or 'none'),
            "requirements": {"name": q, "details": payload.get('details') or ''}, "currency": regions.currency(user),
            "forceRefresh": payload.get('forceRefresh', False),
            "product_refinement": "%s %s specific product specifications price buy %s" % (q, payload.get('details') or '', area),
            "include_domains": payload.get("sites") or None,
        })

    for qq in spec["queries"]:
        qq.setdefault("user_location", bias)
    return spec
