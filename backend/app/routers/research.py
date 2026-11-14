"""Explore/products, generic research tasks + proposals, price watches, media."""
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from .. import db, search_scope
from datetime import date
from ..auth import CurrentUser
from ..errors import ApiError
from ..services import media, proposals, tasks, treats, watches, plans

router = APIRouter(prefix="/api/v1", tags=["research"])


class ExploreIn(BaseModel):
    query: Optional[str] = ""
    kind: str = "events"
    interests: Optional[List[str]] = None
    destination: str = Field('', max_length=100)
    destinationCountry: str = Field('', max_length=2)
    location: str = Field('', max_length=100)
    people: Optional[int] = Field(None, ge=1, le=1000)
    admission: str = Field('any', pattern='^(any|free|paid)$')
    context: str = Field('', max_length=600)
    dateFrom: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    dateTo: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class ProductsIn(BaseModel):
    query: Optional[str] = ""
    keys: Optional[List[str]] = None
    liked: List[str] = Field(default_factory=list)
    disliked: List[str] = Field(default_factory=list)
    round: int = 1
    image: Optional[Union[bool, str, List[str]]] = None
    imageFeatures: Optional[List[str]] = None


class TaskIn(BaseModel):
    intent: str
    request: str = Field("", max_length=500)
    constraints: Optional[Dict[str, Any]] = None


class ApproveIn(BaseModel):
    expectedVersion: Optional[int] = None
    payloadHash: Optional[str] = None


class WatchIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=160)
    category: Optional[str] = None
    mode: str = Field("explore", pattern="^(explore|exact)$")
    city: str = Field("", max_length=100)
    country: str = Field("", max_length=2)
    searchScope: str = Field("country", pattern="^(country|eu|multiple|worldwide)$")
    searchCountries: List[str] = Field(default_factory=list, max_length=10)
    details: str = Field("", max_length=400)
    targetMinor: Optional[int] = Field(None, gt=0, le=100000000)
    currency: Optional[str] = Field(None, min_length=3, max_length=3)
    sites: Optional[List[str]] = Field(None, max_length=10)
    cadenceHours: int = Field(24, ge=0, le=720)
    buyBy: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    notify: bool = True


class WatchPatch(BaseModel):
    expectedVersion: Optional[int] = None
    paused: Optional[bool] = None
    targetMinor: Optional[int] = Field(None, gt=0, le=100000000)
    query: Optional[str] = Field(None, min_length=1, max_length=160)
    sites: Optional[List[str]] = Field(None, max_length=10)
    cadenceHours: Optional[int] = Field(None, ge=0, le=720)


class RotationIn(BaseModel):
    imageUrls: List[str] = Field(..., description="Product photo URL(s) or data URLs; multiple photos = source gallery animation")
    title: Optional[str] = None
    format: str = Field("mp4", pattern="^(mp4|gif|webm)$")


class ItineraryIn(BaseModel):
    title: str
    subtitle: Optional[str] = None
    heroImageUrl: Optional[str] = None
    items: List[Dict[str, str]]


class TeaserIn(BaseModel):
    imageUrls: List[str]
    title: str
    caption: Optional[str] = None


@router.post("/explore")
def explore(body: ExploreIn, user=CurrentUser):
    location = (body.location or body.destination).strip()
    if not location:
        raise ApiError(422, 'LOCATION_REQUIRED', 'Choose a location for your suggestions.')
    for value in (body.dateFrom,body.dateTo):
        if value:
            try: date.fromisoformat(value)
            except ValueError: raise ApiError(400,'INVALID_INPUT','Enter valid calendar dates.')
    if body.destinationCountry:
        search_scope.validate(body.destinationCountry.upper())
    if body.dateFrom and body.dateTo and body.dateFrom > body.dateTo:
        raise ApiError(400,'INVALID_INPUT','End date must be after the start date.')
    return treats.explore(user, body.query, 'events', body.interests, destination=location,
                          destinationCountry=body.destinationCountry.upper(), dateFrom=body.dateFrom, dateTo=body.dateTo,
                          people=body.people, admission=body.admission, context=body.context)


@router.post("/products/search")
def products(body: ProductsIn, user=CurrentUser):
    return treats.find_products(user, body.query, body.keys, body.liked, body.disliked, body.round, body.image, body.imageFeatures)


# ------------------------------------------------------- tasks + proposals
@router.post("/tasks", status_code=202)
def create_task(body: TaskIn, user=CurrentUser):
    return tasks.create(user, body.intent, body.request, body.constraints)


