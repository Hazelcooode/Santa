"""Planner: deterministic ranking, totals and explanations over the ResearchBundle.

Rules: totals are computed in code, never by a model; a missing price stays
unknown (never invented); every recommendation keeps the source URLs that back
it. When the Researcher had no live data, the demo fixtures are used and the
response is labelled mode="demo"."""
import hashlib
import re
import math
from datetime import date

from .. import db, mock_data, regions
from ..exa_client import domain_of, sources_from, safe_url
from ..services.price_evidence import quote

ART_KEYS = [("jazz", "jazz"), ("music", "jazz"), ("concert", "jazz"), ("club", "jazz"), ("climb", "climb"), ("boulder", "climb"),
            ("hike", "climb"), ("sport", "climb"), ("market", "market"), ("christmas", "market"), ("food", "market"),
            ("design", "design"), ("art", "design"), ("museum", "design"), ("aurora", "aurora"), ("lapland", "aurora"),
            ("ski", "aurora"), ("ferry", "ferry"), ("boat", "ferry"), ("cruise", "ferry"), ("sea", "ferry")]


def _art_for(text):
    low = (text or "").lower()
    for k, v in ART_KEYS:
        if k in low:
            return v
    return "design"


def _tokens(s):
    return {w for w in re.findall(r"[a-zäöåü]+", (s or "").lower()) if len(w) > 2}


def _summary(c):
    return c["summary"] if isinstance(c.get("summary"), dict) else {}


def _num(v):
    try:
        f = float(v)
        return f if f > 0 and math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def plan(user, spec, bundle):
    fn = {
        "groceries": plan_groceries, "events": plan_events, "travel": plan_travel, "products": plan_products,
        "medicine": plan_medicine, "wellbeing": plan_wellbeing, "interests": plan_interests, "watch": plan_watch,
    }[spec["intent"]]
    return fn(user, spec, bundle)


# ------------------------------------------------------------------ groceries
STRATEGY_NOTES = {
    "multi": "Lowest price per item across the stores I found. More stops, lowest total.",
    "single": "Everything from one store.",
    "mall": "One trip: stores in the same mall or shopping centre.",
    "nearest": "Closest store. Costs a bit more but saves the walk.",
}


def user_stores(user):
    config = db.get_state(user["id"], "shopping_settings")
    if config and config.get("domains"):
        return [{"id": d, "name": regions.retailer_name(d), "domain": d, "url": "https://"+d, "mall": None, "dist": None} for d in config["domains"]]
    stores = db.get_state(user["id"], "stores")
    if stores:
        return stores
    return [{"id": d, "name": regions.retailer_name(d), "mall": None, "dist": None, "url": "https://www.%s/" % d, "domain": d}
            for d in regions.grocery_domains(user)]


def _lines_total(lines):
    return round(sum(l["price"] * l["qty"] for l in lines), 2)


