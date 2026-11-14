"""Account-owned research snapshots and multi-search event itineraries."""
import threading
import time
from copy import deepcopy
from .. import db
from ..errors import ApiError
from . import media


_drafts={}
_draft_guard=threading.Lock()


def remember_search(user, query, kind, result):
    """Short-lived references allow explicit trip saving; no research history."""
    sid=db.new_id('rs_');now=time.monotonic()
    with _draft_guard:
        for key,(expires,_) in list(_drafts.items()):
            if expires<=now: _drafts.pop(key,None)
        owned=[key for key in _drafts if key[0]==user['id']]
        for key in owned[:-11]:_drafts.pop(key,None)
        while len(_drafts)>=256:_drafts.pop(next(iter(_drafts)))
        _drafts[(user['id'],sid)]=(now+1800,deepcopy(result))
    return sid


def searches(user):
    return {'items':[]}  # Past unsaved outputs are intentionally not restored.


def get(user, pid):
    row=db.q1('SELECT * FROM saved_itineraries WHERE user_id=? AND id=?',(user['id'],pid))
    if not row:
        raise ApiError(404,'NOT_FOUND','Saved trip not found.')
    return dict(db.loads(row['payload'],{}),id=row['id'],createdAt=row['created_at'],updatedAt=row['updated_at'])


def list_plans(user):
    return {'items':[get(user,r['id']) for r in db.q('SELECT id FROM saved_itineraries WHERE user_id=? ORDER BY rowid DESC LIMIT 50',(user['id'],))]}


def create(user, title, choices):
    if not 1 <= len(choices) <= 8:
        raise ApiError(400,'INVALID_INPUT','Choose 1–8 events/options for a trip.')
    items=[];seen=set()
    for choice in choices:
        with _draft_guard:
            draft=_drafts.get((user['id'],choice['searchId']))
            output=deepcopy(draft[1]) if draft and draft[0]>time.monotonic() else None
        if output is None:
            raise ApiError(410,'RESEARCH_EXPIRED','This temporary output expired. Run a new prompt before saving it.')
        event=next((r for r in output.get('results',[]) if r['id']==choice['resultId']),None)
        if not event:
            raise ApiError(404,'NOT_FOUND','Event/option not found in that research output.')
        key=event.get('url') or event['id']
        if key in seen:
            continue
        seen.add(key)
        items.append(dict(event,searchId=choice['searchId']))
    if not items:
        raise ApiError(400,'INVALID_INPUT','Choose at least one event.')
    items.sort(key=lambda e:(e.get('startDate') or '9999', e.get('startTime') or ''))
    pid=db.new_id('ip_'); now=db.iso()
    payload={'title':title.strip() or 'My trip','items':items,'teasers':{},'notice':'Saved research plan, not a booking. Date ranges are event opening windows; review exact visit times and prices at the source.'}
    db.run('INSERT INTO saved_itineraries(id,user_id,payload,created_at,updated_at) VALUES(?,?,?,?,?)',(pid,user['id'],db.dumps(payload),now,now))
    return get(user,pid)


def delete(user,pid):
    get(user,pid)
    db.run('DELETE FROM saved_itineraries WHERE id=? AND user_id=?',(pid,user['id']))


_locks={}
_guard=threading.Lock()


def generate(user,pid,kind,event_ids=None):
    # Single-process SQLite deployment: serialize media creation per plan so
    # concurrent requests cannot bypass the three-event limit.
    with _guard:
        lock=_locks.setdefault((user['id'],pid),threading.Lock())
    if not lock.acquire(blocking=False):
        raise ApiError(409,'MEDIA_RUNNING','Media is already being created for this trip.')
    try:
        return _generate(user,pid,kind,event_ids)
    finally:
        lock.release()


