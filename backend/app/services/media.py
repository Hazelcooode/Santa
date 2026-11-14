"""Cloudinary media (side challenge), via the Cloudinary Python SDK.

  1. rotation_video  - a turntable clip of a product: real multi-angle photos, or
                        a single photo turned into a pseudo-3D spin (per-frame
                        scale + mirror), stitched with `multi` into MP4/GIF.
  2. itinerary_image - a shareable schedule card for an event/trip plan the
                        agents built: hero photo + text layers, rendered by URL.
  3. event_teaser    - a short vertical teaser from real event photos found by
                        Exa: slideshow MP4 (`multi`) + Ken Burns (`e_zoompan`)
                        clips with a title overlay.

Requires CLOUDINARY_URL=cloudinary://key:secret@cloud_name. Uploads are tagged
per request so nothing collides between users."""
import hashlib
import logging

from .. import db
from ..config import settings
from ..errors import ApiError
from ..exa_client import safe_url

log = logging.getLogger("taimi.media")
_configured = None
CANVAS_PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
COLOR_NAMES = [("black", (20, 20, 20)), ("white", (240, 240, 240)), ("grey", (128, 128, 128)), ("brown", (110, 70, 40)),
               ("beige", (215, 195, 160)), ("red", (190, 30, 40)), ("blue", (40, 70, 160)), ("navy", (25, 35, 70)),
               ("green", (50, 120, 60)), ("yellow", (230, 200, 40)), ("pink", (230, 150, 180)), ("purple", (120, 70, 150))]


def configured():
    global _configured
    if _configured is None:
        _configured = False
        if settings.cloudinary_url:
            try:
                import cloudinary

                cloudinary.config(cloudinary_url=settings.cloudinary_url, secure=True)
                _configured = bool(cloudinary.config().cloud_name)
            except Exception as e:  # pragma: no cover
                log.warning("Cloudinary config failed: %s", e)
    return _configured


def _require():
    if not configured():
        raise ApiError(503, "PROVIDER_NOT_CONFIGURED", "Media generation needs CLOUDINARY_URL on the server.", retryable=False)
    import cloudinary.uploader  # noqa: F401

    return cloudinary


def _tag(user, kind, seed):
    return "taimi_%s_%s_%s" % (kind, user["id"][-8:], hashlib.sha1(seed.encode()).hexdigest()[:10])


def _save(user, kind, payload):
    mid = db.new_id("md_")
    db.run("INSERT INTO media_assets(id,user_id,kind,payload,created_at) VALUES(?,?,?,?,?)", (mid, user["id"], kind, db.dumps(payload), db.iso()))
    return dict(payload, id=mid)


def _clean_urls(urls, limit):
    out = []
    for u in urls or []:
        u = safe_url(u) if isinstance(u, str) and not u.startswith("data:image") else u
        if u and u not in out:
            out.append(u)
    return out[:limit]