def _choose(items, matrix, stores, strategy):
    """matrix[item_id][store_id] = price. Returns (lines, unpriced, note)."""
    by_id = {s["id"]: s for s in stores}
    lines, unpriced, note = [], [], STRATEGY_NOTES.get(strategy, "")

    def best_in(item, allowed):
        opts = [(p, sid) for sid, p in matrix.get(item["id"], {}).items() if sid in allowed]
        return min(opts) if opts else None

    if strategy == "nearest" and not any(s.get("dist") is not None for s in stores):
        return [], items, "Distances are unknown. Choose lowest known prices or one store instead."
    if strategy == "mall" and not any(s.get("mall") for s in stores):
        return [], items, "Shopping-centre membership is unknown. Choose one store or lowest known prices."
    if strategy == "single" or strategy == "nearest":
        if strategy == "nearest":
            ranked = sorted(stores, key=lambda s: (s.get("dist") is None, s.get("dist") or 0))
            pick = next((s for s in ranked if any(s["id"] in matrix.get(i["id"], {}) for i in items)), ranked[0] if ranked else None)
            others = []
        else:
            scored = []
            for s in stores:
                known = [i for i in items if s["id"] in matrix.get(i["id"], {})]
                tot = sum(matrix[i["id"]][s["id"]] * i["qty"] for i in known)
                scored.append((-len(known), tot, s))
            scored.sort(key=lambda x: (x[0], x[1]))
            pick = scored[0][2] if scored else None
            others = scored[1:2]
        for it in items:
            p = matrix.get(it["id"], {}).get(pick["id"]) if pick else None
            if p is None:
                unpriced.append(it)
            else:
                lines.append({"item": it, "qty": it["qty"], "store": pick["id"], "price": p})
        if strategy == "single" and others and others[0][0] == -len(lines):
            note += " Runner-up: %s (%s%.2f)." % (others[0][2]["name"], "€", others[0][1])
    else:
        if strategy == "mall":
            malls = {}
            for s in stores:
                malls.setdefault(s.get("mall") or ("solo:" + s["id"]), set()).add(s["id"])
            best_mall, best_key = None, None
            for mall, ids in malls.items():
                known = [best_in(i, ids) for i in items]
                cover = sum(1 for k in known if k)
                tot = sum(k[0] * i["qty"] for k, i in zip(known, items) if k)
                key = (-cover, -len(ids), tot)
                if best_key is None or key < best_key:
                    best_key, best_mall = key, mall
            allowed = malls.get(best_mall, set())
            if best_mall and not best_mall.startswith("solo:"):
                note = "One trip to %s, mixing the stores inside." % best_mall
        else:
            allowed = set(by_id)
        for it in items:
            b = best_in(it, allowed)
            if b:
                lines.append({"item": it, "qty": it["qty"], "store": b[1], "price": b[0]})
            else:
                unpriced.append(it)
    return lines, unpriced, note


def _deals_payload(items, matrix, stores, strategy, sources, mode):
    by_id = {s["id"]: s for s in stores}
    lines, unpriced, note = _choose(items, matrix, stores, strategy)
    plan, order = [], []
    for l in lines:
        if l["store"] not in order:
            order.append(l["store"])
    for sid in order:
        ls = [l for l in lines if l["store"] == sid]
        st = {k: v for k, v in by_id[sid].items() if k != "domain"}
        plan.append({"store": st, "lines": ls, "total": _lines_total(ls)})
    total = _lines_total(lines)
    # Savings vs buying the same lines at the nearest store (when it has a price).
    nearest = sorted(stores, key=lambda s: (s.get("dist") is None, s.get("dist") or 0))
    base = 0.0
    for l in lines:
        ref = matrix.get(l["item"]["id"], {}).get(nearest[0]["id"]) if nearest else None
        base += (ref if ref is not None else l["price"]) * l["qty"]
    if unpriced:
        note += " No reliable price found for: %s (kept on the list, not in the total)." % ", ".join(i["name"] for i in unpriced)
    total_minor = int(round(total * 100))
    return {
        "strategy": strategy, "total": total, "totalMinor": total_minor, "currency": "EUR",
        "saved": round(max(0.0, base - total), 2), "note": note.strip(), "plan": plan,
        "unpriced": [{"id": i["id"], "name": i["name"]} for i in unpriced],
        "hasUnknownCosts": bool(unpriced), "excludedCosts": ["delivery", "travel"],
        "sources": sources, "mode": mode,
        "summary": "%d store(s), %d priced, %d unpriced" % (len(plan), len(lines), len(unpriced)),
    }


def demo_deals(items, strategy):
    stores = mock_data.STORES
    matrix = {it["id"]: {s["id"]: mock_data.demo_price(it, s["id"]) for s in stores} for it in items}
    res = _deals_payload(items, matrix, stores, strategy, [], "demo")
    res["sources"] = [{"title": p["store"]["name"] + " weekly prices", "url": p["store"]["url"]} for p in res["plan"]] + \
                     [{"title": "Price comparison feed", "url": "https://www.ruokahinta.fi/"}]
    return res