@router.get("/tasks/{tid}")
def get_task(tid: str, user=CurrentUser):
    return tasks.get(user, tid)


@router.post("/tasks/{tid}/clarifications")
def clarify(tid: str, body: Dict[str, Any], user=CurrentUser):
    return tasks.clarify(user, tid, body)


@router.post("/tasks/{tid}/cancel")
def cancel(tid: str, user=CurrentUser):
    return tasks.cancel(user, tid)


@router.get("/tasks/{tid}/proposals")
def task_proposals(tid: str, user=CurrentUser):
    return tasks.list_proposals(user, tid)


@router.get("/tasks/{tid}/export", response_class=HTMLResponse)
def export(tid: str, user=CurrentUser):
    return HTMLResponse(tasks.export_html(user, tid))


@router.get("/proposals/{pid}")
def get_proposal(pid: str, user=CurrentUser):
    return proposals.get(user, pid)


@router.post("/proposals/{pid}/approve", status_code=202)
def approve(pid: str, body: ApproveIn, user=CurrentUser, idempotency_key: Optional[str] = Header(None)):
    """MVP action for non-shopping proposals: save the plan (no external write)."""
    p = proposals.get(user, pid)
    if p["kind"] == "shopping_plan":
        from ..services import organiser
        return organiser.place_order(user, pid, idempotency_key, body.expectedVersion, body.payloadHash)

    def save(prop):
        db.run("INSERT INTO bookings(id,user_id,kind,payload,status,created_at) VALUES(?,?,?,?,?,?)",
               (db.new_id("bk_"), user["id"], "saved_plan", db.dumps({"proposalId": prop["id"], "kind": prop["kind"]}), "saved", db.iso()))
        return {"saved": True, "externalWrite": False}
    return proposals.approve(user, pid, idempotency_key, "save_plan", save, body.expectedVersion, body.payloadHash)


@router.get("/actions/{aid}")
def action(aid: str, user=CurrentUser):
    return proposals.get_action(user, aid)


@router.get("/bookings")
def bookings(kind: Optional[str] = None, user=CurrentUser):
    rows = db.q("SELECT * FROM bookings WHERE user_id=? AND (? IS NULL OR kind=?) ORDER BY created_at DESC LIMIT 50", (user["id"], kind, kind))
    return {"items": [dict(db.loads(r["payload"], {}), id=r["id"], kind=r["kind"], status=r["status"], createdAt=r["created_at"]) for r in rows]}


# ------------------------------------------------------------ price watches
@router.get("/price-watches")
def list_watches(user=CurrentUser):
    return watches.list_watches(user)


@router.post("/price-watches", status_code=201)
def create_watch(body: WatchIn, user=CurrentUser):
    return watches.create(user, body.model_dump())


@router.patch("/price-watches/{wid}")
def patch_watch(wid: str, body: WatchPatch, user=CurrentUser):
    return watches.update(user, wid, body.model_dump(exclude_unset=True))


@router.delete("/price-watches/{wid}")
def delete_watch(wid: str, user=CurrentUser):
    watches.delete(user, wid)
    return {"ok": True}


@router.post("/price-watches/{wid}/checks")
def check_watch(wid: str, user=CurrentUser):
    return watches.check(user, wid)


@router.get("/price-watches/{wid}/history")
def watch_history(wid: str, user=CurrentUser):
    return watches.history(user, wid)


# -------------------------------------------------------------------- media
@router.get("/media")
def list_media(user=CurrentUser):
    return {"items": media.list_media(user), "configured": media.configured()}


@router.post("/media/rotation", status_code=201)
def rotation(body: RotationIn, user=CurrentUser):
    return media.rotation_video(user, body.imageUrls, body.title, body.format)


@router.post("/media/itinerary", status_code=201)
def itinerary(body: ItineraryIn, user=CurrentUser):
    return media.itinerary_image(user, body.title, body.items, body.subtitle, body.heroImageUrl)


@router.post("/media/event-teaser", status_code=201)
def teaser(body: TeaserIn, user=CurrentUser):
    return media.event_teaser(user, body.imageUrls, body.title, body.caption)


class SaveOptionsIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    count: int = Field(..., ge=1, le=10)


@router.post('/price-watches/{wid}/options')
def save_watch_options(wid: str, body: SaveOptionsIn, user=CurrentUser):
    return watches.save_options(user,wid,body.count,body.name)


