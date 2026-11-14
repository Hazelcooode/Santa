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
import json
import socket
import ipaddress
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin, unquote

from .. import db
from ..config import settings
from ..errors import ApiError
from ..exa_client import safe_url

log = logging.getLogger("taimi.media")
_configured = None
def _canvas_data():
    import base64, struct, zlib
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\x00\xf7\xf7\xf3'))+chunk(b'IEND',b'')
    return 'data:image/png;base64,'+base64.b64encode(png).decode()
CANVAS_PNG = _canvas_data()
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

                parsed = urlparse(settings.cloudinary_url)
                if parsed.scheme != 'cloudinary' or not parsed.hostname or not parsed.username or not parsed.password:
                    return False
                cloudinary.config(cloud_name=parsed.hostname, api_key=unquote(parsed.username), api_secret=unquote(parsed.password), secure=True)
                _configured = bool(cloudinary.config().cloud_name)
            except Exception as e:  # pragma: no cover
                log.warning("Cloudinary configuration is invalid.")
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
    if len(urls) >= 2:  # source product gallery; angles may vary
        for i, u in enumerate(urls):
            cloudinary.uploader.upload(u, folder=folder, public_id="%s_%02d" % (tag, i), tags=[tag], overwrite=True,
                                       transformation=[{"width": 720, "height": 720, "crop": "pad", "background": "white"}])
        mode = "product gallery (different photos; camera angles may vary)"
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
        mode = "single-photo animation (2D; not a real 360-degree view)"
    res = cloudinary.uploader.multi(tag, format=fmt, delay=110 if len(urls) < 2 else 180,
                                    transformation=[{"width": 720, "height": 720, "crop": "pad", "background": "white"}])
    return _save(user, "rotation", {"kind": "rotation", "mode": mode, "title": title, "url": res.get("secure_url") or res.get("url"),
                                    "format": fmt, "frames": frames if len(urls) < 2 else len(urls), "tag": tag})


def _canvas(cloudinary):
    import cloudinary.uploader
    pid = "%s/canvas" % settings.cloudinary_folder
    try:
        cloudinary.uploader.upload(CANVAS_PNG, public_id=pid, overwrite=False)
    except Exception:
        raise ApiError(502, 'MEDIA_UPLOAD_FAILED', 'Cloudinary could not create the schedule canvas. Check upload permissions.')
    return pid


def _txt(s, n):
    s = " ".join(str(s or "").split())
    return (s[: n - 1] + "…") if len(s) > n else s


def itinerary_image(user,title,items,subtitle=None,hero_image_url=None,theme_text=None):
    """Illustrate selected event themes and facts; never use an event photo."""
    cloudinary=_require()
    import base64
    import cloudinary.uploader
    from cloudinary import CloudinaryImage
    from .poster import schedule_svg
    if not items:
        raise ApiError(400,'INVALID_INPUT','Add at least one schedule item.')
    svg,theme=schedule_svg(title,items,theme_text or ' '.join(str(i.get('title','')) for i in items))
    data='data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()
    pid='%s/%s/%s'%(settings.cloudinary_folder,user['id'][-8:],_tag(user,'schedule',svg))
    try:
        uploaded=cloudinary.uploader.upload(data,public_id=pid,resource_type='image',overwrite=True)
    except Exception:
        raise ApiError(502,'MEDIA_UPLOAD_FAILED','Cloudinary could not create the illustrated schedule. The saved trip is retained.')
    url=CloudinaryImage(uploaded['public_id']).build_url(format='png',secure=True)
    return _save(user,'itinerary',{'kind':'itinerary','url':url,'title':title,'items':items[:8],'theme':theme,'mode':'Theme illustration based on selected event information; no event photos used'})


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
              {"effect": "zoompan:from_(zoom_1.0);to_(zoom_1.15);du_5;fps_24"}, title_layer]
        if cap_layer:
            tr.append(cap_layer)
        kb.append(CloudinaryImage(pid).build_url(transformation=tr, format="mp4", secure=True))
    poster = CloudinaryImage(ids[0]).build_url(transformation=[{"width": 720, "height": 1280, "crop": "fill", "gravity": "auto"}, title_layer],
                                               format="jpg", secure=True)
    return _save(user, "teaser", {"kind": "teaser", "title": title, "slideshowUrl": slideshow.get("secure_url") or slideshow.get("url"),
                                  "kenBurnsUrls": kb, "posterUrl": poster, "photos": len(ids), "skipped": failed, "mode": "Animated real-source photos; not live event footage", "sourceImages": urls})


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