def plan_groceries(user, spec, bundle):
    items = [dict(i, qty=float(i.get("qty") or 1)) for i in spec["payload"]["items"]]
    for it in items:
        if it["qty"].is_integer():
            it["qty"] = int(it["qty"])
        it.setdefault("id", hashlib.sha1(it["name"].encode()).hexdigest()[:8])
    strategy = spec["payload"].get("strategy") or "multi"
    if not bundle["available"]:
        return demo_deals(items, strategy)

    stores = list(user_stores(user))
    by_domain = {}
    for s in stores:
        by_domain.setdefault(s.get("domain") or domain_of(s.get("url", "")), []).append(s)
    matrix, used_sources, price_offers, diagnostics = {}, [], {}, []
    for it in items:
        for c in bundle["candidates"]:
            if c["key"] != it["id"] and c["key"] != it["name"]:
                continue
            allowed = regions.grocery_domains(user)
            if allowed and not any(c["domain"] == d or c["domain"].endswith("."+d) for d in allowed):
                continue
            s = _summary(c)
            def reject(reason):
                diagnostics.append({'itemId': it['id'], 'item': it['name'], 'url': c['url'], 'reason': reason})
            if s.get('page_type') in ('category', 'search', 'article'):
                reject('Category/search/article page, not an individual product offer.')
                continue
            minor, price_reason = quote(s, regions.currency(user), package=True)
            if price_reason:
                reject(price_reason)
                continue
            price = minor / 100
            from ..services.shopping_prices import match_failure
            failure=match_failure(dict(it,_strict=True),c)
            if failure:
                reject(failure)
                continue
            price_offers.setdefault(it["id"], []).append({"priceMinor": minor, "priceBasis": s.get("price_basis"), "currency": regions.currency(user),
                "store": s.get("store") or regions.retailer_name(c["domain"]), "url": c["url"], "product": s.get("product") or c["title"],
                "image": next((u for u in [c.get("image")]+(s.get("image_urls") or []) if safe_url(u)),None),
                "fetchedAt": c.get("fetchedAt") or db.iso(), "cached": c.get("cached", False), "evidence": (str(s.get("price_text") or "") + " (" + str(s.get("price_basis") or "") + ") " + (s.get("match_evidence") or " ".join(c.get("highlights") or [])))[:500]})
            dom = c["domain"]
            targets = by_domain.get(dom)
            if not targets:
                st = {"id": dom, "name": s.get("store") or regions.retailer_name(dom), "mall": None, "dist": None,
                      "url": "https://%s/" % dom, "domain": dom, "online": True}
                stores.append(st)
                by_domain[dom] = targets = [st]
            for st in targets:
                prev = matrix.setdefault(it["id"], {}).get(st["id"])
                if prev is None or price < prev:
                    matrix[it["id"]][st["id"]] = round(price, 2)
            used_sources.append({"title": (s.get("product") or c["title"])[:90] + " · " + dom, "url": c["url"]})
    res = _deals_payload(items, matrix, stores, strategy, sources_from(used_sources, 8), "live")
    for it in items:
        if not any(c.get('key') in (it['id'], it['name']) for c in bundle['candidates']):
            diagnostics.append({'itemId': it['id'], 'item': it['name'], 'reason': 'No product pages returned by the selected websites.'})
    res['storeCoverage'] = bundle.get('lookups', [])
    res['diagnostics'] = diagnostics[:100]
    res['inspectedSources'] = sources_from(bundle['sources'], 16)
    res["priceOffers"] = price_offers
    res["currency"] = regions.currency(user)
    if not matrix:
        res["note"] = "I couldn't find reliable online prices for these items right now. " + res["note"]
    return res


# --------------------------------------------------------------------- events
def _why(text, interests, query):
    low = (text or "").lower()
    for i in interests or []:
        if i and i.lower().split()[0] in low:
            return "Matches your interest in %s." % i
    return "Matches “%s”." % query if query else "Popular near you right now."


