import json
import uuid
from types import SimpleNamespace

import pytest

from app import db, exa_client
from app.config import settings
from app.services import shopping_prices


class ShopExa:
    def __init__(self):
        self.calls=[]

    def search(self,query,**kwargs):
        self.calls.append((query,kwargs))
        def result(product,price,url):
            return SimpleNamespace(url=url,title=product,summary=json.dumps({'product':product,'price':price,'price_text':format(price,'.2f'),'price_basis':'package','availability':'in_stock','availability_evidence':'In stock','currency':'EUR','store':'Chosen Shop','package_size':'200 g'}),highlights=[f'{product} package costs €{price}'],published_date=None,image=None,favicon=None)
        return SimpleNamespace(results=[result('Estrella sour cream onion chips 200 g',2.49,'https://chosen-shop.example/chips'),
                                        result('Other Brand salted chips 200 g',.99,'https://chosen-shop.example/other')],cost_dollars=SimpleNamespace(total=.007))


@pytest.fixture
def account(app_client,monkeypatch):
    app_client.cookies.clear()
    response=app_client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Strong-test-password-2026','name':'Real tester','city':'User city','country':'FI'})
    assert response.status_code==201
    monkeypatch.setattr(settings,'auto_price_lookup',False)
    monkeypatch.setattr(settings,'data_mode','live')
    monkeypatch.setattr(settings,'exa_mode','live')
    monkeypatch.setattr(settings,'exa_api_key','fake-key')
    fake=ShopExa()
    monkeypatch.setattr(exa_client,'_client',fake)
    db.run('DELETE FROM exa_cache')
    db.run('DELETE FROM exa_ledger')
    return app_client,fake


def configure(client):
    response=client.put('/api/v1/shopping/settings',json={'city':'User-selected city','country':'FI','currency':'EUR','domains':['chosen-shop.example']})
    assert response.status_code==200


def add(client):
    response=client.post('/api/v1/shopping/items',json={'name':'chips','brand':'Estrella','details':'sour cream onion','attributes':{'package':'200 g'},'qty':2})
    assert response.status_code==201
    return response.json()


def test_requires_explicit_city_and_sites(account):
    client,_=account
    add(client)
    response=client.post('/api/v1/shopping/prices/refresh',json={})
    assert response.status_code==422
    assert response.json()['error']['code']=='SEARCH_SETTINGS_REQUIRED'
    assert client.get('/api/v1/shopping/settings').json()['domains']==[]


def test_brand_variant_quotes_persist_and_force_bypasses_cache(account):
    client,fake=account
    configure(client)
    item=add(client)
    response=client.post('/api/v1/shopping/prices/refresh',json={'force':False}).json()
    quote=response['items'][0]['quote']
    assert quote['priceMinor']==249 and quote['mode']=='live'
    assert quote['product'].startswith('Estrella')
    assert response['totalMinor']==498
    query,kwargs=fake.calls[-1]
    assert 'Estrella' in query and 'sour cream onion' in query and '200 g' in query
    assert kwargs['include_domains']==['chosen-shop.example']
    n=len(fake.calls)
    client.post('/api/v1/shopping/prices/refresh',json={'force':False})
    assert len(fake.calls)==n
    client.post('/api/v1/shopping/prices/refresh',json={'force':True})
    assert len(fake.calls)>n
    persisted=client.get('/api/v1/shopping/items').json()['items'][0]
    assert persisted['quote']['priceMinor']==249
    assert db.q1('SELECT COUNT(*) AS n FROM shopping_quotes WHERE item_id=?',(item['id'],))['n']>=2


def test_edits_context_and_ownership_invalidate_quotes(account):
    client,_=account;configure(client);item=add(client)
    client.post('/api/v1/shopping/prices/refresh',json={})
    changed=client.patch('/api/v1/shopping/items/'+item['id'],json={'brand':'Different','expectedVersion':item['version']}).json()
    assert changed['quote'] is None
    assert client.patch('/api/v1/shopping/items/'+item['id'],json={'qty':3,'expectedVersion':item['version']}).status_code==409
    client.post('/api/v1/shopping/prices/refresh',json={})
    assert client.get('/api/v1/shopping/items').json()['items'][0]['quote'] is None
    client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Other-password-2026','name':'Other'})
    assert client.get('/api/v1/shopping/items').json()['items']==[]
    assert client.patch('/api/v1/shopping/items/'+item['id'],json={'qty':3}).status_code==404


def test_live_failure_keeps_quotes_and_never_invents_demo(account,monkeypatch):
    client,_=account;configure(client);add(client)
    client.post('/api/v1/shopping/prices/refresh',json={})
    monkeypatch.setattr(settings,'exa_mode','mock')
    response=client.post('/api/v1/shopping/prices/refresh',json={'force':True})
    assert response.status_code==503
    assert response.json()['error']['code']=='LIVE_RESEARCH_UNAVAILABLE'
    assert client.get('/api/v1/shopping/items').json()['items'][0]['quote']['priceMinor']==249
    assert client.get('/api/v1/shopping/prices/status').json()['latest']['status']=='failed'


