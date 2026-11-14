"""All Cloudinary generation/upload/deletion calls are mocked. No paid API calls."""
import base64
import time

import cloudinary
import cloudinary.api
import cloudinary.uploader
import pytest

from app import db
from app.config import settings
from app.errors import ApiError
from app.services import media, product_media, visual_previews as visual, watches


@pytest.fixture
def studio(client, monkeypatch):
    user = db.q1('SELECT * FROM users WHERE email=?', (settings.test_email,))
    db.run('DELETE FROM visual_sessions')
    queued, uploads, deletions, calls = [], [], [], []
    monkeypatch.setattr(cloudinary.config(), 'cloud_name', 'offline')
    monkeypatch.setattr(cloudinary.config(), 'api_secret', 'offline-secret')
    monkeypatch.setattr(visual._pool, 'submit', lambda fn, *args: queued.append((fn, args)))
    monkeypatch.setattr(media, '_require', lambda: cloudinary)
    monkeypatch.setattr(media, 'configured', lambda: True)
    monkeypatch.setattr(media, 'public_url', lambda url: url.startswith('https://shop.example/'))
    monkeypatch.setattr(product_media, 'for_generation', lambda key: {'url': 'https://res.cloudinary.com/offline/image/upload/e_background_removal/item.png', 'assetId': 'product-asset'})
    monkeypatch.setattr(cloudinary.api, 'create_upload_preset', lambda **kw: {})
    monkeypatch.setattr(cloudinary.api, 'delete_upload_preset', lambda preset: {})
    monkeypatch.setattr(cloudinary.uploader, 'upload', lambda raw, **kw: uploads.append((raw, kw)) or {'asset_id': 'room-asset'})
    monkeypatch.setattr(cloudinary.uploader, 'destroy', lambda pid, **kw: deletions.append((pid, kw)) or {'result': 'ok'})
    # Keep the privacy-failure case offline, including the new delivery-type conversion.
    def denied_rename(*args, **kwargs):
        raise RuntimeError('Offline fixture: rename permission denied')
    monkeypatch.setattr(cloudinary.uploader, 'rename', denied_rename)
    def api(method, path, **kw):
        calls.append((method, path, kw))
        if 'image_to_image' in path:
            return {'assets': [{'storage': {'public_id': kw['json']['target']['public_id'], 'type': 'authenticated'}}]}
        if method == 'POST':
            return {'job_id': 'video-job', 'status': 'pending'}
        return {'job_id': 'video-job', 'status': 'completed', 'public_id': 'generated/turn', 'delivery_type': 'upload'}
    monkeypatch.setattr(visual, '_api', api)
    offers = [{'id': 'opt-1', 'title': 'Green chair', 'url': 'https://shop.example/chair', 'images': ['https://shop.example/chair.jpg']}]
    token = watches._proof(user, {'query': 'Chair'}, offers)
    body = {'kind': 'space', 'saveToken': token, 'optionId': 'opt-1',
            'imageData': 'data:image/jpeg;base64,' + base64.b64encode(b'\xff\xd8\xfftest-offline-image').decode()}
    yield client, user, body, queued, uploads, deletions, calls
    visual._active.clear()
    db.run('DELETE FROM visual_sessions')


def run_queued(queued):
    fn, args = queued.pop(0)
    fn(*args)


def test_room_preview_uses_private_assets_never_gallery_and_close_deletes(studio):
    client, user, body, queued, uploads, deletions, calls = studio
    gallery_count = db.q1('SELECT COUNT(*) AS n FROM media_assets')['n']
    r = client.post('/api/v1/visual-previews', json=body)
    assert r.status_code == 202, r.text
    sid = r.json()['id']
    run_queued(queued)
    ready = client.get('/api/v1/visual-previews/' + sid).json()
    assert ready['status'] == 'ready'
    assert ready['url'] == '/api/v1/visual-previews/' + sid + '/content'
    assert uploads[0][1]['type'] == 'authenticated' and uploads[0][1]['backup'] is False
    prompt = calls[0][2]['json']
    assert 'INTERIOR / OBJECT PLACEMENT' in prompt['prompt'] and 'replace' in prompt['prompt']
    assert prompt['reference_images'][0] == {'source_type': 'managed_asset', 'asset_id': 'room-asset'}
    assert prompt['target']['upload_preset']
    assert db.q1('SELECT COUNT(*) AS n FROM media_assets')['n'] == gallery_count
    assert any(pid.endswith('/room') for pid, _ in deletions)
    stored = db.dumps(visual._row(sid))
    assert body['imageData'] not in stored and 'test-offline-image' not in stored
    assert client.delete('/api/v1/visual-previews/' + sid).status_code == 200
    assert client.get('/api/v1/visual-previews/' + sid + '/content').status_code == 410
    visual.sweep()
    assert any(pid.endswith('/result') for pid, _ in deletions)
    assert visual._row(sid) is None