def rotation_video(user, image_urls, title=None, fmt="mp4", frames=12):
    cloudinary = _require()
    import cloudinary.uploader

    urls = _clean_urls(image_urls, 24)
    if not urls:
        raise ApiError(400, "INVALID_INPUT", "Send at least one product image URL (or data URL).")
    tag = _tag(user, "spin", "|".join(urls) + fmt)
    folder = "%s/%s" % (settings.cloudinary_folder, user["id"][-8:])
    if len(urls) >= 4:  # real multi-angle shots
        for i, u in enumerate(urls):
            cloudinary.uploader.upload(u, folder=folder, public_id="%s_%02d" % (tag, i), tags=[tag], overwrite=True,
                                       transformation=[{"width": 720, "height": 720, "crop": "pad", "background": "white"}])
        mode = "multi-angle"
    else:  # pseudo-3D turntable from one photo
        import math
        base = cloudinary.uploader.upload(urls[0], folder=folder, public_id=tag + "_src", overwrite=True)
        for i in range(frames):
            theta = 2 * math.pi * i / frames
            f = max(0.06, abs(math.cos(theta)))
            steps = [{"width": 720, "height": 720, "crop": "pad", "background": "white"},
                     {"width": max(40, int(720 * f)), "height": 720, "crop": "scale"}]
            if math.pi / 2 < theta < 3 * math.pi / 2:
                steps.append({"angle": "hflip"})
            steps.append({"width": 720, "height": 720, "crop": "pad", "background": "white"})
            cloudinary.uploader.upload(base["secure_url"], folder=folder, public_id="%s_%02d" % (tag, i), tags=[tag], overwrite=True,
                                       transformation=steps)
        mode = "single-photo spin"
    res = cloudinary.uploader.multi(tag, format=fmt, delay=110 if mode != "multi-angle" else 180,
                                    transformation=[{"width": 720, "height": 720, "crop": "pad", "background": "white"}])
    return _save(user, "rotation", {"kind": "rotation", "mode": mode, "title": title, "url": res.get("secure_url") or res.get("url"),
                                    "format": fmt, "frames": frames if mode != "multi-angle" else len(urls), "tag": tag})


def _canvas(cloudinary):
    import cloudinary.uploader
    pid = "%s/canvas" % settings.cloudinary_folder
    try:
        cloudinary.uploader.upload(CANVAS_PNG, public_id=pid, overwrite=False)
    except Exception as e:  # already exists is fine
        log.debug("canvas upload: %s", e)
    return pid


def _txt(s, n):
    s = " ".join(str(s or "").split())
    return (s[: n - 1] + "…") if len(s) > n else s


def itinerary_image(user, title, items, subtitle=None, hero_image_url=None):
    """items: [{"time": "Fri 17:05", "title": "Flight HEL → RVN", "where": "..."}] (max 8)."""
    cloudinary = _require()
    from cloudinary import CloudinaryImage

    if not items:
        raise ApiError(400, "INVALID_INPUT", "Add at least one schedule item.")
    pid = _canvas(cloudinary)
    tr = [{"width": 1080, "height": 1350, "crop": "scale", "background": "rgb:F7F7F3"}]
    y = 80
    hero = safe_url(hero_image_url) if hero_image_url else None
    if hero:
        tr.append({"overlay": {"url": hero}, "width": 1080, "height": 520, "crop": "fill", "gravity": "north", "y": 0})
        tr.append({"overlay": {"font_family": "Arial", "font_size": 30, "font_weight": "bold", "text": "TAIMI PLAN"},
                   "color": "#FFFEFA", "background": "rgb:8B75A9", "gravity": "north_west", "x": 48, "y": 40})
        y = 560
    tr.append({"overlay": {"font_family": "Arial", "font_size": 64, "font_weight": "bold", "text": _txt(title, 34)},
               "color": "#353B35", "gravity": "north_west", "x": 60, "y": y})
    y += 90
    if subtitle:
        tr.append({"overlay": {"font_family": "Arial", "font_size": 34, "text": _txt(subtitle, 52)}, "color": "#8B75A9",
                   "gravity": "north_west", "x": 60, "y": y})
        y += 64
    step = max(70, min(100, int((1300 - y) / max(1, len(items[:8])))))
    for it in items[:8]:
        tr.append({"overlay": {"font_family": "Arial", "font_size": 32, "font_weight": "bold", "text": _txt(it.get("time"), 16)},
                   "color": "#D6744C", "gravity": "north_west", "x": 60, "y": y})
        tr.append({"overlay": {"font_family": "Arial", "font_size": 34, "font_weight": "bold", "text": _txt(it.get("title"), 38)},
                   "color": "#353B35", "gravity": "north_west", "x": 330, "y": y})
        if it.get("where"):
            tr.append({"overlay": {"font_family": "Arial", "font_size": 26, "text": _txt(it["where"], 48)}, "color": "#6B6F68",
                       "gravity": "north_west", "x": 330, "y": y + 40})
        y += step
    tr.append({"overlay": {"font_family": "Arial", "font_size": 24, "text": "Sources checked live with Exa · made with Taimi"},
               "color": "#9A9C95", "gravity": "south_west", "x": 60, "y": 40})
    url = CloudinaryImage(pid).build_url(transformation=tr, format="png", secure=True)
    return _save(user, "itinerary", {"kind": "itinerary", "url": url, "title": title, "items": items[:8]})