def test_invalid_quantity_settings_and_general_attributes(account):
    client,_=account
    assert client.post('/api/v1/shopping/items',json={'name':'chips','qty':-1}).status_code==400
    assert client.put('/api/v1/shopping/settings',json={'city':'City','country':'FI','domains':['https://shop.example/path']}).status_code==400
    assert not shopping_prices.matches({'attributes':{'size':'EU 43'}},{'title':'Boots EU 42','summary':{}})
    assert not shopping_prices.matches({'brand':'Estrella','details':'sour cream onion'},{'title':'Estrella salted chips','summary':{}})


def test_addition_never_triggers_price_lookup_even_with_legacy_flag(account,monkeypatch):
    client,fake=account;configure(client)
    monkeypatch.setattr(settings,'auto_price_lookup',True)
    item=add(client)
    assert fake.calls==[]
    assert client.get('/api/v1/shopping/items').json()['items'][0]['quote'] is None
    client.post('/api/v1/shopping/prices/refresh',json={})
    assert client.get('/api/v1/shopping/items').json()['items'][0]['quote']['priceMinor']==249


def test_readiness_has_no_credentials(account):
    client,_=account
    response=client.get('/api/v1/integrations')
    assert response.status_code==200
    assert 'fake-key' not in response.text
    assert response.json()['dataMode']=='live'


def test_refresh_larger_list_and_compare_saved_quotes_without_new_calls(account):
    client,fake=account
    configure(client)
    for _ in range(9):
        add(client)
    response=client.post('/api/v1/shopping/prices/refresh',json={'force':True})
    assert response.status_code==200
    assert len([i for i in response.json()['items'] if i['quote']])==9
    before=len(fake.calls)
    comparison=client.post('/api/v1/shopping/deals',json={'strategy':'single'}).json()
    assert comparison['totalMinor']==9*2*249
    assert not comparison['unpriced']
    assert len(fake.calls)==before


def test_changed_shop_context_hides_previous_quotes(account):
    client,_=account;configure(client);add(client)
    client.post('/api/v1/shopping/prices/refresh',json={})
    client.put('/api/v1/shopping/settings',json={'city':'Different user city','country':'FI','currency':'EUR','domains':['other-shop.example']})
    assert client.get('/api/v1/shopping/items').json()['items'][0]['quote'] is None


