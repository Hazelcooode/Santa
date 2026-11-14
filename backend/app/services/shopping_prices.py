"""Persist sourced quotes against exact item requirements and explicit shop context."""
import hashlib
import re
import threading
import unicodedata
from datetime import timedelta

from .. import db, exa_client, search_scope
from ..config import settings
from ..errors import ApiError
from . import product_media

_locks = {}
_guard = threading.Lock()


def normalise(text):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower()) if not unicodedata.combining(c))
    text = re.sub(r'(\d)\s+(gb|tb|mb|kg|ml|hz|g|l)\b', r'\1\2', text)
    return ' '.join(re.findall(r'[a-z0-9]+', text))


def identity(item):
    return hashlib.sha256(db.dumps([item.get('name'), item.get('brand') or '', item.get('details') or '', item.get('attributes') or {}]).encode()).hexdigest()


def context_hash(user):
    config = dict(get_settings(user), pricingVersion=3)
    if config.get('shopMode') == 'selected':
        config.pop('shopMode', None)
    if config.get('searchScope', 'country') == 'country' and not config.get('searchCountries'):
        config.pop('searchScope', None)
        config.pop('searchCountries', None)
    return hashlib.sha256(db.dumps(config).encode()).hexdigest()


def get_settings(user):
    data = db.get_state(user['id'], 'shopping_settings', {'city': '', 'country': '', 'currency': 'EUR', 'domains': []})
    return dict(data, shopMode=data.get('shopMode', 'selected'), searchScope=data.get('searchScope', 'country'), searchCountries=data.get('searchCountries') or [])


def set_settings(user, body):
    city = ' '.join(str(body.get('city') or '').split())[:100]
    country = str(body.get('country') or '').upper()
    currency = str(body.get('currency') or 'EUR').upper()
    shop_mode = body.get('shopMode', 'selected')
    if shop_mode not in ('selected', 'nearby'):
        raise ApiError(400, 'INVALID_INPUT', 'Choose selected websites or discover nearby shops.')
    domains = []
    for raw in body.get('domains') or []:
        raw = str(raw).strip().lower()
        if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}', raw):
            raise ApiError(400, 'INVALID_DOMAIN', 'Enter website domains only, for example s-kaupat.fi (no URL paths).')
        if raw not in domains:
            domains.append(raw)
    if not city or not re.fullmatch('[A-Z]{2}', country) or not re.fullmatch('[A-Z]{3}', currency) or (shop_mode == 'selected' and not domains) or len(domains) > 10:
        raise ApiError(400, 'SEARCH_SETTINGS_REQUIRED', 'Choose your city, two-letter country, three-letter currency and 1–10 shop websites.')
    country, scope, countries = search_scope.validate(country, body.get('searchScope', 'country'), body.get('searchCountries'))
    value = {'city': city, 'country': country, 'currency': currency, 'domains': domains, 'shopMode': shop_mode, 'searchScope': scope, 'searchCountries': countries}
    db.set_state(user['id'], 'shopping_settings', value)
    return value


def search_user(user, required=False, resolve_shops=True):
    config = get_settings(user)
    if not config['city'] or not config['country'] or (config.get('shopMode') != 'nearby' and not config['domains']):
        if required or settings.data_mode == 'live':
            raise ApiError(422, 'SEARCH_SETTINGS_REQUIRED', 'Set your city, country, currency and grocery websites before searching.')
        return user
    country, scope, countries = search_scope.validate(config['country'], config.get('searchScope', 'country'), config.get('searchCountries'))
    return dict(user, city=config['city'], country=country, currency=config['currency'], site_region=country, preferred_domains=nearby_domains(user, config) if config.get('shopMode') == 'nearby' and resolve_shops else config['domains'], search_scope=scope, search_countries=countries)