def test_close_while_queued_prevents_photo_upload(studio):
    client, user, body, queued, uploads, deletions, calls = studio
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    client.delete('/api/v1/visual-previews/' + sid)
    run_queued(queued)
    assert uploads == [] and calls == []
    assert sid not in visual._active


def test_only_app_products_valid_photos_and_owner_can_access(studio):
    client, user, body, queued, *_ = studio
    assert client.post('/api/v1/visual-previews', json=dict(body, optionId='foreign-option')).status_code == 404
    assert client.post('/api/v1/visual-previews', json=dict(body, saveToken='forged')).status_code == 410
    assert client.post('/api/v1/visual-previews', json=dict(body, imageData='data:image/jpeg;base64,PGh0bWw+')).status_code == 400
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    with pytest.raises(ApiError) as err:
        visual.state({'id': 'other-account'}, sid)
    assert err.value.status == 404
    with pytest.raises(ApiError):
        visual.close({'id': 'other-account'}, sid)


def test_generation_after_close_is_never_visible_and_is_destroyed(studio, monkeypatch):
    client, user, body, queued, uploads, deletions, calls = studio
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    def closes_during_generation(method, path, **kw):
        visual.close(user, sid)
        return {'assets': [{'storage': {'public_id': 'late/result', 'type': 'authenticated'}}]}
    monkeypatch.setattr(visual, '_api', closes_during_generation)
    run_queued(queued)
    assert client.get('/api/v1/visual-previews/' + sid).status_code == 410
    assert any(pid == 'late/result' for pid, _ in deletions)


def test_public_room_output_fails_closed(studio, monkeypatch):
    client, user, body, queued, uploads, deletions, calls = studio
    monkeypatch.setattr(visual, '_api', lambda *a, **k: {'assets': [{'storage': {'public_id': 'bad/public-result', 'type': 'upload'}}]})
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    assert visual.state(user, sid)['status'] == 'failed'
    assert visual.state(user, sid)['url'] is None
    assert any(pid == 'bad/public-result' for pid, _ in deletions)
    visual.sweep()
    # Cleanup must not hide the useful provider/privacy failure from the poller.
    assert visual.state(user, sid)['status'] == 'failed'


def test_video_requests_object_yaw_not_flat_rotation(studio):
    client, user, body, queued, uploads, deletions, calls = studio
    body.update(kind='turn', imageData=None)
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    payload = calls[0][2]['json']
    assert payload['duration'] == 6 and payload['generate_audio'] is False
    assert payload['image_asset_id'] == 'room-asset'  # Mocked beige studio-frame upload.
    assert 'complete 360-degree turn' in payload['prompt'] and 'front view at 360' in payload['prompt']
    assert 'not the flat image' in payload['prompt']
    assert visual.state(user, sid)['status'] == 'ready'
    assert len(uploads) == 1 and uploads[0][1]['public_id'].startswith('sola/products/turn_')
    assert 'b_rgb:f3e8dc' in uploads[0][0]
    visual.close(user, sid); visual.sweep()
    assert any(pid == 'generated/turn' and kw['resource_type'] == 'video' for pid, kw in deletions)


def test_async_image_task_is_polled_and_private_output_is_recorded(studio, monkeypatch):
    client, user, body, queued, *_ = studio
    target = {}
    def api(method, path, **kw):
        if method == 'POST':
            target.update(kw['json']['target'])
            assert kw['json']['async'] is True
            return {'task_id': 'image-task', 'status': 'pending', 'result': None}
        assert path.endswith('/tasks/image-task')
        return {'task_id': 'image-task', 'status': 'completed', 'result': {
            'assets': [{'storage': {'public_id': target['public_id'], 'type': 'authenticated'}}]}}
    monkeypatch.setattr(visual, '_api', api)
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    assert visual.state(user, sid)['status'] == 'ready'
    assert visual._row(sid)['provider_job'] is None


