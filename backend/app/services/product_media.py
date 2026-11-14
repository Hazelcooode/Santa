"""Only deliver normalized Cloudinary cutouts; never redirect to merchant originals."""
import hashlib
import threading
import time
import httpx

from .. import db
from ..errors import ApiError
from . import media

_lock = threading.Lock()


def thumbnail(url):
    if not media.safe_url(url) or not media.configured():
        return None
    key = hashlib.sha256(url.encode()).hexdigest()
    db.run('INSERT OR IGNORE INTO product_image_cache(id,source) VALUES(?,?)', (key, url))
    return '/api/v1/product-images/' + key


def cleaned(key):
    """Upload first: background removal explicitly does not support fetch delivery."""
    cloud = media._require()
    row = db.q1('SELECT * FROM product_image_cache WHERE id=?', (key,))
    if not row:
        raise ApiError(404, 'NOT_FOUND', 'Product image not found.')
    if not row.get('asset_id'):
        with _lock:
            row = db.q1('SELECT * FROM product_image_cache WHERE id=?', (key,))
            if not row.get('asset_id'):
                if not media.public_url(row['source']):
                    raise ApiError(400, 'INVALID_IMAGE', 'A public product photo is required.')
                try:
                    result = cloud.uploader.upload(row['source'], public_id='sola/products/' + key,
                        resource_type='image', overwrite=False, backup=False,
                        transformation=[{'width': 2048, 'height': 2048, 'crop': 'limit'}, {'flags': 'strip_profile'}])
                    db.run('UPDATE product_image_cache SET asset_id=? WHERE id=?', (result['asset_id'], key))
                except Exception:
                    raise ApiError(502, 'IMAGE_PROCESSING_FAILED', 'Cloudinary could not prepare this product photo.')
    from cloudinary import CloudinaryImage
    url = CloudinaryImage('sola/products/' + key).build_url(secure=True, sign_url=True, format='png',
        transformation=[{'effect': 'background_removal'}, {'effect': 'improve'}, {'effect': 'sharpen:30'},
                        {'width': 640, 'height': 640, 'crop': 'pad', 'background': 'transparent'}])
    return {'url': url, 'assetId': row.get('asset_id') or result['asset_id']}


def for_generation(key):
    """Wait for the cutout before handing it to a generative model.

    Image-to-video accepts a managed asset ID, so store the cleaned rendition as
    a separate reusable product asset. This cache never contains room photos.
    """
    result = cleaned(key)
    row = db.q1('SELECT clean_asset_id FROM product_image_cache WHERE id=?', (key,))
    if row.get('clean_asset_id'):
        return dict(result, assetId=row['clean_asset_id'])
    try:
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            for attempt in range(18):
                with client.stream('GET', result['url']) as response:
                    if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
                        break
                    if response.status_code not in (420, 423):
                        raise ValueError('Cutout unavailable')
                time.sleep(5)
            else:
                raise ValueError('Cutout still pending')
        asset = media._require().uploader.upload(result['url'], public_id='sola/products/clean_'+key,
            resource_type='image', overwrite=False, backup=False, format='png')
        db.run('UPDATE product_image_cache SET clean_asset_id=? WHERE id=?', (asset['asset_id'], key))
        return dict(result, assetId=asset['asset_id'])
    except Exception:
        raise ApiError(502, 'CUTOUT_NOT_READY', 'Cloudinary is still preparing the product cutout, or background removal is unavailable. Retry shortly.')
