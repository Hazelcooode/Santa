"""Life treatment: events, trips and explicit product searches.

Product search remembers which results the user liked/disliked (by id) and
turns that into attribute weights for the next round, so the strategy iterates
with feedback. A reference photo is analysed on-device; the backend accepts the
detected features (`imageFeatures`), or, if the client sends the image itself,
extracts colour (Cloudinary) / features (optional vision model)."""
import re

from .. import agents, db, llm, mock_data
from ..errors import ApiError
from . import media


def _interests(user, given):
    if given:
        return [str(x)[:40] for x in given][:8]
    rows = db.q("SELECT text FROM memories WHERE user_id=? ORDER BY created_at DESC LIMIT 5", (user["id"],))
    return [r["text"] for r in rows]


def explore(user, query, kind="events", interests=None, **location):
    if kind not in ("events", "travel"):
        raise ApiError(400, "INVALID_INPUT", "kind must be events or travel.")
    q = (query or "").strip()[:200]
    res = agents.run(user, "events" if kind == "events" else "travel",
                     {"query": q or ("Lapland this winter" if kind == "travel" else ""), "interests": _interests(user, interests), "forceRefresh": True, **location})
    if res.get("status") == "clarifying":
        raise ApiError(422, "CLARIFICATION_NEEDED", "Where would you like to go?", details={"missingFields": res["missingFields"]})
    from . import plans
    res['searchId'] = plans.remember_search(user, q, kind, res)
    return res


def _remember_products(user, results):
    for p in results:
        db.run("INSERT OR REPLACE INTO products_seen(id,user_id,data,created_at) VALUES(?,?,?,?)",
               (p["id"], user["id"], db.dumps({k: p[k] for k in ("id", "title", "attrs", "price", "store", "url") if k in p}), db.iso()))


def _attr_map(user, ids):
    out = {}
    if not ids:
        return out
    rows = db.q("SELECT data FROM products_seen WHERE user_id=? AND id IN (%s)" % ",".join("?" * len(ids)), (user["id"], *ids))
    for r in rows:
        for a in db.loads(r["data"], {}).get("attrs", []):
            out[a] = out.get(a, 0) + 1
    return out


def extract_keys(query):
    if llm.available():
        out = llm.complete("Extract what the shopper wants. Reply JSON {\"productType\": string, \"keys\": [short lowercase features], "
                           "\"maxPrice\": number|null}. Features are 1-2 words (e.g. waterproof, black, lined).",
                           [("user", query)], want_json=True, temperature=0)
        if isinstance(out, dict) and isinstance(out.get("keys"), list):
            keys = [str(k).lower()[:24] for k in out["keys"]][:8]
            if out.get("maxPrice"):
                keys.append("under €%d" % int(out["maxPrice"]))
            return keys, out.get("productType")
    keys = mock_data.extract_keys(query)
    words = [w for w in re.findall(r"[a-zA-Z]+", query.lower()) if len(w) > 3 and w not in {"under", "with", "that", "need", "want", "looking"}]
    ptype = " ".join(w for w in words if w not in " ".join(keys))[:60] or None
    return (keys or ["good value"]), ptype


def image_features(user, image):
    """`image` may be a list of feature strings (on-device) or a data: URL."""
    if isinstance(image, list):
        return [str(x).lower()[:24] for x in image][:6]
    if isinstance(image, str) and image.startswith("data:image"):
        if llm.available():
            out = llm.complete("List up to 5 short visual product features (colour, material, style) as JSON {\"features\": [..]}.",
                               [("user", "What features does this product have?")], want_json=True, image_data_url=image, temperature=0)
            if isinstance(out, dict) and out.get("features"):
                return [str(x).lower()[:24] for x in out["features"]][:5]
        color = media.dominant_color(user, image)
        if color:
            return [color]
    return []


def find_products(user, query, keys=None, liked=None, disliked=None, round_=1, image=None, image_features_list=None):
    q = (query or "").strip()[:300]
    if not q and not keys:
        raise ApiError(400, "INVALID_INPUT", "Describe what you're looking for.")
    ptype = None
    if keys:
        keys = [str(k)[:30] for k in keys][:10]
        ptype = db.get_state(user["id"], "product_type")
    else:
        keys, ptype = extract_keys(q)
        db.set_state(user["id"], "product_type", ptype)
    # image=True means the photo stayed on the device and no features were sent.
    feats = image_features_list or (image_features(user, image) if image and image is not True else [])
    for f in feats:
        if f not in keys:
            keys.append(f)
    liked, disliked = list(liked or [])[:20], list(disliked or [])[:20]
    liked_map, disliked_map = _attr_map(user, liked), _attr_map(user, disliked)
    top_liked = [a for a, _ in sorted(liked_map.items(), key=lambda kv: -kv[1]) if a not in disliked_map][:3]
    res = agents.run(user, "products", {"query": q, "keys": keys, "productType": ptype or q, "likedAttrs": top_liked if round_ > 1 else [],
                                        "likedAttrMap": liked_map, "dislikedAttrMap": disliked_map, "disliked": disliked})
    _remember_products(user, res["results"])
    if round_ <= 1:
        strategy = 'Searched: "%s"%s' % (" + ".join(keys), " + visual match from your photo" if feats or image else "")
    else:
        strategy = "Round %d: boosted %s, filtered what you didn't like" % (round_, ", ".join(top_liked) if top_liked else "what you liked")
    return {"keys": keys, "results": res["results"], "strategy": strategy, "mode": res.get("mode"), "notice": res.get("notice"),
            "imageFeatures": feats}