# Provider contract and regressions. Every SDK call below is a local fake.
def test_exa_price_schema_is_supported_and_missing_price_stays_unknown(account,monkeypatch):
    from app.agents.researcher import SCHEMAS
    client,_=account;configure(client);add(client)
    class StrictExa:
        def search(self,query,**kwargs):
            schema=kwargs['contents']['summary']['schema']
            def validate(value):
                if isinstance(value,dict):
                    if 'type' in value:
                        assert isinstance(value['type'],str), 'Exa does not accept union type arrays'
                    for child in value.values(): validate(child)
                elif isinstance(value,list):
                    for child in value: validate(child)
            validate(schema)
            assert 'price' not in schema.get('required',[])
            result=SimpleNamespace(url='https://chosen-shop.example/chips',title='Estrella sour cream onion chips 200 g',summary=json.dumps({'product':'Estrella sour cream onion chips 200 g','currency':'EUR'}),highlights=['No public package price'],published_date=None,image=None,favicon=None)
            return SimpleNamespace(results=[result],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(exa_client,'_client',StrictExa())
    response=client.post('/api/v1/shopping/prices/refresh',json={'force':True})
    assert response.status_code==200
    body=response.json()
    assert body['matchedItemCount']==0 and body['unpricedItemCount']==1
    assert body['items'][0]['quote'] is None
    assert 'without a new matching quote' in body['notice']
    assert client.get('/api/v1/shopping/prices/status').json()['latest']['status']=='partial'
    assert SCHEMAS['price']['properties']['price']['type']=='number'


def test_provider_rejection_is_visible_and_not_retried(account,monkeypatch):
    client,_=account;configure(client);add(client)
    class RejectExa:
        calls=0
        def search(self,*args,**kwargs):
            self.calls+=1
            raise ValueError('Request failed with status code 400: requestId=500-503-invalid-schema')
    fake=RejectExa();monkeypatch.setattr(exa_client,'_client',fake)
    response=client.post('/api/v1/shopping/prices/refresh',json={'force':True})
    assert response.status_code==502
    assert response.json()['error']['code']=='EXA_INVALID_REQUEST'
    assert 'HTTP 400' in response.json()['error']['message']
    assert response.json()['error']['retryable'] is False
    assert fake.calls==1
    assert 'HTTP 400' in client.get('/api/v1/shopping/prices/status').json()['latest']['reason']


def test_zero_cadence_is_manual_only_but_manual_checks_still_work(account):
    from app.services import watches
    client,_=account
    body={'query':'chips','city':'User city','country':'FI','currency':'EUR','sites':['chosen-shop.example'],'cadenceHours':0}
    response=client.post('/api/v1/price-watches',json=body)
    assert response.status_code==201
    watch=response.json();wid=watch['id']
    assert watch['cadenceHours']==0
    from app import auth
    user=auth.user_for_token(client.cookies.get(auth.COOKIE))
    assert watches.check(user,wid,automatic=True)['skipped'] is True
    assert wid not in {w['id'] for w in watches.due()}
    assert client.post('/api/v1/price-watches/'+wid+'/checks').status_code==200
    assert wid not in {w['id'] for w in watches.due()}
    changed=client.patch('/api/v1/price-watches/'+wid,json={'cadenceHours':24}).json()
    assert changed['cadenceHours']==24
    changed=client.patch('/api/v1/price-watches/'+wid,json={'cadenceHours':0}).json()
    assert changed['cadenceHours']==0
    assert client.patch('/api/v1/price-watches/'+wid,json={'cadenceHours':-1}).status_code==400
    assert client.patch('/api/v1/price-watches/'+wid,json={'cadenceHours':None}).status_code==400


def test_cross_country_scopes_do_not_send_eu_or_home_country_bias(account):
    client,fake=account
    base={'city':'User city','country':'FI','currency':'EUR','domains':['chosen-shop.example','another-shop.example']}
    add(client)
    for scope,countries in [('eu',[]),('multiple',['FI','DE']),('worldwide',[])]:
        response=client.put('/api/v1/shopping/settings',json=dict(base,searchScope=scope,searchCountries=countries))
        assert response.status_code==200
        assert client.post('/api/v1/shopping/prices/refresh',json={'force':True}).status_code==200
        query,kwargs=fake.calls[-1]
        assert 'user_location' not in kwargs
        assert kwargs['include_domains'] in [[d] for d in base['domains']]
        assert {kw['include_domains'][0] for _,kw in fake.calls} == set(base['domains'])
        if scope=='eu': assert 'European Union' in query
        if scope=='multiple': assert 'FI, DE' in query
        if scope=='worldwide': assert 'worldwide' in query
    response=client.put('/api/v1/shopping/settings',json=dict(base,country='EU'))
    assert response.status_code==400
    assert response.json()['error']['code']=='INVALID_COUNTRY'
    assert client.put('/api/v1/shopping/settings',json=dict(base,searchScope='multiple',searchCountries=[])).status_code==400


def test_watch_cross_country_search_and_manual_cadence(account):
    client,fake=account
    watch=client.post('/api/v1/price-watches',json={'query':'chips','city':'User city','country':'FI','currency':'EUR','sites':['chosen-shop.example','another-shop.example'],'cadenceHours':0,'searchScope':'multiple','searchCountries':['FI','DE']})
    assert watch.status_code==201
    wid=watch.json()['id']
    assert client.post('/api/v1/price-watches/'+wid+'/checks').status_code==200
    query,kwargs=fake.calls[-1]
    assert 'FI, DE' in query and 'user_location' not in kwargs
    assert len(kwargs['include_domains'])==2


def priced_page(title, **fields):
    return SimpleNamespace(url='https://chosen-shop.example/product', title=title,
        summary=json.dumps(dict(dict(title=title, product=title, price=2.49, price_text='2.49 EUR', price_basis='package', availability='in_stock', availability_evidence='In stock', currency='EUR'), **fields)),
        highlights=[title], published_date=None, image=None, favicon=None)


def test_localized_product_refines_category_and_keeps_cached_quote(account, monkeypatch):
    client,fake=account;configure(client)
    client.post('/api/v1/shopping/items',json={'name':'Chips','brand':'Estrella','attributes':{'flavour':'hot honey'}})
    def search(query,**kwargs):
        fake.calls.append((query,kwargs))
        if 'specific product' in query:
            page=priced_page('Estrella Hot Honey perunalastu 275 g',page_type='product',item_type_match=True,attribute_checks=[{'key':'flavour','value':'hot honey','exact_match':True,'evidence':'Estrella Hot Honey'}],request_match='matches',match_evidence='Estrella Hot Honey perunalastu 275 g')
        else:
            page=priced_page('Sipsit, snacksit ja pähkinät',page_type='category')
        return SimpleNamespace(results=[page],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    result=client.post('/api/v1/shopping/prices/refresh',json={'force':True}).json()
    assert result['matchedItemCount']==1
    assert len(fake.calls)==2
    assert all(kw['include_domains']==['chosen-shop.example'] for _,kw in fake.calls)
    assert result['items'][0]['quote']['priceMinor']==249
    # The quote identity/context was already validated at persistence; translated
    # names must also remain usable on a subsequent cached comparison.
    before=len(fake.calls)
    compared=client.post('/api/v1/shopping/deals',json={'strategy':'multi'}).json()
    assert compared['totalMinor']==249
    assert len(fake.calls)==before


def test_category_only_diagnostics_do_not_become_price_sources(account,monkeypatch):
    client,fake=account;configure(client);add(client)
    monkeypatch.setattr(fake,'search',lambda *a,**kw:SimpleNamespace(results=[priced_page('Estrella category',page_type='category')],cost_dollars=SimpleNamespace(total=.007)))
    result=client.post('/api/v1/shopping/prices/refresh',json={}).json()
    assert result['matchedItemCount']==0 and result['sources']==[]
    assert 'not an individual product' in result['diagnostics'][0]['reason']
    assert result['items'][0]['quote'] is None


def test_watch_natural_requirements_and_history_attempts(account,monkeypatch):
    client,fake=account
    watch=client.post('/api/v1/price-watches',json={'query':'laptop with gpu','details':'it should have gpu from nvidia 50xx generation, it should have 16gb of ram','city':'User city','country':'FI','currency':'EUR','sites':['chosen-shop.example'],'cadenceHours':0}).json()
    def search(*a,**kw):
        return SimpleNamespace(results=[priced_page('Gaming laptop NVIDIA RTX 5060 16 GB RAM',page_type='product',attributes=['NVIDIA RTX 5060','16 GB RAM'],request_match='matches',match_evidence='Gaming laptop NVIDIA RTX 5060 16 GB RAM')],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    path='/api/v1/price-watches/'+watch['id']
    result=client.post(path+'/checks').json()
    assert result['checkState']=='ready' and len(result['offers'])==1
    hist=client.get(path+'/history').json()
    assert len(hist['items'])==1 and hist['checks'][0]['offerCount']==1
    db.run('DELETE FROM exa_cache')
    monkeypatch.setattr(fake,'search',lambda *a,**kw:SimpleNamespace(results=[priced_page('Gaming laptop NVIDIA RTX 4060 8 GB RAM',page_type='product',request_match='mismatch')],cost_dollars=SimpleNamespace(total=.007)))
    result=client.post(path+'/checks').json()
    assert result['checkState']=='stale' and result['offers']==[]
    hist=client.get(path+'/history').json()
    assert len(hist['items'])==1 and len(hist['checks'])==2
    assert 'specifications' in result['diagnostics'][0]['reason']
    assert all('diagnostics' not in c for c in hist['checks'])


def test_no_matches_is_not_provider_error(account,monkeypatch):
    client,fake=account
    watch=client.post('/api/v1/price-watches',json={'query':'boots','city':'User city','country':'FI','currency':'EUR','sites':['chosen-shop.example']}).json()
    monkeypatch.setattr(fake,'search',lambda *a,**kw:SimpleNamespace(results=[],cost_dollars=SimpleNamespace(total=.007)))
    path='/api/v1/price-watches/'+watch['id']
    result=client.post(path+'/checks').json()
    assert result['checkState']=='no_matches'
    hist=client.get(path+'/history').json()
    assert hist['items']==[] and len(hist['checks'])==1
    assert 'first successful' in hist['notice']


def test_units_model_families_and_unsupported_constraints():
    item={'name':'laptop','details':'it should have gpu from nvidia 50xx generation, it should have 16gb of ram'}
    assert shopping_prices.matches(item,{'title':'Laptop NVIDIA RTX 5060 16 GB RAM'})
    assert not shopping_prices.matches(item,{'title':'Laptop NVIDIA RTX 4060 16 GB RAM'})
    assert not shopping_prices.matches(item,{'title':'Laptop NVIDIA RTX 5060 8 GB RAM'})
    assert not shopping_prices.matches({'brand':'Estrella'},{'title':'Other Brand chips','summary':{'request_match':'matches','match_evidence':'Other Brand chips'}})
    assert not shopping_prices.matches({'details':'hot honey'},{'title':'Chips','summary':{'request_match':'matches','match_evidence':''}})


@pytest.mark.parametrize('shown,expected', [('EUR2.49',249),('2.49EUR',249),('.99 EUR',99),('2,49 EUR',249),('EUR 2.49',249),('1.299,99 EUR',129999),('1,299.99 EUR',129999),('2 49 EUR',None),('249 cents',None),('2.49 / kg',None),('8.00 EUR / l',None),('2 for 5 EUR',None),('-2.49 EUR',None)])
def test_display_price_is_authoritative_and_package_only(shown,expected):
    from app.services.price_evidence import quote
    minor,reason=quote({'price':249,'price_text':shown,'price_basis':'package','currency':'EUR'},'EUR',package=True)
    assert minor==expected
    assert (reason is None)==(expected is not None)


def test_each_selected_shop_gets_its_own_lookup(account,monkeypatch):
    client,fake=account
    client.put('/api/v1/shopping/settings',json={'city':'User city','country':'FI','currency':'EUR','domains':['first.example','second.example']})
    client.post('/api/v1/shopping/items',json={'name':'chips'})
    def search(query,**kw):
        fake.calls.append((query,kw));domain=kw['include_domains'][0]
        p=priced_page('Chips',price=249,price_text='2,49 EUR',page_type='product')
        p.url='https://'+domain+'/chips'
        return SimpleNamespace(results=[p],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    r=client.post('/api/v1/shopping/prices/refresh',json={}).json()
    assert {kw['include_domains'][0] for _,kw in fake.calls}=={'first.example','second.example'}
    assert len(r['items'][0]['offers'])==2
    assert {o['priceMinor'] for o in r['items'][0]['offers']}=={249}
    assert len(r['storeCoverage'])==2


def test_nearby_discovery_is_explicit_and_verifies_retailers(account,monkeypatch):
    client,fake=account
    assert client.put('/api/v1/shopping/settings',json={'city':'Chosen city','country':'FI','domains':[],'shopMode':'nearby'}).status_code==200
    client.post('/api/v1/shopping/items',json={'name':'chips'})
    def search(query,**kw):
        fake.calls.append((query,kw));page=priced_page('Chips')
        if 'physical stores' in query:
            page.summary=json.dumps({'is_retailer':True,'local_presence':True,'evidence':'Our store in Chosen city'})
        return SimpleNamespace(results=[page],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    r=client.post('/api/v1/shopping/prices/refresh',json={})
    assert r.status_code==200
    assert r.json()['matchedItemCount']==1
    assert any(kw.get('include_domains')==['chosen-shop.example'] for _,kw in fake.calls)


def test_optional_watch_sites_multiple_options_survive_sign_in(account,monkeypatch):
    client,fake=account
    user_email=db.q1('SELECT email FROM users ORDER BY rowid DESC LIMIT 1')['email']
    watch=client.post('/api/v1/price-watches',json={'query':'boots','city':'Chosen city','country':'FI','cadenceHours':0}).json()
    def search(*a,**kw):
        fake.calls.append((a,kw));pages=[]
        for i in range(10):
            p=priced_page('Boots '+str(i),price_text=str(100+i)+'.00 EUR');p.url='https://chosen-shop.example/boot-'+str(i);pages.append(p)
        pages.append(priced_page('Boots sold out',availability='out_of_stock'))
        return SimpleNamespace(results=pages,cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    path='/api/v1/price-watches/'+watch['id']
    result=client.post(path+'/checks').json()
    assert len(result['offers'])==10 and 'lastOffers' not in result
    assert 'include_domains' not in fake.calls[0][1]
    assert any('not confirmed available' in d['reason'] for d in result['diagnostics'])
    for count in (1,5,10):
        saved=client.post('/api/v1/price-watch-lists',json={'count':count,'name':'My boots '+str(count),'saveToken':result['saveToken'],'cadenceHours':0})
        assert saved.status_code==201 and len(saved.json()['savedOptions'])==count
    assert len(client.get(path+'/history').json()['items'])==10
    client.post('/api/v1/auth/logout')
    assert client.post('/api/v1/auth/login',json={'email':user_email,'password':'Strong-test-password-2026'}).status_code==200
    restored=next(w for w in client.get('/api/v1/price-watches').json()['items'] if w['id']==saved.json()['id'])
    assert 'lastOffers' not in restored and len(restored['savedOptions'])==10
    assert restored['name']=='My boots 10' and restored['query']=='boots'


def test_copenhagen_events_do_not_append_home_city_and_can_be_combined(account,monkeypatch):
    client,fake=account
    def search(query,**kw):
        fake.calls.append((query,kw))
        if kw.get('include_domains'):return SimpleNamespace(results=[],cost_dollars=SimpleNamespace(total=.007))
        pages=[]
        for city,match in [('Copenhagen',True),('Helsinki',False)]:
            p=priced_page(city+' Christmas Market',start_date='2099-11-01',end_date='2099-12-30',date_text='November to December 2099',start_time='11:00',end_time='21:00',city=city,venue='Market square',location_match=match,event_page_type='single_event',price_text='Free')
            p.url='https://events.example/'+city;p.image='https://photos.example/'+city+'.jpg';pages.append(p)
        return SimpleNamespace(results=pages,cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    result=client.post('/api/v1/explore',json={'query':'Copenhagen, Christmas markets','kind':'events'}).json()
    assert [r['title'] for r in result['results']]==['Copenhagen Christmas Market']
    event=result['results'][0]
    assert event['endDate']=='2099-12-30' and event['startTime']=='11:00'
    assert all('Helsinki' not in q for q,_ in fake.calls)
    assert all('user_location' not in kw for _,kw in fake.calls)
    trip=client.post('/api/v1/itineraries',json={'title':'Copenhagen festive weekend','choices':[{'searchId':result['searchId'],'resultId':event['id']}]}).json()
    assert trip['items'][0]['price']=='Free'
    assert client.get('/api/v1/research-searches').json()['items']==[]
    assert client.get('/api/v1/itineraries').json()['items'][0]['id']==trip['id']
    # Another account cannot read this plan or borrow its source output.
    client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Other-password-2026','name':'Other'})
    assert client.get('/api/v1/itineraries').json()['items']==[]
    assert client.post('/api/v1/itineraries/'+trip['id']+'/media',json={'kind':'schedule'}).status_code==404
    assert client.post('/api/v1/itineraries',json={'choices':[{'searchId':result['searchId'],'resultId':event['id']}]}).status_code==410


def test_cloudinary_schedule_rotation_and_three_event_limit_offline(account,monkeypatch):
    from app.services import media,plans
    from app import auth
    import cloudinary
    import cloudinary.uploader
    client,_=account
    user=auth.user_for_token(client.cookies.get(auth.COOKIE))
    monkeypatch.setattr(cloudinary.config(),'cloud_name','offline-cloud')
    monkeypatch.setattr(media,'_require',lambda:cloudinary)
    uploads=[];multis=[]
    def upload(url,**kwargs):
        uploads.append((url,kwargs));pid=kwargs.get('public_id','test')
        return {'secure_url':'https://res.cloudinary.com/offline-cloud/image/upload/'+pid+'.jpg','public_id':pid}
    monkeypatch.setattr(cloudinary.uploader,'upload',upload)
    monkeypatch.setattr(cloudinary.uploader,'multi',lambda tag,**kw:multis.append((tag,kw)) or {'secure_url':'https://res.cloudinary.com/offline-cloud/video/upload/preview.mp4'})
    events=[{'id':'event-'+str(i),'title':'Event '+str(i),'when':'2099-11-15 18:00','startDate':'2099-11-15','endDate':'2099-11-16','where':'Copenhagen','price':'DKK 120','images':['https://photos.example/'+str(i)+'.jpg'],'sources':[{'url':'https://events.example/'+str(i),'title':'Event source'}]} for i in range(4)]
    sid=plans.remember_search(user,'Events in Copenhagen','events',{'results':events})
    trip=plans.create(user,'Jury weekend',[{'searchId':sid,'resultId':e['id']} for e in events])
    base='/api/v1/itineraries/'+trip['id']+'/media'
    schedule=client.post(base,json={'kind':'schedule'})
    assert schedule.status_code==201,schedule.text
    assert 'DKK 120' in schedule.json()['schedule']['items'][0]['where']
    assert '2099-11-16' in schedule.json()['schedule']['items'][0]['time']
    assert '/image/upload/' in schedule.json()['schedule']['url']
    clips=client.post(base,json={'kind':'teasers','eventIds':[e['id'] for e in events[:3]]})
    assert clips.status_code==201,clips.text
    assert len(clips.json()['teasers'])==3
    assert len(multis)==3
    # The limit counts previous clips too, rather than allowing a fourth by retry.
    assert client.post(base,json={'kind':'teasers','eventIds':[events[3]['id']]}).status_code==400
    assert client.post(base,json={'kind':'teasers','eventIds':[events[0]['id']]}).status_code==201
    assert len(multis)==3
    rotation=media.rotation_video(user,['https://photos.example/product.jpg'],'Boots')
    assert '2D' in rotation['mode'] and rotation['url'].endswith('.mp4')
    assert len(multis)==4


def test_product_image_parser_and_private_urls_rejected(monkeypatch):
    from app.services.media import ProductPhotos, public_url
    parser=ProductPhotos()
    parser.feed('<meta property="og:image" content="https://cdn.example/front.jpg"><script type="application/ld+json">{"@type":"Product","image":["https://cdn.example/back.jpg",{"url":"https://cdn.example/side.jpg"}]}</script><img src="https://cdn.example/unrelated-ad.jpg">')
    assert parser.images==['https://cdn.example/front.jpg','https://cdn.example/back.jpg','https://cdn.example/side.jpg']
    assert not public_url('http://127.0.0.1/secret')
    assert not public_url('http://169.254.169.254/latest/meta-data')


def test_event_listing_refines_to_single_event_without_merging(account,monkeypatch):
    client,fake=account
    def search(query,**kw):
        fake.calls.append((query,kw))
        if kw.get('include_domains'):
            return SimpleNamespace(results=[],cost_dollars=SimpleNamespace(total=.007))
        single='official individual event detail' in query
        page=priced_page('Copenhagen Comedy Night' if single else '20 events in Copenhagen',
                        event_page_type='single_event' if single else 'event_listing',location_match=True,
                        start_date='2099-12-18',end_date='2099-12-18',date_text='18 December 2099, 20:00',
                        start_time='20:00',city='Copenhagen',venue='Comedy Club',price_text='DKK 150',
                        event_evidence='Copenhagen Comedy Night, Comedy Club, 18 December 2099 at 20:00')
        page.url='https://events.example/comedy-night' if single else 'https://events.example/calendar'
        return SimpleNamespace(results=[page],cost_dollars=SimpleNamespace(total=.007))
    monkeypatch.setattr(fake,'search',search)
    result=client.post('/api/v1/explore',json={'query':'Comedy in Copenhagen','kind':'events'}).json()
    assert len(result['results'])==1
    event=result['results'][0]
    assert event['eventPageType']=='single_event' and event['url'].endswith('/comedy-night')
    assert event['startTime']=='20:00' and event['price']=='DKK 150'
    assert any('listing' in d['reason'] for d in result['diagnostics'])
    assert any('official individual event detail' in q for q,_ in fake.calls)
    assert all('ONE individual event' in kw['contents']['summary']['query'] for _,kw in fake.calls if 'summary' in kw.get('contents',{}))


def test_itinerary_print_and_calendar_exports_are_owned_and_escape_content(account):
    from app.services import plans
    from app import auth
    client,_=account
    user=auth.user_for_token(client.cookies.get(auth.COOKIE))
    event={'id':'event-export','eventPageType':'single_event','title':'Comedy <script>alert(1)</script>',
           'startDate':'2099-12-18','endDate':'2099-12-20','when':'18–20 December, local time 20:00',
           'where':'Copenhagen','price':'DKK 150','images':[], 'sources':[{'title':'Original event','url':'https://events.example/comedy'}]}
    sid=plans.remember_search(user,'Comedy','events',{'results':[event]})
    plan=plans.create(user,'Winter weekend',[{'searchId':sid,'resultId':event['id']}])
    path='/api/v1/itineraries/'+plan['id']
    printed=client.get(path+'/print')
    assert printed.status_code==200
    assert '<script>alert' not in printed.text and '&lt;script&gt;' in printed.text
    calendar=client.get(path+'/calendar')
    assert calendar.status_code==200 and 'text/calendar' in calendar.headers['content-type']
    assert 'DTSTART;VALUE=DATE:20991218' in calendar.text
    assert 'DTEND;VALUE=DATE:20991221' in calendar.text
    assert 'STATUS:TENTATIVE' in calendar.text
    client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Other-password-2026','name':'Other'})
    assert client.get(path+'/print').status_code==404
    assert client.get(path+'/calendar').status_code==404


def test_exact_attributes_and_actual_product_type_cannot_be_bypassed_by_positive_ai():
    from app.services.shopping_prices import match_failure
    item={'name':'ground beef','attributes':{'category':'meat','fat':'5%'},'_strict':True}
    wrong={'title':'Ground beef seasoning 5% salt','summary':{'product':'Ground beef seasoning 5% salt','page_type':'product','request_match':'matches','item_type_match':True,'category_match':True,'match_evidence':'Seasoning for ground beef, 5% salt'}}
    assert 'related product' in match_failure(item,wrong)
    product={'title':'Ground beef 5% fat','summary':{'product':'Ground beef 5% fat','page_type':'product','request_match':'matches','item_type_match':True,'category_match':True,'match_evidence':'Ground beef 5% fat'}}
    assert 'binding' in match_failure(item,product)
    product['summary']['attribute_checks']=[{'key':'fat','value':'5%','exact_match':True,'evidence':'Ground beef 5% fat'}]
    assert match_failure(item,product) is None
    product['summary']['attribute_checks'][0]['evidence']='5% protein'
    assert match_failure(item,product) is not None
    product['summary']['attribute_checks'][0]['value']='10%'
    assert match_failure(item,product) is not None
    product['summary']['category_match']=False
    assert match_failure(item,product) is not None


def test_strategy_change_uses_saved_quotes_and_multiplies_quantity_without_search(account,monkeypatch):
    client,fake=account;configure(client)
    item=add(client)
    client.patch('/api/v1/shopping/items/'+item['id'],json={'qty':6})
    client.post('/api/v1/shopping/prices/refresh',json={})
    calls=len(fake.calls)
    for strategy in ('multi','single'):
        response=client.post('/api/v1/shopping/deals',json={'strategy':strategy,'cachedOnly':True})
        assert response.status_code==200,response.text
        result=response.json()
        assert result['strategy']==strategy and result['totalMinor']==249*6
        assert result['plan'][0]['lines'][0]['qty']==6
    assert len(fake.calls)==calls
    client.post('/api/v1/shopping/items',json={'name':'Unpriced addition','qty':6})
    result=client.post('/api/v1/shopping/deals',json={'strategy':'single'}).json()
    assert result['totalMinor']==249*6 and len(result['unpriced'])==1
    assert len(fake.calls)==calls


def test_price_research_is_temporary_name_required_and_bound_to_user(account,monkeypatch):
    client,fake=account
    monkeypatch.setattr(fake,'search',lambda *a,**kw:SimpleNamespace(results=[priced_page('Boots')],cost_dollars=SimpleNamespace(total=.007)))
    count=db.q1('SELECT COUNT(*) AS n FROM price_watches')['n']
    result=client.post('/api/v1/price-watch-research',json={'query':'boots','city':'Chosen city','country':'FI','currency':'EUR','sites':[],'cadenceHours':0}).json()
    assert len(result['offers'])==1 and result['saveToken']
    assert db.q1('SELECT COUNT(*) AS n FROM price_watches')['n']==count
    assert client.post('/api/v1/price-watch-lists',json={'name':' ','count':1,'saveToken':result['saveToken']}).status_code==400
    saved=client.post('/api/v1/price-watch-lists',json={'name':'My next boots','count':1,'saveToken':result['saveToken'],'cadenceHours':6})
    assert saved.status_code==201,saved.text
    watch=saved.json();data=db.loads(db.q1('SELECT data FROM price_watches WHERE id=?',(watch['id'],))['data'])
    assert data['name']=='My next boots' and data['query']=='boots' and data['cadenceHours']==6
    assert 'diagnostics' not in data and 'lastOffers' not in data
    client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Other-password-2026','name':'Other'})
    assert client.post('/api/v1/price-watch-lists',json={'name':'Stolen','count':1,'saveToken':result['saveToken']}).status_code==410


def test_unsaved_event_output_is_not_written_as_research_history(account):
    from app.services import plans
    from app import auth
    client,_=account;user=auth.user_for_token(client.cookies.get(auth.COOKIE))
    before=db.q1('SELECT COUNT(*) AS n FROM research_searches')['n']
    sid=plans.remember_search(user,'AI and science','events',{'results':[{'id':'science','title':'AI science night'}]})
    assert db.q1('SELECT COUNT(*) AS n FROM research_searches')['n']==before
    assert plans.searches(user)['items']==[]
    saved=plans.create(user,'Science trip',[{'searchId':sid,'resultId':'science'}])
    assert saved['items'][0]['title']=='AI science night'


def test_themed_schedule_uses_information_not_event_photos(account,monkeypatch):
    import base64
    import cloudinary
    import cloudinary.uploader
    from app.services import media
    client,_=account
    monkeypatch.setattr(cloudinary.config(),'cloud_name','offline-cloud')
    monkeypatch.setattr(media,'_require',lambda:cloudinary)
    uploads=[]
    monkeypatch.setattr(cloudinary.uploader,'upload',lambda value,**kw:uploads.append(value) or {'public_id':'science-poster'})
    result=media.itinerary_image({'id':'offline-user'},'AI & Science', [{'time':'2099-12-18 18:00','title':'Robotics and AI','where':'Science hall - EUR 10'}],hero_image_url='https://events.example/MUST_NOT_FETCH.jpg',theme_text='AI physics research')
    assert result['theme']=='AI & SCIENCE'
    assert uploads[0].startswith('data:image/svg+xml;base64,')
    svg=base64.b64decode(uploads[0].split(',',1)[1]).decode()
    assert 'Robotics and AI' in svg and 'EUR 10' in svg and '<ellipse' in svg
    assert 'MUST_NOT_FETCH' not in svg and '<image' not in svg


def test_video_proxy_streams_inline_range_and_checks_ownership(account,monkeypatch):
    from app.services import media
    from app import auth
    import httpx
    client,_=account;user=auth.user_for_token(client.cookies.get(auth.COOKIE))
    asset=media._save(user,'rotation',{'url':'https://res.cloudinary.com/demo/image/multi/test.mp4'})
    seen=[]
    class FakeClient:
        def __init__(self,**kw):pass
        def build_request(self,method,url,headers):seen.append(headers);return httpx.Request(method,url)
        def send(self,request,stream):return httpx.Response(206,headers={'Content-Length':'3','Content-Range':'bytes 0-2/3'},content=b'abc',request=request)
        def close(self):pass
    monkeypatch.setattr(httpx,'Client',FakeClient)
    response=client.get('/api/v1/media/'+asset['id']+'/playback',headers={'Range':'bytes=0-2'})
    assert response.status_code==206 and response.content==b'abc'
    assert response.headers['content-type']=='video/mp4' and response.headers['content-disposition']=='inline'
    assert seen==[{'Range':'bytes=0-2'}]
    client.post('/api/v1/auth/register',json={'email':uuid.uuid4().hex+'@example.com','password':'Other-password-2026','name':'Other'})
    assert client.get('/api/v1/media/'+asset['id']+'/playback').status_code==404



def test_cached_strategy_does_not_discover_nearby_shops(account,monkeypatch):
    client,fake=account
    client.put('/api/v1/shopping/settings',json={'city':'Chosen city','country':'FI','currency':'EUR','domains':[],'shopMode':'nearby'})
    client.post('/api/v1/shopping/items',json={'name':'Banana','qty':6})
    def forbidden(*args,**kwargs):raise AssertionError('Comparison must not start shop discovery')
    monkeypatch.setattr(shopping_prices,'nearby_domains',forbidden)
    result=client.post('/api/v1/shopping/deals',json={'strategy':'single'})
    assert result.status_code==200,result.text
    assert result.json()['totalMinor']==0 and len(result.json()['unpriced'])==1
    assert fake.calls==[]