def _posts(bundle, key="social", limit=2):
    out = []
    for c in bundle["candidates"]:
        if c["key"] != key or not c["highlights"]:
            continue
        m = re.search(r"reddit\.com/(r/[^/]+)", c["url"])
        who = m.group(1) if m else "@" + c["domain"].split(".")[0]
        out.append({"who": who, "text": c["highlights"][0][:220], "url": c["url"]})
        if len(out) >= limit:
            break
    return out


def plan_events(user, spec, bundle):
    q = spec["payload"].get("query") or ""
    interests = spec.get("interests") or []
    if not bundle["available"]:
        lst = mock_data.clone(mock_data.EVENTS)
        ql, il = q.lower(), [i.lower() for i in interests]
        for e in lst:
            e["_s"] = sum(3 * (t in ql) + 2 * (t in il) for t in e["tags"]) + (3 if ql and ql in e["title"].lower() else 0)
        lst.sort(key=lambda e: -e["_s"])
        for e in lst:
            e.pop("_s")
        return {"results": lst[:20], "query": q, "summary": "%d demo events" % len(lst)}

    posts = _posts(bundle)
    today = date.today().isoformat()
    results, seen, diagnostics = [], set(), []
    for c in bundle["candidates"]:
        if c["key"] != "events":
            continue
        s = _summary(c)
        if s.get('event_page_type') not in ('single_event', 'activity'):
            diagnostics.append({'url':c['url'],'reason':'This is a listing, article or unverified event page. Only individual event pages or specific sourced activities are shown.'})
            continue
        title = (s.get("title") or c["title"]).strip()
        if not title or ' '.join(title.casefold().split()) in seen:
            continue
        if (q or spec.get('eventDestination')) and s.get('location_match') is not True:
            continue
        admission = s.get('admission') or 'unknown'
        price_text = (s.get('price_text') or '').strip()
        if admission == 'unknown' and re.fullmatch(r'(free|free admission|free entry|0(?:[.,]00)?(?:\s*(?:eur|euro|€))?)', price_text, re.I):
            admission = 'free'
        requested_admission = spec['payload'].get('admission') or 'any'
        if requested_admission != 'any' and admission != requested_admission:
            diagnostics.append({'url': c['url'], 'reason': 'The requested admission type is not confirmed by this source.'})
            continue
        if spec['payload'].get('people') and s.get('group_suitable') is False:
            diagnostics.append({'url': c['url'], 'reason': 'The source rules do not suit the requested group size.'})
            continue
        event_end = s.get('end_date') or s.get('start_date') or '9999'
        if spec['payload'].get('dateFrom') and event_end < spec['payload']['dateFrom']:
            continue
        if spec['payload'].get('dateTo') and (s.get('start_date') or '') > spec['payload']['dateTo']:
            continue
        if event_end < today:
            continue  # already happened
        seen.add(' '.join(title.casefold().split()))
        where = ", ".join(x for x in (s.get("venue"), s.get("city")) if x) or spec.get("city") or ""
        text = " ".join([title, s.get("category") or "", s.get("summary") or ""])
        results.append({
            "id": "ev_" + hashlib.sha1(c["url"].encode()).hexdigest()[:10],
            "title": title[:120], "when": s.get("date_text") or "Check source for dates/opening times", "where": where[:80],
            "startDate": s.get('start_date') or '', "endDate": s.get('end_date') or s.get('start_date') or '',
            "startTime": s.get('start_time') or '', "endTime": s.get('end_time') or '', "city": s.get('city') or '', "country": s.get('country') or '',
            "price": s.get("price_text") or "See source", "tags": [t for t in [s.get("category")] if t],
            "why": _why(text, interests, q), "summary": s.get("summary") or (c["highlights"] or [""])[0][:200],
            "art": _art_for(text), "images": [c["image"]] if c.get("image") else [],
            "activityIdea": s.get("activity_idea") or "", "admission": admission,
            "posts": posts[:1], "sources": [{"title": c["title"][:90], "url": c["url"]}] + [{"title": "Social post", "url": p["url"]} for p in posts[:1]],
            "url": c["url"], "eventPageType":s.get("event_page_type"), "evidence":s.get("event_evidence") or "",
        })
    return {"results": results[:20], "query": q, "diagnostics":diagnostics[:20],
            "notice":"Up to 20 individual events and specific activity ideas. Dates, admission and group capacity require checking with the source; fewer results means fewer qualifying matches were found.",
            "summary": "%d event and activity suggestions" % len(results[:20])}