def match_failure(item, candidate):
    summary = candidate.get('summary') if isinstance(candidate.get('summary'), dict) else {}
    if summary.get('page_type') in ('category', 'search', 'article'):
        return 'This is not an individual product page.'
    if summary.get('request_match') == 'mismatch' or summary.get('item_type_match') is False:
        return 'The actual product type or requested requirements do not match.'
    if candidate.get('_identity_verified'):
        return None  # Server-owned quote already validated for this identity/context.
    text = normalise(' '.join([str(summary.get('product') or summary.get('title') or candidate.get('title') or ''),
        str(summary.get('package_size') or ''), ' '.join(str(a) for a in summary.get('attributes') or []),
        str(summary.get('match_evidence') or '')]))
    requested = normalise(item.get('name') or '')
    # Related products cannot qualify just because their intended use repeats the
    # requested item name (e.g. seasoning FOR ground beef).
    for term in ('seasoning','spice mix','accessory','replacement part','case for'):
        if term in text and term not in requested:
            return 'A related product/accessory was found instead of the requested item.'
    constraints=[('brand',item.get('brand') or '')]
    attributes=item.get('attributes') or {}
    for key,value in attributes.items():
        if key.lower() in ('category','aisle'):
            if summary.get('category_match') is not True:
                return 'The requested category could not be verified: '+str(value)
        else:
            constraints.append((key,str(value)))
            package_key=normalise(key) in ('package','package size')
            if package_key and normalise(value)==normalise(summary.get('package_size') or ''):
                continue
            checks=summary.get('attribute_checks') or []
            check=next((c for c in checks if isinstance(c,dict) and normalise(c.get('key'))==normalise(key) and normalise(c.get('value'))==normalise(value)),None)
            if not check or check.get('exact_match') is not True or not str(check.get('evidence') or '').strip():
                return 'The exact attribute binding could not be verified: '+str(key)+'='+str(value)
            key_words=set(normalise(key).split())-{'percent','percentage','size','unit'}
            if re.search(r'\d',str(value)) and key_words and not key_words.issubset(set(normalise(check['evidence']).split())):
                return 'The numeric value is not tied to the requested attribute: '+str(key)
            if normalise(value) not in normalise(check['evidence']):
                return 'Attribute evidence does not contain the requested value: '+str(key)

    if item.get('_strict'):
        constraints.append(('details',item.get('details') or ''))
    for key,value in constraints:
        value=normalise(value)
        if value and not re.search(r'(?<![a-z0-9])'+re.escape(value)+r'(?![a-z0-9])',text):
            return 'Exact '+str(key)+' requirement is not evidenced: '+str(value)
    grounded=summary.get('request_match')=='matches' and bool(str(summary.get('match_evidence') or '').strip())
    if grounded:
        if item.get('_strict') and summary.get('item_type_match') is not True:
            return 'The actual item type (not a related product) could not be verified.'
        return None
    name_words=set(requested.split())-{'pack','bag','the','with','a','an','of'}
    if name_words and not name_words.issubset(set(text.split())):
        return 'The requested product identity could not be verified.'
    ignored=set('the a an and with of it should have has be from generation ram gpu system memory is needs need must at least'.split())
    for word in set(normalise(item.get('details') or '').split())-ignored:
        if re.fullmatch(r'\d+x+',word):
            if not re.search(r'\b'+word.replace('x',r'\d')+r'\b',text):
                return 'The required model family is not evidenced.'
        elif word not in text.split():
            return 'A required detail is not evidenced: '+word
    return None


def matches(item,candidate):
    return match_failure(item,candidate) is None


def attach(user, item):
    quotes = db.q('SELECT * FROM shopping_quotes WHERE user_id=? AND item_id=? AND identity_hash=? AND context_hash=? AND mode=? ORDER BY fetched_at DESC, rowid DESC',
                  (user['id'], item['id'], identity(item), context_hash(user), 'live'))
    seen, offers = set(), []
    for q in quotes:
        if q['url'] in seen:
            continue
        seen.add(q['url'])
        offers.append({'id': q['id'], 'priceMinor': q['price_minor'], 'currency': q['currency'], 'store': q['store'], 'url': q['url'],
                       'product': q['product'], 'image': product_media.thumbnail(q.get('image_url')), 'priceBasis': q.get('price_basis') or 'package', 'fetchedAt': q['fetched_at'], 'expiresAt': q['expires_at'], 'stale': db.parse_iso(q['expires_at']) <= db.now(),
                       'mode': q['mode'], 'cached': bool(q['cached']), 'evidence': q['evidence'], 'verification': 'source_claim'})
    fresh = [o for o in offers if not o['stale']]
    item['offers'] = offers[:20]
    item['quote'] = min(fresh, key=lambda o: o['priceMinor']) if fresh else (offers[0] if offers else None)
    item['priceStatus'] = 'fresh' if fresh else 'stale' if offers else 'unknown'
    return item