def _generate(user,pid,kind,event_ids=None):
    plan=get(user,pid)
    if kind=='schedule':
        rows=[]
        for event in plan['items']:
            when=event.get('when') or 'Time not specified'
            date_range=' – '.join(dict.fromkeys(x for x in [event.get('startDate'),event.get('endDate')] if x))
            if date_range:
                when=date_range+' '+(event.get('startTime') or '')
                if event.get('endTime'):
                    when+=' – '+event['endTime']
            rows.append({'time':when,'title':event['title'],'where':' · '.join(x for x in [event.get('where'),event.get('price') or 'Price unknown'] if x)})
        plan['schedule']=media.itinerary_image(user,plan['title'],rows,'Dates, places & sourced prices',theme_text=' '.join([plan['title']]+[e.get('title','')+' '+e.get('summary','')+' '+' '.join(e.get('tags') or []) for e in plan['items']]))
    elif kind=='teasers':
        event_ids=list(dict.fromkeys(event_ids or []))
        current=plan.get('teasers') or {}
        if not event_ids or len(set(event_ids)|set(current))>3:
            raise ApiError(400,'TEASER_LIMIT','Choose at most 3 distinct events per saved trip for video previews.')
        events={e['id']:e for e in plan['items']}
        if any(eid not in events for eid in event_ids):
            raise ApiError(400,'INVALID_INPUT','Choose events from this saved trip.')
        if any(not events[eid].get('images') for eid in event_ids):
            raise ApiError(400,'NO_EVENT_PHOTOS','A selected event has no real source photos; choose another event.')
        # Persist each completed clip immediately; retrying does not regenerate it.
        for eid in event_ids:
            if eid in current:
                continue
            event=events[eid]
            current[eid]=dict(media.event_teaser(user,event['images'],event['title'],event.get('when')),eventId=eid,sources=event.get('sources') or [])
            plan['teasers']=current
            db.run('UPDATE saved_itineraries SET payload=?,updated_at=? WHERE id=? AND user_id=?',(db.dumps(plan),db.iso(),pid,user['id']))
    else:
        raise ApiError(400,'INVALID_INPUT','Choose schedule or teasers.')
    db.run('UPDATE saved_itineraries SET payload=?,updated_at=? WHERE id=? AND user_id=?',(db.dumps(plan),db.iso(),pid,user['id']))
    return get(user,pid)


def printable(user,pid):
    from html import escape
    p=get(user,pid)
    rows=''.join('<article><p class="when">%s</p><h2>%s</h2><p>%s &middot; %s</p><p>%s</p>%s</article>' % (
        escape(e.get('when') or 'Schedule not specified'),escape(e['title']),escape(e.get('where') or 'See source'),
        escape(e.get('price') or 'Price unknown'),escape(e.get('summary') or ''),
        ''.join('<p><a href="%s">%s</a></p>' % (escape(source['url'],quote=True),escape(source.get('title') or 'Original event')) for source in e.get('sources',[]))) for e in p['items'])
    return '<!doctype html><html lang="en"><meta charset="utf-8"><title>%s - Sola itinerary</title><style>body{font:15px/1.6 system-ui;color:#292d2c;background:#f7f7f3;max-width:800px;margin:40px auto;padding:0 24px}h1{font-size:32px}h2{font-size:20px}article{background:#fffefa;border:1px solid #e7e8e1;border-radius:12px;padding:22px;margin:18px 0;break-inside:avoid}.when{color:#a75a3d;font-size:12px}a{color:#594972;overflow-wrap:anywhere}button{background:#353b35;color:white;border:0;border-radius:8px;padding:12px 20px;cursor:pointer}@media print{body{background:white;margin:0;max-width:none}button{display:none}}</style><body><p>SOLA / YOUR SAVED ITINERARY</p><h1>%s</h1><p>%s</p><button onclick="window.print()">Print / Save as PDF</button>%s<p>Source information only. No tickets or transport have been booked. Review opening windows, local times, prices and travel feasibility.</p></body></html>' % (escape(p['title']),escape(p['title']),escape(p.get('notice') or ''),rows)


def calendar_file(user,pid):
    from datetime import date,timedelta
    p=get(user,pid)
    def text(value):
        return str(value or '').replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Sola//Saved itinerary//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH']
    count=0
    for e in p['items']:
        try:
            start=date.fromisoformat(e.get('startDate') or '')
            end=date.fromisoformat(e.get('endDate') or e['startDate'])+timedelta(days=1)
        except (ValueError,KeyError):
            continue
        if end<=start:end=start+timedelta(days=1)
        details='\n'.join(x for x in ['Opening window / event dates; choose and verify the exact local visit time.',e.get('when'),e.get('price'),e.get('summary'),*(s['url'] for s in e.get('sources',[]))] if x)
        lines+=['BEGIN:VEVENT','UID:'+text(pid+'-'+e['id']+'@sola.local'),'DTSTAMP:'+db.now().strftime('%Y%m%dT%H%M%SZ'),'DTSTART;VALUE=DATE:'+start.strftime('%Y%m%d'),'DTEND;VALUE=DATE:'+end.strftime('%Y%m%d'),'SUMMARY:'+text(e['title']),'LOCATION:'+text(e.get('where')),'DESCRIPTION:'+text(details),'STATUS:TENTATIVE','END:VEVENT']
        count+=1
    if not count:
        raise ApiError(422,'NO_EVENT_DATES','This plan has no verified event dates to export. Original local times remain in the printable itinerary.')
    lines+=['END:VCALENDAR']
    folded=[]
    for line in lines:
        part='';length=0
        for char in line:
            width=len(char.encode('utf-8'))
            if length+width>74:
                folded.append(part);part=' ';length=1
            part+=char;length+=width
        folded.append(part)
    return '\r\n'.join(folded)+'\r\n'