# --------------------------------------------------------------------- travel
def plan_travel(user, spec, bundle):
    q = spec["payload"].get("query") or ""
    if not bundle["available"]:
        return {"results": mock_data.clone(mock_data.TRAVEL), "query": q, "summary": "demo trips"}
    dest = spec.get("destination") or q
    nights = int(spec.get("nights") or 2)

    def best(key, kinds=None):
        opts = []
        for c in bundle["candidates"]:
            if c["key"] != key:
                continue
            s = _summary(c)
            if kinds and s.get("kind") not in kinds:
                continue
            opts.append((_num(s.get("price")) or 1e9, s, c))
        opts.sort(key=lambda x: x[0])
        return opts

    transport = best("transport", {"flight", "train", "ferry", "bus", "other", None})
    stays = best("stay", {"stay", "other", None})
    acts = [c for c in bundle["candidates"] if c["key"] == "do"]
    posts = _posts(bundle)
    images = [c["image"] for c in bundle["candidates"] if c.get("image")][:5]
    details, srcs, total = [], [], 0.0
    if transport:
        p, s, c = transport[0]
        cur = s.get("currency") or ""
        details.append({"k": (s.get("kind") or "Transport").capitalize(), "v": "%s%s" % (s.get("title") or c["title"],
                        (" · %s %.0f" % (cur, p)) if p < 1e9 else "")})
        srcs.append({"title": c["title"][:80], "url": c["url"]})
        total += p if p < 1e9 else 0
    if stays:
        p, s, c = stays[0]
        details.append({"k": "Stay", "v": "%s%s" % (s.get("title") or c["title"], (" · %.0f/night" % p) if p < 1e9 else "")})
        srcs.append({"title": c["title"][:80], "url": c["url"]})
        total += p * nights if p < 1e9 else 0
    if acts:
        s = _summary(acts[0])
        details.append({"k": "Do", "v": (s.get("title") or acts[0]["title"])[:100]})
        srcs.append({"title": acts[0]["title"][:80], "url": acts[0]["url"]})
    trip = {
        "id": "tr_" + hashlib.sha1(dest.encode()).hexdigest()[:10],
        "title": "%s: %d nights" % (dest.title(), nights), "kind": "trip",
        "when": "Next available dates", "where": "%s → %s" % (spec.get("city") or "You", dest.title()),
        "price": ("from %.0f %s total" % (total, spec.get("currency"))) if total else "Prices on source pages",
        "why": "Built from live listings for %s." % dest, "art": _art_for(dest + " " + q), "details": details,
        "images": images, "posts": posts[:2], "sources": srcs + [{"title": "Traveller post", "url": p["url"]} for p in posts[:1]],
    }
    results = [trip]
    for c in acts[1:4]:
        s = _summary(c)
        results.append({
            "id": "tr_" + hashlib.sha1(c["url"].encode()).hexdigest()[:10],
            "title": (s.get("title") or c["title"])[:110], "kind": "activity",
            "when": s.get("date_text") or "Flexible", "where": s.get("venue") or dest.title(),
            "price": s.get("price_text") or "See source", "why": s.get("summary") or "Popular in %s." % dest.title(),
            "art": _art_for((s.get("title") or "") + " " + dest), "images": [c["image"]] if c.get("image") else [],
            "posts": [], "sources": [{"title": c["title"][:80], "url": c["url"]}],
        })
    return {"results": results, "query": q, "destination": dest, "summary": "trip to %s" % dest}