def test_video_proxy_has_five_second_transform_ranges_and_no_store(studio, monkeypatch):
    import httpx
    client, user, body, queued, *_ = studio
    body.update(kind='turn', imageData=None)
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    monkeypatch.setattr(cloudinary.config(), 'cloud_name', 'offline')
    monkeypatch.setattr(cloudinary.config(), 'api_secret', 'offline-secret')
    real_client = httpx.Client
    seen = []
    def transport(req):
        seen.append(req)
        return httpx.Response(206, content=b'vid', headers={'Content-Type': 'video/mp4', 'Content-Range': 'bytes 0-2/20'})
    monkeypatch.setattr(httpx, 'Client', lambda **kw: real_client(transport=httpx.MockTransport(transport), **kw))
    r = client.get('/api/v1/visual-previews/' + sid + '/content', headers={'Range': 'bytes=0-2'})
    assert r.status_code == 206 and r.content == b'vid'
    assert r.headers['content-type'] == 'video/mp4'
    assert r.headers['cache-control'] == 'no-store'
    assert seen[0].headers['Range'] == 'bytes=0-2'
    assert 'e_accelerate:20' in str(seen[0].url) and 'du_5' in str(seen[0].url) and 'vc_h264' in str(seen[0].url)
    r = client.get('/api/v1/visual-previews/' + sid + '/content?download=true')
    assert r.headers['content-disposition'].startswith('attachment;')


def test_provider_delete_failure_retains_cleanup_ledger(studio, monkeypatch):
    client, user, body, queued, *_ = studio
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    visual.close(user, sid)
    monkeypatch.setattr(cloudinary.uploader, 'destroy', lambda *a, **k: (_ for _ in ()).throw(RuntimeError('offline outage')))
    visual.sweep()
    assert visual._row(sid) is not None
    assert visual._row(sid)['cleanup_after'] > time.time()
    monkeypatch.setattr(cloudinary.uploader, 'destroy', lambda *a, **k: {'result': 'ok'})
    db.run('UPDATE visual_sessions SET cleanup_after=0 WHERE id=?', (sid,))
    visual.sweep()
    assert visual._row(sid) is None


def test_restart_recovers_late_private_image_and_deletes_it(studio, monkeypatch):
    client, user, body, queued, uploads, deletions, calls = studio
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    visual._active.discard(sid)  # Simulate a process restart losing in-memory work.
    queued.clear()
    db.run("UPDATE visual_sessions SET provider_job='orphan-task',status='running' WHERE id=?", (sid,))
    def recovered(method, path, **kw):
        assert path.endswith('/tasks/orphan-task')
        return {'status': 'completed', 'result': {'assets': [{'storage': {
            'public_id': 'temporary/orphan-result', 'type': 'authenticated'}}]}}
    monkeypatch.setattr(visual, '_api', recovered)
    visual.sweep()
    assert any(pid == 'temporary/orphan-result' and kw['type'] == 'authenticated' for pid, kw in deletions)
    assert visual._row(sid)['cancelled'] == 1


def test_expired_preview_cannot_be_streamed_and_is_cleaned(studio):
    client, user, body, queued, uploads, deletions, calls = studio
    sid = client.post('/api/v1/visual-previews', json=body).json()['id']
    run_queued(queued)
    db.run('UPDATE visual_sessions SET expires=? WHERE id=?', (time.time()-1, sid))
    assert client.get('/api/v1/visual-previews/' + sid + '/content').status_code == 410
    visual.sweep()
    assert visual._row(sid) is None


def test_missing_cloudinary_never_exposes_original_thumbnail(monkeypatch):
    monkeypatch.setattr(media, 'configured', lambda: False)
    assert media.image_thumbnail('https://shop.example/original.jpg') is None


def test_cutouts_upload_before_removal_and_have_equal_transparent_size(client, monkeypatch):
    monkeypatch.setattr(media, 'configured', lambda: True)
    monkeypatch.setattr(media, '_require', lambda: cloudinary)
    monkeypatch.setattr(media, 'public_url', lambda url: True)
    upload = []
    monkeypatch.setattr(cloudinary.uploader, 'upload', lambda source, **kw: upload.append((source, kw)) or {'asset_id': 'asset'})
    # Explicit dummy cloud config is local SDK state, never real credentials.
    monkeypatch.setattr(cloudinary.config(), 'cloud_name', 'offline')
    monkeypatch.setattr(cloudinary.config(), 'api_secret', 'offline-secret')
    path = product_media.thumbnail('https://shop.example/offline-cutout.jpg')
    result = client.get(path, follow_redirects=False)
    assert result.status_code == 307
    url = result.headers['location']
    assert '/image/upload/' in url and '/fetch/' not in url
    assert 'e_background_removal' in url and 'e_improve' in url and 'e_sharpen:30' in url
    assert 'h_640' in url and 'w_640' in url and 'b_transparent' in url and url.endswith('.png')
    assert len(upload) == 1
    client.get(path, follow_redirects=False)
    assert len(upload) == 1