class ProductPhotos(HTMLParser):
    def __init__(self):
        super().__init__(); self.images=[]; self.in_json=False; self.parts=[]
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='meta' and (a.get('property') or a.get('name')) in ('og:image','og:image:secure_url','twitter:image'):
            if a.get('content'): self.images.append(a['content'])
        if tag=='script' and a.get('type')=='application/ld+json':
            self.in_json=True;self.parts=[]
    def handle_data(self,data):
        if self.in_json:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag!='script' or not self.in_json:return
        self.in_json=False
        try:self.walk(json.loads(''.join(self.parts)))
        except (ValueError,TypeError):pass
    def walk(self,value):
        if isinstance(value,list):
            for item in value:self.walk(item)
        elif isinstance(value,dict):
            types=value.get('@type') or []
            if isinstance(types,str):types=[types]
            if 'Product' in types:
                images=value.get('image') or []
                if not isinstance(images,list):images=[images]
                for item in images:
                    url=item if isinstance(item,str) else item.get('url') or item.get('contentUrl') if isinstance(item,dict) else None
                    if url:self.images.append(url)
            if '@graph' in value:self.walk(value['@graph'])


def public_url(url):
    parsed=urlparse(url or '')
    if not safe_url(url) or parsed.username or parsed.password or parsed.port not in (None,80,443):
        return False
    try:
        addresses=socket.getaddrinfo(parsed.hostname,None)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (ValueError,OSError):return False


def product_images(url, known=None):
    """On-demand extraction of Product JSON-LD and OG images, never arbitrary img tags."""
    import httpx
    photos=list(known or [])
    current=url
    try:
        with httpx.Client(timeout=12,follow_redirects=False,trust_env=False) as client:
            for _ in range(4):
                if not public_url(current):break
                with client.stream('GET',current,headers={'User-Agent':'Taimi product preview/1.0'}) as response:
                    if response.is_redirect:
                        current=urljoin(current,response.headers.get('location',''));continue
                    response.raise_for_status()
                    if 'text/html' not in response.headers.get('content-type',''):break
                    data=bytearray()
                    for piece in response.iter_bytes():
                        data.extend(piece)
                        if len(data)>2_000_000:break
                    parser=ProductPhotos();parser.feed(bytes(data[:2_000_000]).decode('utf-8',errors='replace'))
                    photos=parser.images+photos
                    break
    except (httpx.HTTPError,ValueError):
        pass  # A known research image can still be used if the shop blocks HTML.
    return list(dict.fromkeys(urljoin(current,u) for u in photos if isinstance(u,str) and public_url(urljoin(current,u))))[:12]


def image_thumbnail(url):
    if not safe_url(url):return None
    if not configured():return url
    from cloudinary import CloudinaryImage
    return CloudinaryImage(url).build_url(type='fetch',width=480,height=320,crop='pad',background='rgb:f7f7f3',quality='auto',fetch_format='auto',secure=True)


def playback(user,mid,range_header=None):
    """Same-origin, range-capable playback avoids image/multi MIME/download quirks."""
    import httpx
    import re
    from fastapi.responses import StreamingResponse
    row=db.q1('SELECT payload,kind FROM media_assets WHERE id=? AND user_id=?',(mid,user['id']))
    if not row:raise ApiError(404,'NOT_FOUND','Media not found.')
    if row['kind'] not in ('rotation','teaser'):raise ApiError(400,'INVALID_INPUT','This asset is not a video.')
    payload=db.loads(row['payload'],{});url=payload.get('url') or payload.get('slideshowUrl')
    parsed=urlparse(url or '')
    if parsed.scheme!='https' or not (parsed.hostname or '').endswith('.cloudinary.com'):
        raise ApiError(502,'MEDIA_URL_INVALID','A valid Cloudinary playback URL is required.')
    headers={}
    if range_header:
        if not re.fullmatch(r'bytes=\d*-\d*',range_header):raise ApiError(400,'INVALID_RANGE','Use a single byte range.')
        headers['Range']=range_header
    client=httpx.Client(timeout=30,follow_redirects=False)
    try:
        response=client.send(client.build_request('GET',url,headers=headers),stream=True)
        if response.status_code not in (200,206):
            response.close();client.close()
            raise ApiError(502,'VIDEO_NOT_READY','Cloudinary video is not ready or could not be fetched. Try the direct link or retry shortly.')
    except httpx.HTTPError:
        client.close();raise ApiError(502,'VIDEO_FETCH_FAILED','Video playback failed. Try the direct link.')
    def chunks():
        try:
            yield from response.iter_bytes()
        finally:
            response.close();client.close()
    outgoing={'Content-Disposition':'inline','Accept-Ranges':'bytes','Cache-Control':'private, max-age=300'}
    for key in ('Content-Length','Content-Range'):
        if response.headers.get(key):outgoing[key]=response.headers[key]
    return StreamingResponse(chunks(),status_code=response.status_code,media_type='video/mp4',headers=outgoing)