# ------------------------------------------------------------------- products
def score_products(products, keys, liked_attrs, disliked_attrs, disliked_ids):
    max_price = None
    for k in keys:
        m = re.match(r"under [€$£]?(\d+)", k)
        if m:
            max_price = int(m.group(1))
    out = []
    for p in products:
        attrs = [a.lower() for a in p.get("attrs", [])]
        text = (p["title"] + " " + " ".join(attrs)).lower()
        s = 0.0
        matched = [k for k in keys if not k.startswith("under ") and k.lower() in text]
        s += 2 * len(matched)
        s += sum(0.8 * liked_attrs.get(a, 0) - 1.2 * disliked_attrs.get(a, 0) for a in attrs)
        if max_price and p.get("price") and p["price"] > max_price:
            s -= 4
        if p["id"] in disliked_ids:
            s -= 10
        out.append(dict(p, score=round(s, 2), matched=matched))
    out.sort(key=lambda x: -x["score"])
    return out


def plan_products(user, spec, bundle):
    pl = spec["payload"]
    keys = pl.get("keys") or []
    if not bundle["available"]:
        products = [dict(p, sources=[mock_data.src(p["store"] + " product page", p["url"]),
                                     mock_data.src("Review roundup", "https://www.reddit.com/r/BuyItForLife/")])
                    for p in mock_data.clone(mock_data.PRODUCTS)]
    else:
        products, seen = [], set()
        for i, c in enumerate(c for c in bundle["candidates"] if c["key"] == "products"):
            s = _summary(c)
            title = (s.get("title") or c["title"]).strip()[:100]
            if title.lower() in seen:
                continue
            seen.add(title.lower())
            products.append({
                "id": "p_" + hashlib.sha1(c["url"].encode()).hexdigest()[:10],
                "title": title, "price": round(_num(s.get("price")) or 0, 2) or None,
                "currency": s.get("currency") or regions.currency(user),
                "store": s.get("store") or c["domain"], "attrs": [a.lower()[:30] for a in (s.get("attributes") or [])][:8],
                "art": "boot%d" % (i % 6 + 1), "image": c.get("image"), "url": c["url"],
                "sources": [{"title": c["title"][:80], "url": c["url"]}],
            })
    ranked = score_products(products, keys, pl.get("likedAttrMap") or {}, pl.get("dislikedAttrMap") or {}, set(pl.get("disliked") or []))
    for p in ranked:
        if p.get("price") is None:
            p["price"] = 0  # frontend renders numbers; 0 + priceKnown=false means "see store"
            p["priceKnown"] = False
    return {"results": ranked, "summary": "%d products" % len(ranked)}


# ------------------------------------------------------------------- medicine
SYMPTOM_KEYS = [("throat", r"throat|cough"), ("head", r"head|pain|ache|fever"), ("sleep", r"sleep|insomnia"), ("cold", r".")]


def plan_medicine(user, spec, bundle):
    q = spec["payload"].get("query") or ""
    disclaimer = "Over-the-counter options only. Ask a pharmacist if unsure and see a doctor if symptoms last."
    if not bundle["available"]:
        key = next(k for k, rx in SYMPTOM_KEYS if re.search(rx, q.lower()))
        lst = [dict(m, sources=[mock_data.src(m["pharmacy"] + " — product info", "https://www.yliopistonapteekki.fi/"),
                                mock_data.src("Fimea medicine info", "https://www.fimea.fi/")]) for m in mock_data.clone(mock_data.MEDS[key])]
        return {"results": lst, "disclaimer": disclaimer, "summary": "demo medicines"}
    out, seen = [], set()
    for c in bundle["candidates"]:
        s = _summary(c)
        if not s.get("name") or s.get("otc") is not True:
            continue  # never suggest prescription-only products
        name = s["name"].strip()[:100]
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "price": round(_num(s.get("price")) or 0, 2), "priceKnown": bool(_num(s.get("price"))),
                    "currency": s.get("currency") or regions.currency(user),
                    "pharmacy": s.get("pharmacy") or c["domain"], "eta": "check at checkout",
                    "note": (s.get("usage_note") or "Read the leaflet before use.")[:200], "url": c["url"],
                    "sources": [{"title": c["title"][:80], "url": c["url"]}]})
    return {"results": out[:5], "disclaimer": disclaimer, "summary": "%d OTC options" % len(out[:5])}


