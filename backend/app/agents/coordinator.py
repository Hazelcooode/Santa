"""Coordinator: turns a request into a validated TaskSpec.

Only public search terms go into queries: no names, health history or calendar
text. Location comes from the user's profile (city + country), so the same code
works for users anywhere; site_region / preferred_domains choose which local
websites to search."""
import re
from datetime import datetime

from .. import db, llm, regions

STOP = set("a an the and or for to in on at of with this that next my me i want find some any please near around from "
           "trip travel weekend winter summer spring autumn fall holiday holidays visit go going cheap".split())

INTENTS = ("groceries", "events", "travel", "products", "medicine", "wellbeing", "interests", "watch")


def _month_year():
    return datetime.utcnow().strftime("%B %Y")


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
        for it in items[:8]:  # budget: at most 8 priced lookups per run
            name = _clean_item_name(it["name"])
            spec["queries"].append({
                "key": it.get("id") or name, "kind": "prices", "schema": "price",
                "query": "%s price %s grocery" % (name, city), "include_domains": domains,
                "summary_query": "Current price of %s at this store" % name, "num_results": 6,
                "refine_without_domains": bool(domains),
            })
        spec["overflowItems"] = [i.get("id") for i in items[8:]]

    elif intent == "events":
        interests = payload.get("interests") or []
        topic = q or " ".join(interests[:2]) or "things to do"
        base = "%s events in %s %s" % (topic, city, _month_year())
        spec["queries"] += [
            {"key": "events", "kind": "events", "schema": "event", "query": base, "num_results": 7,
             "summary_query": "Event name, date, venue and ticket price",
             "start_published_date": None},
            {"key": "social", "kind": "social", "schema": None, "query": "%s %s recommendations" % (topic, city),
             "include_domains": regions.SOCIAL[:3], "num_results": 5},
        ]
        spec["interests"] = interests

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
            "key": "watch", "kind": "watch", "schema": "product", "num_results": 6,
            "query": "%s price buy" % q, "summary_query": "Exact product name, price, store",
            "include_domains": payload.get("sites") or None,
        })

    for qq in spec["queries"]:
        qq.setdefault("user_location", cc)
    return spec