@router.post('/price-watches/{wid}/options/{oid}/rotation', status_code=202)
def rotate_watch_option(wid: str,oid: str,user=CurrentUser):
    try:
        return watches.rotate_option(user,wid,oid)
    except ApiError:
        raise
    except Exception:
        raise ApiError(502,'MEDIA_PROVIDER_FAILED','Cloudinary could not generate the product preview. Existing saved options are retained.')


class EventChoiceIn(BaseModel):
    searchId: str
    resultId: str


class SavedTripIn(BaseModel):
    title: str = Field('My trip', max_length=120)
    choices: List[EventChoiceIn] = Field(..., min_length=1, max_length=8)


class PlanMediaIn(BaseModel):
    kind: str = Field(..., pattern='^(schedule|teasers)$')
    eventIds: List[str] = Field(default_factory=list, max_length=3)


@router.get('/research-searches')
def saved_searches(user=CurrentUser):
    return plans.searches(user)


@router.get('/itineraries')
def saved_trips(user=CurrentUser):
    return plans.list_plans(user)


@router.post('/itineraries',status_code=201)
def save_trip(body: SavedTripIn,user=CurrentUser):
    return plans.create(user,body.title,[c.model_dump() for c in body.choices])


@router.delete('/itineraries/{pid}')
def delete_trip(pid: str,user=CurrentUser):
    plans.delete(user,pid)
    return {'ok':True}


@router.post('/itineraries/{pid}/media',status_code=201)
def plan_media(pid: str,body: PlanMediaIn,user=CurrentUser):
    try:
        return plans.generate(user,pid,body.kind,body.eventIds)
    except ApiError:
        raise
    except Exception:
        raise ApiError(502,'MEDIA_PROVIDER_FAILED','Cloudinary could not generate this media. Check account permissions and retry; the saved plan is retained.')


@router.get('/itineraries/{pid}/print',response_class=HTMLResponse)
def print_itinerary(pid: str,user=CurrentUser):
    return HTMLResponse(plans.printable(user,pid))


@router.get('/itineraries/{pid}/calendar')
def export_itinerary_calendar(pid: str,user=CurrentUser):
    return Response(plans.calendar_file(user,pid),media_type='text/calendar',headers={'Content-Disposition':'attachment; filename="sola-itinerary.ics"'})


@router.post('/price-watch-research')
def research_price_watch(body: WatchIn,user=CurrentUser):
    return watches.research(user,body.model_dump())


class SaveResearchIn(BaseModel):
    name: str = Field(...,min_length=1,max_length=120)
    count: int = Field(...,ge=1,le=10)
    saveToken: str = Field(...,max_length=100000)
    cadenceHours: int = Field(0,ge=0,le=720)


@router.post('/price-watch-lists',status_code=201)
def save_researched_list(body: SaveResearchIn,user=CurrentUser):
    return watches.save_research(user,body.name,body.count,body.saveToken,body.cadenceHours)


@router.get('/media/{mid}/playback')
def play_media(mid: str,user=CurrentUser,range_header: Optional[str]=Header(None,alias='Range')):
    return media.playback(user,mid,range_header)


class VisualPreviewIn(BaseModel):
    kind: str = Field(..., pattern='^(space|turn)$')
    previewMode: str = Field('room', pattern='^(clothing|room|other)$')
    instructions: str = Field('', max_length=500)
    optionId: str = Field(..., max_length=100)
    watchId: Optional[str] = Field(None, max_length=100)
    saveToken: Optional[str] = Field(None, max_length=100000)
    imageData: Optional[str] = Field(None, max_length=5600000)


@router.post('/visual-previews', status_code=202)
def create_visual_preview(body: VisualPreviewIn, user=CurrentUser):
    from ..services import visual_previews
    return visual_previews.start(user, body.model_dump())


@router.get('/visual-previews/{sid}')
def visual_preview_status(sid: str, user=CurrentUser):
    from ..services import visual_previews
    return visual_previews.state(user, sid)


@router.delete('/visual-previews/{sid}')
def close_visual_preview(sid: str, user=CurrentUser):
    from ..services import visual_previews
    return visual_previews.close(user, sid)


@router.get('/visual-previews/{sid}/content')
def visual_preview_content(sid: str, download: bool=False, user=CurrentUser,
                           range_header: Optional[str]=Header(None, alias='Range')):
    from ..services import visual_previews
    return visual_previews.content(user, sid, range_header, download)


@router.get('/product-images/{key}')
def product_cutout(key: str, user=CurrentUser):
    from ..services import product_media
    from fastapi.responses import RedirectResponse
    return RedirectResponse(product_media.cleaned(key)['url'], status_code=307,
                            headers={'Cache-Control': 'private, max-age=3600'})
