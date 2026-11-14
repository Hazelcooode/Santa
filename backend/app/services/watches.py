"""Price watches (docs/price-watch.md): saved searches or exact items, a target
price, scheduled + manual checks through the agents, immutable observation
history and de-duplicated alerts. Thresholds are deterministic code."""
from datetime import timedelta
import hashlib
import hmac
import secrets
import base64
import time

from .. import agents, db, search_scope
from ..errors import ApiError
from ..config import settings
from ..exa_client import domain_of

MAX_WATCHES = 50


def cadence(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 720:
        raise ApiError(400, "INVALID_CADENCE", "Use 0 for manual-only checks, or 1–720 hours for automatic checks.")
    return value


def _public(row):
    d = db.loads(row["data"], {})
    d.pop('diagnostics',None)
    for check in d.get('checks',[]):check.pop('diagnostics',None)
    from . import media
    for key in ('savedOptions','lastOffers'):
        for offer in d.get(key,[]):
            offer['thumbnail']=media.image_thumbnail(next(iter(offer.get('images') or []),None))
    obs = db.q("SELECT at,price_minor AS priceMinor,currency,title,url,store FROM price_observations WHERE watch_id=? ORDER BY at DESC, price_minor ASC LIMIT 1",
               (row["id"],))
    if obs and d.get('pricingVersion') != 2:
        obs=[]
        d['checkNotice']='Previous quotes need a new price check after the package-price validation update. Historical observations are retained as originally recorded.'
    return dict(d, id=row["id"], status=row["status"], version=row["version"], createdAt=row["created_at"], updatedAt=row["updated_at"],
                latest=obs[0] if obs else None)


def list_watches(user):
    return {"items": [_public(r) for r in db.q("SELECT * FROM price_watches WHERE user_id=? ORDER BY created_at DESC", (user["id"],))],
            "nextCursor": None}


def get(user, wid):
    row = db.q1("SELECT * FROM price_watches WHERE id=? AND user_id=?", (wid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Watch not found.")
    return row


def create(user, body):
    n = db.q1("SELECT COUNT(*) AS n FROM price_watches WHERE user_id=?", (user["id"],))["n"]
    if n >= MAX_WATCHES:
        raise ApiError(422, "LIMIT_REACHED", "You can keep up to %d watches." % MAX_WATCHES)
    query = (body.get("query") or body.get("name") or "").strip()[:160]
    if not query:
        raise ApiError(400, "INVALID_INPUT", "What should I watch?")
    sites = [domain_of(s if "://" in s else "https://"+s) for s in body.get("sites") or []]
    if settings.data_mode == "live" and (not body.get("city") or not body.get("country") ):
        raise ApiError(422,"SEARCH_SETTINGS_REQUIRED","Choose a city and country for this watch; websites are optional.")
    scope = body.get("searchScope", "country")
    countries = body.get("searchCountries") or []
    if body.get("country") or scope != "country" or countries:
        _, scope, countries = search_scope.validate(body.get("country"), scope, countries)
    data = {"searchScope": scope, "searchCountries": countries, "mode": body.get("mode") or "explore", "city": body.get("city") or "", "country": (body.get("country") or "").upper(), "details": body.get("details") or "", "query": query, "category": body.get("category"), "targetMinor": body.get("targetMinor"),
            "currency": body.get("currency") or user.get("currency") or "EUR", "sites": sites[:10],
            "cadenceHours": cadence(body.get("cadenceHours", 24)), "buyBy": body.get("buyBy"),
            "notify": bool(body.get("notify", True)), "alerts": [], "checkState": "idle", "lastCheckedAt": None}
    wid = db.new_id("pw_")
    db.run("INSERT INTO price_watches(id,user_id,data,status,version,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
           (wid, user["id"], db.dumps(data), "active", 1, db.iso(), db.iso()))
    return _public(get(user, wid))


def update(user, wid, body):
    row = get(user, wid)
    if body.get("expectedVersion") is not None and int(body["expectedVersion"]) != row["version"]:
        raise ApiError(409, "VERSION_CONFLICT", "This watch changed elsewhere.")
    data = db.loads(row["data"], {})
    status = row["status"]
    if "paused" in body:
        status = "paused" if body["paused"] else "active"
    if "targetMinor" in body:
        data["targetMinor"] = body["targetMinor"]
        data["alerts"] = []  # re-arm
    if "cadenceHours" in body:
        cadence(body["cadenceHours"])
    for k in ("query", "sites", "cadenceHours", "notify", "buyBy"):
        if k in body:
            data[k] = body[k]
    db.run("UPDATE price_watches SET data=?, status=?, version=version+1, updated_at=? WHERE id=?", (db.dumps(data), status, db.iso(), wid))
    return _public(get(user, wid))


def delete(user, wid):
    get(user, wid)
    db.run("DELETE FROM price_observations WHERE watch_id=? AND user_id=?", (wid, user["id"]))
    db.run("DELETE FROM price_watches WHERE id=?", (wid,))


def check(user, wid, automatic=False):
    row = get(user, wid)
    data = db.loads(row["data"], {})
    if automatic and data.get("cadenceHours", 24) == 0:
        return dict(_public(row), skipped=True, reason="Manual-only watch; no research started.")
    if row["status"] != "active":
        raise ApiError(409,"WATCH_PAUSED","Resume this watch before checking prices.")
    if data.get("buyBy") and data["buyBy"] < db.now().date().isoformat():
        raise ApiError(410,"WATCH_EXPIRED","This watch's buy-by date has passed.")
    research_user = dict(user, city=data.get("city") or user.get("city"), country=data.get("country") or user.get("country"), site_region=data.get("country") or user.get("site_region"), currency=data["currency"], search_scope=data.get("searchScope", "country"), search_countries=data.get("searchCountries") or [])
    try:
        res = agents.run(research_user, "watch", {"query": data["query"], "sites": data.get("sites"), "details": data.get("details"), "mode": data.get("mode"), 'forceRefresh': not automatic})
    except ApiError as error:
        data['lastCheckedAt'] = db.iso()
        data['checkState'] = 'error'
        data['checkNotice'] = str(error)
        data['checks'] = ([{'at': data['lastCheckedAt'], 'status': 'error', 'notice': str(error)}] + data.get('checks', []))[:20]
        db.run('UPDATE price_watches SET data=?, updated_at=? WHERE id=?', (db.dumps(data), db.iso(), wid))
        raise
    offers = res.get("offers") or []
    data["modeResult"] = res.get("mode")
    data["lastCheckedAt"] = db.iso()
    for offer in offers:
        offer['id'] = 'opt_' + hashlib.sha256(offer['url'].encode()).hexdigest()[:16]
        offer['checkedAt'] = data['lastCheckedAt']
        from . import media
        offer['thumbnail'] = media.image_thumbnail(next(iter(offer.get('images') or []),None))
    if offers:
        if data.get('savedOptions'):
            data['savedOptions']=offers[:data.get('saveCount') or len(data['savedOptions'])]
        data.pop('lastOffers',None)
    data['checkNotice'] = res.get('notice') or ('Found matching quotes.' if offers else 'No matching quote found. No new price was added to history.')
    diagnostics = res.get('diagnostics') or []
    data.pop('diagnostics',None)
    for attempt in data.get('checks',[]):attempt.pop('diagnostics',None)
    if not offers:
        data["checkState"] = "stale" if data.get("lastPriceMinor") else ("partial" if res.get("mode") == "demo" else "no_matches")
    else:
        best = offers[0]
        data["checkState"] = "ready"
        data["lastPriceMinor"] = best["priceMinor"]
        data["pricingVersion"] = 2
        for offer in (data.get('savedOptions') or offers)[:10]:
            db.run("INSERT INTO price_observations(id,user_id,watch_id,at,price_minor,currency,title,url,store) VALUES(?,?,?,?,?,?,?,?,?)",
                   (db.new_id("po_"), user["id"], wid, data['lastCheckedAt'], offer["priceMinor"], offer["currency"], offer["title"], offer["url"], offer["store"]))
        tgt = data.get("targetMinor")
        if tgt and best["priceMinor"] <= tgt and not data.get("alerts"):
            data["alerts"] = [{"at": db.iso(), "priceMinor": best["priceMinor"], "url": best["url"], "store": best["store"]}]
    data['checks'] = ([{'at': data['lastCheckedAt'], 'status': data['checkState'], 'notice': data['checkNotice'],
                       'offerCount': len(offers)}] + data.get('checks', []))[:20]
    db.run("UPDATE price_watches SET data=?, updated_at=? WHERE id=?", (db.dumps(data), db.iso(), wid))
    return dict(_public(get(user, wid)), offers=offers[:10], diagnostics=diagnostics, saveToken=_proof(user,_watch_spec(data),offers), mode=res.get("mode"))


def history(user, wid):
    row = get(user, wid)
    return {"items": db.q("SELECT at,price_minor AS priceMinor,currency,title,url,store FROM price_observations WHERE watch_id=? AND user_id=? ORDER BY at",
                          (wid, user["id"])), 'checks': db.loads(row['data'], {}).get('checks', []),
            'notice': 'Price history starts with the first successful matching quote; it does not retrieve historical website prices. Recent check attempts are shown separately (up to 20).'}


def due(now=None):
    now = now or db.now()
    out = []
    for r in db.q("SELECT * FROM price_watches WHERE status='active'"):
        d = db.loads(r["data"], {})
        interval = d.get("cadenceHours", 24)
        if not isinstance(interval, int) or interval <= 0 or interval > 720:
            continue
        if d.get("buyBy") and d["buyBy"] < now.date().isoformat():
            continue
        last = db.parse_iso(d.get("lastCheckedAt")) if d.get("lastCheckedAt") else None
        if not last or now - last >= timedelta(hours=interval):
            out.append(r)
    return out


def save_options(user, wid, count, name=None):
    if not str(name or '').strip():
        raise ApiError(400,'LIST_NAME_REQUIRED','Name this saved list before saving results.')
    if count not in (1, 5, 10):
        raise ApiError(400, 'INVALID_INPUT', 'Choose 1, 5 or 10 options.')
    row=get(user,wid); data=db.loads(row['data'], {})
    offers=data.get('savedOptions') or data.get('lastOffers') or []
    if not offers:
        raise ApiError(409, 'NO_OPTIONS', 'Run a successful price check first.')
    data['savedOptions']=offers[:count]
    data['name']=str(name).strip()[:120]
    data['saveCount']=count
    db.run('UPDATE price_watches SET data=?,updated_at=? WHERE id=?', (db.dumps(data),db.iso(),wid))
    return _public(get(user,wid))


def rotate_option(user, wid, oid):
    from . import visual_previews
    return visual_previews.start(user, {'kind': 'turn', 'watchId': wid, 'optionId': oid})


_PROOF_KEY=secrets.token_bytes(32)


def _proof(user,spec,offers):
    raw=db.dumps({'user':user['id'],'spec':spec,'offers':offers[:10],'expires':time.time()+1800}).encode()
    encoded=base64.urlsafe_b64encode(raw).decode()
    return encoded+'.'+hmac.new(_PROOF_KEY,encoded.encode(),hashlib.sha256).hexdigest()


def research(user,body):
    """An unsaved request: diagnostics and drafts never enter watch storage."""
    from . import media
    spec=dict(body)
    if not spec.get('query') or not spec.get('city') or not spec.get('country'):
        raise ApiError(422,'SEARCH_SETTINGS_REQUIRED','Choose the item, city and country for this search.')
    country,scope,countries=search_scope.validate(spec['country'],spec.get('searchScope','country'),spec.get('searchCountries'))
    person=dict(user,city=spec['city'],country=country,site_region=country,currency=spec.get('currency') or 'EUR',search_scope=scope,search_countries=countries)
    res=agents.run(person,'watch',dict(spec,forceRefresh=True))
    offers=res.get('offers') or []
    for offer in offers:
        offer['id']='opt_'+hashlib.sha256(offer['url'].encode()).hexdigest()[:16]
        offer['checkedAt']=db.iso()
        offer['thumbnail']=media.image_thumbnail(next(iter(offer.get('images') or []),None))
    return dict(res,offers=offers[:10],saveToken=_proof(user,spec,offers))


def save_research(user,name,count,token,cadence_hours=0):
    name=str(name or '').strip()
    if not name:raise ApiError(400,'LIST_NAME_REQUIRED','Enter a name for this saved list.')
    if count not in (1,5,10):raise ApiError(400,'INVALID_INPUT','Choose 1, 5 or 10 results.')
    proof=research_proof(user,token)
    if not proof['offers']:raise ApiError(409,'NO_OPTIONS','No qualifying offers are available to save.')
    spec=dict(proof['spec'],cadenceHours=cadence(cadence_hours))
    created=create(user,spec);row=get(user,created['id']);data=db.loads(row['data'],{})
    data.update(name=name[:120],savedOptions=proof['offers'][:count],saveCount=count,lastCheckedAt=db.iso(),checkState='ready',pricingVersion=2,lastPriceMinor=proof['offers'][0]['priceMinor'])
    db.run('UPDATE price_watches SET data=? WHERE id=?',(db.dumps(data),row['id']))
    for offer in data['savedOptions']:
        db.run('INSERT INTO price_observations(id,user_id,watch_id,at,price_minor,currency,title,url,store) VALUES(?,?,?,?,?,?,?,?,?)',
            (db.new_id('po_'),user['id'],row['id'],data['lastCheckedAt'],offer['priceMinor'],offer['currency'],offer['title'],offer['url'],offer['store']))
    return _public(get(user,row['id']))


def _watch_spec(data):
    keys=('query','category','mode','city','country','searchScope','searchCountries','details','targetMinor','currency','sites','cadenceHours','buyBy','notify')
    return {key:data[key] for key in keys if key in data}


def research_proof(user,token):
    try:
        encoded,signature=token.rsplit('.',1)
        if not hmac.compare_digest(signature,hmac.new(_PROOF_KEY,encoded.encode(),hashlib.sha256).hexdigest()):raise ValueError()
        proof=db.loads(base64.urlsafe_b64decode(encoded))
        if proof['user']!=user['id'] or proof['expires']<time.time():raise ValueError()
    except (ValueError,KeyError,TypeError):
        raise ApiError(410,'RESEARCH_EXPIRED','This temporary result expired. Run the price search again.')
    return proof