def event_teaser(user, image_urls, title, caption=None):
    cloudinary = _require()
    import cloudinary.uploader
    from cloudinary import CloudinaryImage

    urls = _clean_urls(image_urls, 6)
    if not urls:
        raise ApiError(400, "INVALID_INPUT", "Need at least one event photo URL (Exa results include `images`).")
    tag = _tag(user, "teaser", "|".join(urls) + (title or ""))
    folder = "%s/%s" % (settings.cloudinary_folder, user["id"][-8:])
    ids, failed = [], []
    for i, u in enumerate(urls):
        try:
            r = cloudinary.uploader.upload(u, folder=folder, public_id="%s_%02d" % (tag, i), tags=[tag], overwrite=True)
            ids.append(r["public_id"])
        except Exception as e:  # remote image may block hotlinking
            failed.append({"url": u, "error": str(e)[:120]})
    if not ids:
        raise ApiError(502, "MEDIA_FETCH_FAILED", "Couldn't fetch any of the event photos.", details=failed)
    title_layer = {"overlay": {"font_family": "Arial", "font_size": 54, "font_weight": "bold", "text": _txt(title, 30)},
                   "color": "#FFFEFA", "background": "rgb:353B35", "gravity": "south", "y": 140}
    cap_layer = {"overlay": {"font_family": "Arial", "font_size": 34, "text": _txt(caption, 44)}, "color": "#FFFEFA",
                 "gravity": "south", "y": 80} if caption else None
    slideshow = cloudinary.uploader.multi(tag, format="mp4", delay=1600,
                                          transformation=[{"width": 720, "height": 1280, "crop": "fill", "gravity": "auto"}])
    kb = []
    for pid in ids[:3]:
        tr = [{"width": 720, "height": 1280, "crop": "fill", "gravity": "auto"},
              {"effect": "zoompan:mode_ztr;maxzoom_1.35;du_5"}, title_layer]
        if cap_layer:
            tr.append(cap_layer)
        kb.append(CloudinaryImage(pid).build_url(transformation=tr, format="mp4", secure=True))
    poster = CloudinaryImage(ids[0]).build_url(transformation=[{"width": 720, "height": 1280, "crop": "fill", "gravity": "auto"}, title_layer],
                                               format="jpg", secure=True)
    return _save(user, "teaser", {"kind": "teaser", "title": title, "slideshowUrl": slideshow.get("secure_url") or slideshow.get("url"),
                                  "kenBurnsUrls": kb, "posterUrl": poster, "photos": len(ids), "skipped": failed})


def dominant_color(user, data_url):
    if not configured():
        return None
    try:
        import cloudinary.uploader
        r = cloudinary.uploader.upload(data_url, folder="%s/%s/ref" % (settings.cloudinary_folder, user["id"][-8:]), colors=True)
        hexes = [c[0] for c in (r.get("colors") or [])][:3]
    except Exception as e:
        log.warning("colour analysis failed: %s", e)
        return None
    for hx in hexes:
        rgb = tuple(int(hx.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        name = min(COLOR_NAMES, key=lambda c: sum((a - b) ** 2 for a, b in zip(c[1], rgb)))[0]
        if name not in ("white",):  # skip studio backgrounds
            return name
    return None


def list_media(user, limit=20):
    rows = db.q("SELECT id,kind,payload,created_at FROM media_assets WHERE user_id=? ORDER BY created_at DESC LIMIT ?", (user["id"], limit))
    return [dict(db.loads(r["payload"], {}), id=r["id"], createdAt=r["created_at"]) for r in rows]
