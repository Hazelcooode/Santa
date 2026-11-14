"""Explore/products, generic research tasks + proposals, price watches, media."""
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .. import db
from ..auth import CurrentUser
from ..errors import ApiError
from ..services import media, proposals, tasks, treats, watches

router = APIRouter(prefix="/api/v1", tags=["research"])


class ExploreIn(BaseModel):
    query: Optional[str] = ""
    kind: str = "events"
    interests: Optional[List[str]] = None


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
    query: str
    category: Optional[str] = None
    targetMinor: Optional[int] = Field(None, ge=0)
    currency: Optional[str] = None
    sites: Optional[List[str]] = None
    cadenceHours: Optional[int] = 24
    buyBy: Optional[str] = None
    notify: bool = True


class WatchPatch(BaseModel):
    expectedVersion: Optional[int] = None
    paused: Optional[bool] = None
    targetMinor: Optional[int] = None
    query: Optional[str] = None
    sites: Optional[List[str]] = None
    cadenceHours: Optional[int] = None


class RotationIn(BaseModel):
    imageUrls: List[str] = Field(..., description="Product photo URL(s) or data URLs; 4+ angles = real turntable")
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
    return treats.explore(user, body.query, body.kind, body.interests)


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