def persist_quotes(user, items, result, refresh_id, quoted_context=None):
    if quoted_context is not None and quoted_context != context_hash(user):
        return 0
    if result.get('mode') != 'live':
        return 0
    current = {r['id']: r for r in db.q('SELECT * FROM shopping_items WHERE user_id=? AND bought IS NULL', (user['id'],))}
    count = 0
    for item in items:
        row = current.get(item['id'])
        if not row:
            continue
        latest = dict(row, attributes=db.loads(row.get('attributes'), {}))
        if identity(latest) != identity(item):
            continue  # edited/deleted while the provider request was in flight
        for offer in result.get('priceOffers', {}).get(item['id'], []):
            fetched = offer.get('fetchedAt') or db.iso()
            expiry = db.iso(db.parse_iso(fetched) + timedelta(hours=6))
            db.run('INSERT INTO shopping_quotes(id,user_id,item_id,identity_hash,context_hash,refresh_id,price_minor,currency,store,url,product,fetched_at,expires_at,evidence,mode,cached,image_url,price_basis) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (db.new_id('sq_'), user['id'], item['id'], identity(item), context_hash(user), refresh_id, offer['priceMinor'], offer['currency'], offer['store'], offer['url'], offer['product'], fetched, expiry, offer.get('evidence') or '', 'live', int(offer.get('cached', False)), exa_client.safe_url(offer.get('image')), offer.get('priceBasis') or 'package'))
            count += 1
    return count


def refresh(user, force=True, item_ids=None, strategy='multi'):
    from . import organiser
    search_user(user, required=True)
    with _guard:
        lock = _locks.setdefault(user['id'], threading.Lock())
    if not lock.acquire(blocking=False):
        raise ApiError(409, 'REFRESH_RUNNING', 'A price refresh is already running. Wait for it to finish.')
    rid = db.new_id('rf_')
    try:
        db.run('INSERT INTO shopping_refreshes(id,user_id,status,started_at) VALUES(?,?,?,?)', (rid,user['id'],'running',db.iso()))
        pending = organiser.list_items(user, include_bought=False)
        if item_ids is not None:
            pending = [i for i in pending if i['id'] in item_ids]
        if len(pending) > 32:
            raise ApiError(422, 'LIST_TOO_LARGE', 'Refresh up to 32 open items at a time; select itemIds for a larger list.')
        if not pending:
            raise ApiError(422, 'EMPTY_LIST', 'Your shopping list is empty.')
        results = []
        for start in range(0, len(pending), 8):
            result = organiser.find_deals(user, strategy, items=pending[start:start+8], force_refresh=force, refresh_id=rid)
            results.append(result)
        result = results[-1]
        if len(results) > 1:
            result = dict(result, notice='All items refreshed in bounded batches. Compare the full list after refresh to choose a basket strategy.', batchCount=len(results))
        matched = {iid for batch in results for iid, quotes in batch.get('priceOffers', {}).items() if quotes}
        missing = len(pending) - len(matched)
        result = dict(result, matchedItemCount=len(matched), unpricedItemCount=missing,
                      diagnostics=[d for batch in results for d in batch.get('diagnostics', [])][:100],
                      storeCoverage=[c for batch in results for c in batch.get('storeCoverage', [])])
        if result.get('mode') == 'live':
            result['notice'] = f'Price check finished: {len(matched)} items matched; {missing} without a new matching quote. Existing saved quotes are retained. Check sources and selected currency; delivery and stock may be unknown.'
        db.run('UPDATE shopping_refreshes SET status=?,finished_at=? WHERE id=?', ('partial' if missing and result.get('mode') == 'live' else 'ready' if result.get('mode') == 'live' else 'demo',db.iso(),rid))
        return dict(result, refreshId=rid, items=organiser.list_items(user), notice=result.get('notice') or 'Provider research completed. Quotes are page claims, not checkout guarantees; local stock and delivery fees may be unknown.')
    except Exception as error:
        reason = str(error) if isinstance(error, ApiError) else 'Research failed; existing quotes retained.'
        db.run('UPDATE shopping_refreshes SET status=?,finished_at=?,reason=? WHERE id=?', ('failed',db.iso(),reason[:500],rid))
        raise
    finally:
        lock.release()


def auto_refresh(user, item_id):
    if not settings.auto_price_lookup:
        return
    try:
        # Automatic lookups reuse cache. Only explicit Update prices bypasses it.
        refresh(user, force=False, item_ids=[item_id])
    except ApiError:
        pass  # editable list succeeds even when research/configuration is unavailable


def status(user):
    return db.q1('SELECT id,status,started_at AS startedAt,finished_at AS finishedAt,reason FROM shopping_refreshes WHERE user_id=? ORDER BY rowid DESC LIMIT 1', (user['id'],))


def nearby_domains(user, config):
    result = exa_client.search(user['id'], 'places',
        'Grocery supermarkets with physical stores in %s %s official retailer websites' % (config['city'], config['country']),
        user_location=config['country'], num_results=8,
        summary_query='Is this an actual grocery retailer with a physical store in the requested city? Quote local presence evidence. Exclude directories, delivery aggregators and articles.',
        summary_schema={'type':'object','properties':{'is_retailer':{'type':'boolean'}, 'local_presence':{'type':'boolean'}, 'evidence':{'type':'string'}},'required':['is_retailer','local_presence']})
    domains=[]
    for row in result.get('results', []):
        summary=row.get('summary') or {}
        domain=row.get('domain')
        if summary.get('is_retailer') is True and summary.get('local_presence') is True and summary.get('evidence') and domain and domain not in domains:
            domains.append(domain)
    if not domains:
        raise ApiError(503, 'NO_NEARBY_SHOPS', result.get('reason') or 'No nearby grocery websites could be verified. Try selected shop websites instead.')
    return domains[:5]
