"""Live-data code paths with a fake Exa client: caching, budget caps, honest
unknown prices, structured extraction -> frontend shapes."""
import json
from types import SimpleNamespace

import pytest

from app import db, exa_client
from app.config import settings


def R(url, title, summary=None, highlights=None, image=None):
    if summary and summary.get('price'):
        summary=dict(summary,price_text=summary.get('price_text') or format(summary['price'],'.2f'),price_basis='package',availability='in_stock',availability_evidence='In stock')
    if summary and summary.get('start_date'):
        summary=dict(summary,location_match=True,event_page_type="single_event")
    return SimpleNamespace(url=url, title=title, published_date=None, image=image, favicon=None,
                           highlights=highlights or ["snippet about " + title], summary=json.dumps(summary) if summary else None)


class FakeExa:
    def __init__(self):
        self.calls = []

    def search(self, query, **kw):
        self.calls.append((query, kw))
        q = query.lower()
        if "oat milk" in q:
            res = [R("https://www.s-kaupat.fi/tuote/oat", "Oat drink 1L", {"product": "Oat milk drink 1 l", "price": 1.65, "currency": "EUR"}),
                   R("https://www.lidl.fi/p/oat", "Oat drink", {"product": "Oat milk 1 L", "price": 1.39, "currency": "EUR"}),
                   R("https://www.k-ruoka.fi/x", "Cheese", {"product": "Edam cheese", "price": 0.5, "currency": "EUR"})]
        elif "oat drink" in q:  # real-world shapes: Finnish titles, Exa's number read as 179 but the page says 1,79 €
            ok = {"page_type": "product", "price_basis": "package", "request_match": "matches", "item_type_match": True}
            res = [R("https://www.k-ruoka.fi/kauppa/tuote/oatly", "Oatly kaurajuoma 1l | K-Ruoka",
                     dict(ok, product="Oatly kaurajuoma täyteläinen 1l", price=179, price_text="1,79 €", currency="EUR",
                          match_evidence="Oatly kaurajuoma täyteläinen 1l"),
                     highlights=["Hinta 1,79 € kappale\n\n1 79 /kpl"]),
                   R("https://www.s-kaupat.fi/tuote/oatly", "Oatly Kaurajuoma 1L | S-kaupat",
                     dict(ok, product="Oatly Kaurajuoma 1L", price=1.94, price_text="1,94 €", currency="EUR", match_evidence="Oatly Kaurajuoma 1L"),
                     highlights=["n. Noin 1,94 €"]),
                   R("https://www.lidl.fi/p/oatdrinkchoc", "Oat drink chocolate",
                     dict(ok, product="Oat drink chocolate", price=0.99, price_text="0,99 €", currency="EUR", request_match="mismatch"))]
        elif " events " in q:
            res = [R("https://venue.example/jazz", "Jazz night", {"title": "Jazz Night at Storyville", "date_text": "Sat 21 Nov 21:00",
                     "start_date": "2099-11-21", "venue": "Storyville", "city": "Helsinki", "price_text": "€15", "category": "jazz"},
                     image="https://venue.example/img.jpg"),
                   R("https://old.example/e", "Old", {"title": "Past fest", "start_date": "2001-01-01"})]
        elif "reddit" in json.dumps(kw.get("include_domains") or []) or "recommendations" in q:
            res = [R("https://www.reddit.com/r/Helsinki/comments/1", "thread", highlights=["Storyville is great on Saturdays"])]
        elif "buy" in q:
            res = [R("https://shop.example/boot", "Boot A", {"title": "Trail Boot", "price": 120, "currency": "EUR", "store": "Shop",
                     "attributes": ["waterproof", "black"]})]
        else:
            res = []
        return SimpleNamespace(results=res, cost_dollars=SimpleNamespace(total=0.006))


@pytest.fixture()
def live(monkeypatch):
    fake = FakeExa()
    monkeypatch.setattr(settings, "exa_mode", "live")
    monkeypatch.setattr(settings, "exa_api_key", "test-key")
    monkeypatch.setattr(exa_client, "_client", fake)
    db.run("DELETE FROM exa_cache")
    db.run("DELETE FROM exa_ledger")
    return fake


def test_live_deals_never_invent_prices(client, live):
    r = client.post("/api/deals", json={"items": [{"id": "a1", "name": "Oat milk 1 L", "qty": 2},
                                                   {"id": "a2", "name": "Saffron threads", "qty": 1}], "strategy": "multi"}).json()
    assert r["mode"] == "live"
    lines = [l for p in r["plan"] for l in p["lines"]]
    assert len(lines) == 1 and lines[0]["price"] == 1.39 and r["plan"][0]["store"]["name"] == "Lidl Sörnäinen"
    assert r["total"] == 2.78
    assert [u["name"] for u in r["unpriced"]] == ["Saffron threads"] and r["hasUnknownCosts"]
    assert all(s["url"].startswith("https://") for s in r["sources"])
    # the cheese page (different product) was ignored
    assert all("k-ruoka" not in s["url"] for s in r["sources"])


def test_cache_and_ledger(client, live):
    body = {"items": [{"id": "a1", "name": "Oat milk 1 L", "qty": 1}], "strategy": "single"}
    client.post("/api/deals", json=body)
    n = len(live.calls)
    client.post("/api/deals", json=body)
    assert len(live.calls) == n  # served from cache
    u = client.get("/api/v1/usage").json()
    assert u["exa"]["totalCalls"] >= 1 and u["exa"]["cacheHits"] >= 1 and u["exa"]["totalUsd"] > 0


def test_budget_cap_falls_back_to_demo(client, live, monkeypatch):
    monkeypatch.setattr(settings, "exa_total_budget_usd", 0.0)
    r = client.post("/api/deals", json={"items": [{"id": "z", "name": "Rye bread"}], "strategy": "multi"}).json()
    assert r["mode"] == "demo" and "budget" in r["notice"]


def test_live_events_filter_and_social(client, live):
    r = client.post("/api/explore", json={"query": "jazz", "kind": "events", "interests": ["jazz"]}).json()
    assert r["mode"] == "live"
    titles = [e["title"] for e in r["results"]]
    assert titles == ["Jazz Night at Storyville"]  # past event dropped
    e = r["results"][0]
    assert e["images"] == ["https://venue.example/img.jpg"] and e["posts"][0]["who"] == "r/Helsinki" and e["art"] == "jazz"


def test_live_products_and_region(client, live):
    r = client.post("/api/products", json={"query": "black waterproof boots under 150", "round": 1}).json()
    assert r["results"][0]["title"] == "Trail Boot" and r["results"][0]["price"] == 120
    q, kw = [c for c in live.calls if "buy" in c[0].lower()][-1]
    assert kw.get("user_location") == "FI"


def test_live_deals_cross_language_and_minor_units(client, live):
    r = client.post("/api/deals", json={"items": [{"id": "o1", "name": "Oat drink 1 L", "qty": 1}], "strategy": "multi"}).json()
    assert r["mode"] == "live"
    lines = [l for p in r["plan"] for l in p["lines"]]
    assert len(lines) == 1 and lines[0]["price"] == 1.79  # 179 corrected from page text; chocolate drink rejected
    assert r["total"] == 1.79 and not r["unpriced"]
