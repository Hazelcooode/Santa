"""Basket camera: the server accepts only on-device summaries, derives the basket,
wardrobe and advice from them, and handles images only with consent."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"taimi-test-frame" * 20 + b"\xff\xd9"
MODEL = {"id": "taimi-laundry-mlp", "version": "1.0", "runtime": "on-device (browser)", "params": 846}


def item(label, colour, conf=0.97, i=0):
    return {"label": label, "colour": colour, "confidence": conf, "bbox": [0.1 + 0.01 * i, 0.2, 0.1, 0.1]}


def frame(fid, items, trigger="history", minutes_ago=60, image=FAKE_JPEG):
    return {"frameId": fid, "capturedAt": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
            "trigger": trigger, "model": MODEL, "imageSha256": hashlib.sha256(image).hexdigest(),
            "imageWidth": 640, "imageHeight": 480, "processingMs": 12, "items": items}


BASE = [item("dark_tshirt", "dark", i=0), item("dark_tshirt", "dark", i=1), item("underwear", "white", i=2),
        item("towel", "white", i=3), item("gym_wear", "colour", i=4)]


@pytest.fixture()
def history(client):
    r = client.post("/api/v1/laundry/observations", json={"reset": True, "observations": [
        frame("bf-test-0", BASE[:2], minutes_ago=300), frame("bf-test-1", BASE, minutes_ago=60)]})
    assert r.status_code == 200, r.text
    client.delete("/api/v1/consents/camera_images_off_device")
    return r.json()


def test_summaries_become_basket_and_advice(client, history):
    st = history
    assert {b["name"]: b["n"] for b in st["basket"]} == {"Dark T-shirts": 2, "Underwear": 1, "Towel": 1, "Gym wear": 1}
    assert {b["group"] for b in st["basket"]} == {"darks", "whites", "sport"}
    cam = st["camera"]
    assert [f["frameId"] for f in cam["frames"]] == ["bf-test-0", "bf-test-1"]
    assert cam["frames"][1]["added"] == [{"label": "gym_wear", "colour": "colour", "n": 1, "name": "pair of gym shorts"},
                                         {"label": "towel", "colour": "white", "n": 1, "name": "towel"},
                                         {"label": "underwear", "colour": "white", "n": 1, "name": "pair of underwear"}]
    assert cam["imagesAllowed"] is False and all(f["image"] is None for f in cam["frames"])
    # every piece of advice carries evidence
    kinds = {s["kind"] for s in st["suggestions"]}
    assert {"runway", "load", "slot"} <= kinds
    for s in st["suggestions"]:
        assert s["evidence"]["why"] and isinstance(s["evidence"]["sources"], list)
    darks = next(s for s in st["suggestions"] if s["id"] == "load-darks")
    assert darks["evidence"]["frames"] == ["bf-test-0"] and "40 °C" in darks["evidence"]["rules"][0]
    assert st["headline"]["text"]
    # the mobile state snapshot keeps its format
    snap = client.get("/api/v1/state").json()
    assert snap["basket"][0].keys() == {"name", "n", "group"}


def test_new_piece_updates_wardrobe_and_adds_colour_advice(client, history):
    before = {w["cat"]: w["clean"] for w in history["wardrobe"]}
    st = client.post("/api/v1/laundry/observations", json={"observations": [
        frame("np-test-2", BASE + [item("colour_tshirt", "colour", i=5)], trigger="new_item", minutes_ago=1)]}).json()
    after = {w["cat"]: w["clean"] for w in st["wardrobe"]}
    assert after["T-shirts"] == max(0, before["T-shirts"] - 1)
    assert st["camera"]["frames"][-1]["added"] == [{"label": "colour_tshirt", "colour": "colour", "n": 1, "name": "colour T-shirt"}]
    ids = [s["id"] for s in st["suggestions"]]
    assert "load-colours" in ids and "colours" in ids
    runway = next(s for s in st["suggestions"] if s["kind"] == "runway")
    if runway["title"].startswith("Wash before t-shirts"):
        assert any("Camera update" == f["label"] for f in runway["evidence"]["facts"])


def test_history_frames_do_not_change_wardrobe(client, history):
    before = {w["cat"]: w["clean"] for w in history["wardrobe"]}
    st = client.post("/api/v1/laundry/observations", json={"observations": [
        frame("bf-test-9", BASE + [item("socks", "dark", i=6)], trigger="history", minutes_ago=30)]}).json()
    assert {w["cat"]: w["clean"] for w in st["wardrobe"]} == before


def test_router_keeps_unsure_frames_on_device_without_consent(client, history):
    st = client.post("/api/v1/laundry/observations", json={"observations": [
        frame("np-test-3", BASE + [item("unknown_item", "colour", conf=0.41, i=7)], trigger="new_item", minutes_ago=1)]}).json()
    last = st["camera"]["frames"][-1]
    assert last["route"] == "device-private" and last["source"] == "device" and last["boxes"] == []
    assert any(s["id"] == "second-look" for s in st["suggestions"])
    assert "confidence" not in json.dumps(st)   # confidence is for the router only, never for the user


def test_buried_garments_still_count_until_basket_is_empty(client, history):
    st = client.post("/api/v1/laundry/observations", json={"observations": [
        frame("bf-test-5", [item("knitwear", "colour", i=0)], minutes_ago=20)]}).json()   # a cardigan on top hides the rest
    names = {b["name"]: b["n"] for b in st["basket"]}
    assert names["Dark T-shirts"] == 2 and names["Knitwear"] == 1 and st["basketCount"] == 6
    assert {"load-delicates", "knitwear"} <= {s["id"] for s in st["suggestions"]}
    st = client.post("/api/v1/laundry/observations", json={"observations": [frame("bf-test-6", [], minutes_ago=10)]}).json()
    assert st["basket"] == [] and st["camera"]["frames"][-1]["removed"]


@pytest.mark.parametrize("mutate", [
    lambda f: f.update(image="data:image/jpeg;base64,AAAA"),           # no field can carry pixels
    lambda f: f["items"][0].update(thumbnail="AAAA"),
    lambda f: f["items"][0].update(label="handbag"),                    # unknown label
    lambda f: f["items"][0].update(confidence=1.5),
    lambda f: f.update(imageSha256="not-a-hash"),
    lambda f: f.update(capturedAt=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat()),
])
def test_rejects_anything_but_a_formatted_summary(client, history, mutate):
    f = frame("np-bad-1", list(BASE), trigger="new_item", minutes_ago=1)
    f["items"] = [dict(i) for i in f["items"]]
    mutate(f)
    r = client.post("/api/v1/laundry/observations", json={"observations": [f]})
    assert r.status_code == 400, r.text


def test_images_only_with_consent_and_matching_fingerprint(client, history):
    data_url = "data:image/jpeg;base64," + base64.b64encode(FAKE_JPEG).decode()
    url = "/api/v1/laundry/frames/bf-test-1/image"
    r = client.post(url, json={"image": data_url})
    assert r.status_code == 403 and r.json()["error"]["code"] == "CONSENT_REQUIRED"
    assert client.get(url).status_code == 403

    assert client.post("/api/v1/consents/camera_images_off_device").status_code == 200
    other = "data:image/jpeg;base64," + base64.b64encode(FAKE_JPEG + b"x").decode()
    r = client.post(url, json={"image": other})
    assert r.status_code == 422 and r.json()["error"]["code"] == "IMAGE_MISMATCH"
    assert client.post("/api/v1/laundry/frames/nope-0000/image", json={"image": data_url}).status_code == 404
    r = client.post(url, json={"image": data_url})
    assert r.status_code == 200 and r.json()["bytes"] == len(FAKE_JPEG) and r.json()["route"]["route"] == "device"  # all sure
    got = client.get(url)
    assert got.status_code == 200 and got.content == FAKE_JPEG and got.headers["content-type"] == "image/jpeg"
    st = client.get("/api/v1/laundry").json()
    assert st["camera"]["imagesAllowed"] and st["camera"]["frames"][1]["image"] == url
    assert {b["label"] for b in st["camera"]["frames"][1]["boxes"]} == {"dark_tshirt", "underwear", "towel", "gym_wear"}

    # withdrawing access deletes what left the device
    client.delete("/api/v1/consents/camera_images_off_device")
    assert client.get(url).status_code == 403
    client.post("/api/v1/consents/camera_images_off_device")
    assert client.get(url).status_code == 404
    client.delete("/api/v1/consents/camera_images_off_device")


def test_edge_scripts_frames_and_models_are_served(client):
    for path in ("/taimi-edge.js", "/taimi-laundry-ui.js", "/laundry-frames/frame-0.jpg", "/laundry-frames/frame-4.jpg"):
        assert client.get(path).status_code == 200, path
    assert "taimi-edge.js" in client.get("/mobile/").text and "taimi-edge.js" in client.get("/").text
    assert client.get("/not-a-file.js").status_code == 404
    edge = client.get("/taimi-edge.js").text
    assert "allowRemoteModels = false" in edge and "/vendor/models/" in edge   # weights load from this server only


def test_reset_restores_wardrobe(client, history):
    before = {w["cat"]: w["clean"] for w in history["wardrobe"]}
    client.post("/api/v1/laundry/observations", json={"observations": [
        frame("np-test-r", BASE + [item("dark_tshirt", "dark", i=8)], trigger="new_item", minutes_ago=1)]})
    st = client.post("/api/v1/laundry/observations", json={"reset": True, "observations": [frame("bf-test-r", BASE)]}).json()
    assert {w["cat"]: w["clean"] for w in st["wardrobe"]} == before


def test_unsure_frame_goes_to_the_agent_only_with_consent(client, history, monkeypatch):
    from types import SimpleNamespace
    from app import llm
    from app.config import settings
    calls = []

    class Msgs:
        def create(self, **kw):
            calls.append(kw)
            reply = {"items": [{"label": "knitwear", "colour": "colour", "bbox": [0.1, 0.1, 0.8, 0.8]},
                               {"label": "jeans", "colour": "dark", "bbox": [0.3, 0.8, 0.3, 0.15]}]}
            if "format" not in kw["output_config"]:   # the headline
                return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Wool cycle tonight.")])
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))])
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(llm, "_client", SimpleNamespace(messages=Msgs()))

    unsure = [item("colour_tshirt", "colour", conf=0.32, i=0), item("jeans", "dark", conf=0.57, i=1)]
    client.post("/api/v1/laundry/observations", json={"reset": True, "observations": [frame("np-agent-1", unsure, trigger="new_item", minutes_ago=2)]})
    assert not any("image" in str(c.get("messages")) for c in calls)   # nothing visual leaves without consent
    data_url = "data:image/jpeg;base64," + base64.b64encode(FAKE_JPEG).decode()
    client.post("/api/v1/consents/camera_images_off_device")
    r = client.post("/api/v1/laundry/frames/np-agent-1/image", json={"image": data_url}).json()
    assert r["route"] == {"route": "agent", "reason": "reviewed", "items": 2}
    sent = next(c for c in calls if "format" in c["output_config"])
    assert sent["messages"][0]["content"][0]["type"] == "image" and sent["model"] == "claude-haiku-5-5"
    st = client.get("/api/v1/laundry").json()
    assert {b["name"] for b in st["basket"]} == {"Knitwear", "Jeans"} and st["camera"]["frames"][-1]["source"] == "agent"
    assert all(b["by"] == "agent" for b in st["camera"]["frames"][-1]["boxes"])
    # withdrawing access deletes the photo and the agent's result: back to the on-device result
    client.delete("/api/v1/consents/camera_images_off_device")
    st = client.get("/api/v1/laundry").json()
    assert {b["name"] for b in st["basket"]} == {"Colour T-shirt", "Jeans"} and st["camera"]["frames"][-1]["source"] == "device"
