"""Credential-free readiness report and explicit provider probes. Never return secrets."""
import time
import threading

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .. import db, exa_client, llm
from ..auth import CurrentUser, token_from_request, user_for_token
from ..config import settings
from ..errors import ApiError
from ..services import media

router = APIRouter(tags=['integrations'])
_checks = {}
_lock = threading.Lock()


@router.get('/api/v1/integrations')
def status(user=CurrentUser):
    db.q1('SELECT 1')
    return {'environment': settings.environment, 'dataMode': settings.data_mode, 'database': 'sqlite',
            'providers': {'exa': {'configured': bool(settings.exa_api_key), 'mode': exa_client.effective_mode()},
                          'cloudinary': {'configured': media.configured()}, 'gemini': {'configured': llm.available(), 'model': settings.gemini_model}},
            'scheduler': settings.scheduler_enabled, 'automaticPriceLookup': settings.auto_price_lookup,
            'simulations': ['checkout','payment','laundry reservation','calendar-provider sync','ride booking','SMS/social/emergency delivery','camera inference','biometric verification','wearable sample data and health reminders'],
            'notice': 'Configured means a credential is present, not that it has been verified. Probes are explicit and may use provider credits.'}


@router.post('/api/v1/integrations/{provider}/check')
def check(provider: str, user=CurrentUser):
    if provider not in ('exa','cloudinary','gemini'):
        raise ApiError(404,'NOT_FOUND','Unknown provider.')
    with _lock:
        key=(user['id'],provider)
        if time.monotonic()-_checks.get(key, -1000)<30:
            raise ApiError(429,'RATE_LIMITED','Wait 30 seconds between provider checks.',headers={'Retry-After':'30'})
        _checks[key]=time.monotonic()
    if provider=='exa':
        response=exa_client.search(user['id'],'places','Exa official search API documentation',num_results=1,include_domains=['exa.ai'],force_refresh=True)
        return {'provider':provider,'ok':response['available'],'source':response.get('source'),'reason':response.get('reason'),'resultCount':len(response.get('results',[])), 'costUsd':response.get('costUsd',0)}
    if provider=='gemini':
        if not llm.available():
            raise ApiError(503,'PROVIDER_NOT_CONFIGURED','Set GEMINI_API_KEY and an available MODEL_ID.')
        value=llm.complete('Reply with the single word OK.', [('user','Connection check')], max_tokens=20, temperature=0)
        return {'provider':provider,'ok':bool(value),'model':settings.gemini_model,'notice':'Failure can mean an invalid key, unavailable model, quota or network error.' if not value else 'Model responded.'}
    if not media.configured():
        raise ApiError(503,'PROVIDER_NOT_CONFIGURED','Set CLOUDINARY_URL.')
    try:
        import cloudinary.api
        result=cloudinary.api.ping(timeout=15)
        return {'provider':provider,'ok':result.get('status')=='ok'}
    except Exception:
        raise ApiError(502,'PROVIDER_CHECK_FAILED','Cloudinary check failed. Verify credentials, network access and account permissions.',retryable=True)


@router.get('/integrations',response_class=HTMLResponse,include_in_schema=False)
def page(request: Request):
    if not user_for_token(token_from_request(request)):
        return RedirectResponse('/login?next=/integrations',status_code=303)
    return HTMLResponse('''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Integration status · Taimi</title><link rel="stylesheet" href="/src/styles.css"><link rel="stylesheet" href="/src/live-shopping.css"><main style="max-width:950px;margin:auto"><p class="eyebrow">LOCAL TESTING & RELEASE STATUS</p><h1>Your integrations</h1><p>Keys stay on the server. Checks are manual and may consume provider credits. No purchase, upload or message is sent by these probes.</p><p><a href="/">Website</a> · <a href="/mobile/">Mobile interface</a> · <a href="/docs">Test every API function</a></p><section class="panel" id="integration-status">Loading…</section><p id="probe-status" role="status"></p><section class="panel" style="margin-top:20px"><h2>What is simulated?</h2><p id="simulation-list"></p><p>Provider API keys do not turn these simulations into real services. Research and media endpoints can be tested through the API explorer. Use a fresh registered account for real input; the seeded test account intentionally contains fixtures.</p></section><script type="module" src="/src/integrations.js"></script></main></html>''',headers={'Cache-Control':'no-store'})