# ------------------------------------------------------------------ wellbeing
def plan_wellbeing(user, spec, bundle):
    mood = spec["payload"].get("mood") or "tired"
    meals = mock_data.clone(mock_data.MEALS.get(mood, mock_data.MEALS["tired"]))
    acts = mock_data.ACTIVITIES.get(mood, mock_data.ACTIVITIES["tired"])
    sources = list(mock_data.WELLBEING_SOURCES)
    if bundle["available"]:
        live = []
        for c in bundle["candidates"]:
            s = _summary(c)
            if s.get("title"):
                t = _num(s.get("time_minutes"))
                live.append({"title": s["title"][:80], "why": (s.get("why") or "Balanced and easy to make")[:120],
                             "time": "%d min" % t if t else "—", "url": c["url"]})
        if live:
            meals = live[:3]
            sources = sources_from(bundle["sources"], 3)
    return {"meals": meals, "activities": acts, "sources": sources, "summary": "%d meals" % len(meals)}


# ------------------------------------------------------------------ interests
def plan_interests(user, spec, bundle):
    posts = []
    if bundle["available"]:
        for key, out in bundle["byKey"].items():
            r = next((r for r in out["results"] if r.get("highlights")), None)
            if r:
                posts.append({"topic": key, "text": "Saw this and thought of you (%s): %s" % (key, r["title"][:120]),
                              "sources": [{"title": r["title"][:80], "url": r["url"]}]})
    return {"posts": posts, "summary": "%d finds" % len(posts)}


# ---------------------------------------------------------------------- watch
def plan_watch(user, spec, bundle):
    offers, diagnostics = [], []
    for c in bundle["candidates"]:
        s = _summary(c)
        minor, price_reason = quote(s, regions.currency(user))
        title = (s.get("title") or c["title"])[:100]
        from ..services.shopping_prices import matches
        required = spec["payload"].get("details") or ""
        if spec["payload"].get("mode") == "exact":
            required = spec["payload"]["query"] + " " + required
        candidate = dict(c, summary=dict(s, product=title))
        allowed = spec['payload'].get('sites') or []
        if allowed and not any(c['domain'] == d or c['domain'].endswith('.'+d) for d in allowed):
            reason = 'Source is outside your selected websites.'
        elif s.get('page_type') in ('category', 'search', 'article'):
            reason = 'Category/search/article page, not an individual product offer.'
        elif price_reason:
            reason = price_reason
        elif s.get('availability') != 'in_stock' or not s.get('availability_evidence'):
            reason = 'This exact option is not confirmed available to buy now.'
        elif not matches({'name': spec['payload']['query'], 'details': required}, candidate):
            reason = 'Product type or required specifications did not match, or could not be verified.'
        else:
            reason = None
        if reason:
            diagnostics.append({'url': c['url'], 'title': title, 'reason': reason})
        else:
            offers.append({"title": title, "priceMinor": minor,
                           "currency": regions.currency(user), "store": s.get("store") or c["domain"],
                           "url": c["url"], "availability": "in_stock", "availabilityEvidence": s.get("availability_evidence"), "priceText": s.get("price_text"), "priceBasis": s.get("price_basis"),
                           "images": list(dict.fromkeys([u for u in ([c.get("image")] + (s.get("image_urls") or [])) if safe_url(u)]))[:12],
                           "evidence": s.get("match_evidence") or ""})
    offers.sort(key=lambda o: o["priceMinor"])
    return {"offers": offers, "diagnostics": diagnostics[:20], "inspectedSources": sources_from(bundle['sources'], 16),
            "notice": 'Found matching price quotes.' if offers else 'No verified matching price found. History records successful quotes only; category pages, missing prices and unsupported requirements are excluded.',
            "summary": "%d offers" % len(offers)}
