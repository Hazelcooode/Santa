"""Life organiser, laundry, calendar, home/today and the state snapshot."""
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from fastapi import APIRouter, Header, BackgroundTasks
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import CurrentUser
from ..errors import ApiError
from ..services import calendar, home, laundry, organiser, shopping_prices

router = APIRouter(prefix="/api/v1", tags=["organiser"])


class ItemIn(BaseModel):
    name: str = Field(..., max_length=80)
    qty: float = Field(1, gt=0, le=10000, allow_inf_nan=False)
    prio: int = Field(2, ge=1, le=3)
    note: Optional[str] = Field(None, max_length=200)
    brand: Optional[str] = Field(None, max_length=100)
    details: Optional[str] = Field(None, max_length=400)
    attributes: Dict[str, str] = Field(default_factory=dict, max_length=20)


class ItemPatch(BaseModel):
    name: Optional[str] = None
    qty: Optional[float] = Field(None, gt=0, le=10000, allow_inf_nan=False)
    prio: Optional[int] = Field(None, ge=1, le=3)
    note: Optional[str] = Field(None, max_length=200)
    brand: Optional[str] = Field(None, max_length=100)
    details: Optional[str] = Field(None, max_length=400)
    attributes: Optional[Dict[str, str]] = Field(None, max_length=20)
    bought: Optional[Union[bool, str]] = None
    expectedVersion: Optional[int] = None


class ObservationIn(BaseModel):
    detections: List[Dict[str, Any]] = Field(..., description="Derived on-device detections, e.g. {label:'oat_milk', level:0}")
    frameId: Optional[str] = None


# --- basket camera summaries (formatted by the on-device model) ------------
GarmentLabel = Literal["dark_tshirt", "white_tshirt", "colour_tshirt", "jeans", "socks", "underwear", "towel", "gym_wear",
                       "knitwear", "joggers", "unknown_item"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GarmentIn(Strict):
    label: GarmentLabel
    colour: Literal["white", "dark", "colour"]
    confidence: float = Field(..., ge=0, le=1)
    bbox: List[float] = Field(..., min_length=4, max_length=4, description="x, y, w, h as fractions of the frame")


class DetectionCount(Strict):
    label: GarmentLabel
    n: int = Field(..., ge=0, le=60)


class EdgeModelIn(Strict):
    id: str = Field(..., pattern=r"^[a-z0-9-]{3,40}$")
    version: str = Field(..., pattern=r"^[0-9a-z.\-]{1,16}$")
    runtime: str = Field(..., max_length=40)
    params: int = Field(..., ge=1, le=2_000_000_000)


class FrameSummaryIn(Strict):
    """What the camera hub may send: derived data only. There is no field that can carry pixels."""
    frameId: str = Field(..., pattern=r"^[a-z0-9-]{4,48}$")
    capturedAt: datetime
    trigger: Literal["history", "new_item", "periodic"]
    model: EdgeModelIn
    imageSha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    imageWidth: int = Field(..., ge=16, le=4096)
    imageHeight: int = Field(..., ge=16, le=4096)
    processingMs: float = Field(..., ge=0, le=600_000)
    items: List[GarmentIn] = Field(..., max_length=60)
    detections: Optional[List[DetectionCount]] = Field(None, max_length=20, description="Counts per label (recomputed by the server)")


class ObservationBatchIn(Strict):
    reset: bool = False
    observations: List[FrameSummaryIn] = Field(..., min_length=1, max_length=30)


class FrameImageIn(Strict):
    image: str = Field(..., max_length=900_000, description="data:image/jpeg;base64,... — only with consent")


class DealsIn(BaseModel):
    cachedOnly: bool = True
    strategy: str = "multi"
    items: Optional[List[Dict[str, Any]]] = None


class OrderIn(BaseModel):
    proposalId: str
    expectedVersion: Optional[int] = None
    payloadHash: Optional[str] = None


class TripIn(BaseModel):
    day: Union[str, int] = "today"
    start: float = Field(..., ge=0, le=24)


class BookIn(BaseModel):
    key: Optional[str] = None
    day: Optional[int] = None
    slot: Optional[int] = None


class WardrobeIn(BaseModel):
    wardrobe: List[Dict[str, Any]]


class EventIn(BaseModel):
    title: str
    start: str
    end: str


class DeviceIn(BaseModel):
    on: bool


# --- home ---------------------------------------------------------------
@router.get("/dashboard")
def dashboard(user=CurrentUser):
    return home.dashboard(user)


@router.get("/state")
def state(user=CurrentUser):
    """Whole account in the mobile app's local-state shape (for hydration)."""
    return home.state(user)


@router.get("/today")
def today(user=CurrentUser):
    return home.today(user)


@router.post("/today/{deco}")
def today_done(deco: str, user=CurrentUser):
    return home.mark_done(user, deco)


# --- shopping list -------------------------------------------------------
@router.get("/shopping/items")
def items(user=CurrentUser):
    lst = organiser.list_items(user)
    return {"items": lst, "open": len([i for i in lst if not i["bought"]]), "nextCursor": None}


@router.post("/shopping/items", status_code=201)
def add_item(body: ItemIn, background: BackgroundTasks, user=CurrentUser):
    item = organiser.add_item(user, body.name, body.qty, body.prio, "you", body.note, brand=body.brand, details=body.details, attributes=body.attributes)
    pass  # Prices are refreshed only by an explicit user action.
    return item


@router.patch("/shopping/items/{item_id}")
def patch_item(item_id: str, body: ItemPatch, background: BackgroundTasks, user=CurrentUser):
    changes = body.model_dump(exclude_unset=True, exclude={"expectedVersion"})
    item = organiser.update_item(user, item_id, changes, body.expectedVersion)
    if set(changes) & {"name", "brand", "details", "attributes"}:
        pass  # Prices are refreshed only by an explicit user action.
    return item


@router.delete("/shopping/items/{item_id}")
def del_item(item_id: str, user=CurrentUser):
    organiser.delete_item(user, item_id)
    return {"ok": True}


@router.post("/shopping/deals")
def deals(body: DealsIn, user=CurrentUser):
    """Live prices for the server-side list (or given items) with a strategy: multi|single|mall|nearest."""
    return organiser.find_deals(user, body.strategy, body.items, cached_only=body.cachedOnly)


@router.post("/shopping/orders", status_code=202)
def order(body: OrderIn, user=CurrentUser, idempotency_key: Optional[str] = Header(None)):
    """Approve a shopping plan proposal -> simulated online order(s), one per store."""
    return organiser.place_order(user, body.proposalId, idempotency_key, body.expectedVersion, body.payloadHash)


@router.get("/shopping/proposals/{proposal_id}/print", response_class=HTMLResponse)
def print_list(proposal_id: str, user=CurrentUser):
    return HTMLResponse(organiser.printable(user, proposal_id))


@router.get("/shopping/stores")
def stores(user=CurrentUser):
    from ..agents.planner import user_stores
    return {"items": user_stores(user)}


@router.put("/shopping/stores")
def set_stores(body: List[Dict[str, Any]], user=CurrentUser):
    from .. import db
    clean = []
    for s in body[:20]:
        if not s.get("name"):
            raise ApiError(400, "INVALID_INPUT", "Each store needs a name.")
        clean.append({"id": str(s.get("id") or s["name"]).lower().replace(" ", "-")[:40], "name": str(s["name"])[:60], "mall": s.get("mall"),
                      "dist": s.get("dist"), "url": s.get("url"), "domain": s.get("domain")})
    db.set_state(user["id"], "stores", clean)
    return {"items": clean}


# --- cameras / inventory --------------------------------------------------
@router.get("/devices")
def devices(user=CurrentUser):
    return {"items": organiser.devices(user)}


@router.patch("/devices/{key}")
def device(key: str, body: DeviceIn, user=CurrentUser):
    return {"items": organiser.set_device(user, key, body.on)}


@router.get("/inventory/regulars")
def regulars(user=CurrentUser):
    return {"items": organiser.regulars(user)}


@router.get("/devices/{key}/frames")
def frames(key: str, user=CurrentUser):
    """The mocked camera frames used for the demo (stand-in for on-device video)."""
    return {"items": organiser.frames(key)}


@router.post("/devices/{key}/scan")
def scan(key: str, background: BackgroundTasks, frame: Optional[int] = None, user=CurrentUser):
    """Replay the next mocked frame: fridge/storage -> shopping list, basket -> laundry, door -> door events."""
    if key == "basket":
        return laundry.scan(user, frame)
    if key == "door":
        from ..services import safety
        return safety.simulate_door(user)
    result = organiser.scan(user, key, frame)
    for item in result.get("added", []):
        pass  # Prices are refreshed only by an explicit user action.
    return result


@router.post("/devices/{key}/observations")
def observe(key: str, body: ObservationIn, background: BackgroundTasks, user=CurrentUser):
    """Real devices: post derived detections only (video never leaves the device)."""
    if key == "basket":
        return laundry.ingest(user, body.detections)
    result = organiser.ingest_observation(user, key, body.detections, body.frameId)
    for item in result.get("added", []):
        pass  # Prices are refreshed only by an explicit user action.
    return result


# --- grocery run ----------------------------------------------------------
@router.get("/shopping/trip")
def trip(user=CurrentUser):
    return organiser.grocery_trip(user)


@router.put("/shopping/trip")
def set_trip(body: TripIn, user=CurrentUser):
    return organiser.set_trip(user, body.day, body.start)


@router.post("/shopping/trip/book")
def book_trip(user=CurrentUser):
    return organiser.book_trip(user)


# --- laundry --------------------------------------------------------------
@router.get("/laundry")
def laundry_state(user=CurrentUser):
    return laundry.state(user)


@router.post("/laundry/observations")
def laundry_observations(body: ObservationBatchIn, user=CurrentUser):
    """Summaries from the basket camera's on-device model. Images are never accepted here."""
    obs = []
    for o in body.observations:
        d = o.model_dump()
        at = d["capturedAt"]
        d["capturedAt"] = at if at.tzinfo else at.replace(tzinfo=timezone.utc)
        d["detections"] = [{"label": k, "n": v} for k, v in sorted(laundry.Counter(i["label"] for i in d["items"]).items())]
        obs.append(d)
    return laundry.ingest_observations(user, obs, reset=body.reset)


@router.post("/laundry/frames/{frame_id}/image")
def laundry_frame_upload(frame_id: str, body: FrameImageIn, user=CurrentUser):
    """Only with the camera_images_off_device consent; the bytes must match the frame's fingerprint."""
    return laundry.upload_image(user, frame_id, body.image)


@router.get("/laundry/frames/{frame_id}/image")
def laundry_frame_image(frame_id: str, user=CurrentUser):
    mime, data = laundry.get_image(user, frame_id)
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})


@router.post("/laundry/bookings", status_code=201)
def laundry_book(body: BookIn, user=CurrentUser):
    return dict(laundry.book(user, body.key, body.day, body.slot), simulated=True, notice="App reservation only; no laundry-machine provider is connected.")


@router.delete("/laundry/bookings/{ident}")
def laundry_cancel(ident: str, user=CurrentUser):
    return laundry.cancel(user, ident)


@router.put("/laundry/wardrobe")
def wardrobe(body: WardrobeIn, user=CurrentUser):
    return laundry.update_wardrobe(user, body.wardrobe)


# --- calendar -------------------------------------------------------------
@router.get("/calendar/events")
def cal_events(days: int = 3, user=CurrentUser):
    s = calendar.at_local(user, 0, 0)
    e = calendar.at_local(user, max(1, min(days, 14)), 0)
    return {"items": [calendar.public_event(user, ev) for ev in calendar.events_between(user, s, e)]}


@router.post("/calendar/events", status_code=201)
def cal_add(body: EventIn, user=CurrentUser):
    from .. import db
    s, e = db.parse_iso(body.start), db.parse_iso(body.end)
    if e <= s:
        raise ApiError(400, "INVALID_INPUT", "End must be after start.")
    return {"id": calendar.add_event(user, body.title, s, e, source="user")}


@router.delete("/calendar/events/{event_id}")
def cal_del(event_id: str, user=CurrentUser):
    calendar.delete_event(user, event_id)
    return {"ok": True}


@router.get("/calendar/free-slots")
def cal_free(duration: int = 45, days: int = 2, earliest: float = 8, latest: float = 21, user=CurrentUser):
    return {"items": calendar.free_slots(user, max(15, min(duration, 480)), max(1, min(days, 7)), earliest, latest)}


class ShoppingSettingsIn(BaseModel):
    city: str = Field(..., min_length=1, max_length=100)
    country: str = Field(..., min_length=2, max_length=2)
    currency: str = Field("EUR", min_length=3, max_length=3)
    domains: List[str] = Field(default_factory=list, max_length=10)
    shopMode: str = Field("selected", pattern="^(selected|nearby)$")
    searchScope: str = Field("country", pattern="^(country|eu|multiple|worldwide)$")
    searchCountries: List[str] = Field(default_factory=list, max_length=10)


class RefreshPricesIn(BaseModel):
    force: bool = True
    itemIds: Optional[List[str]] = Field(None, max_length=100)
    strategy: str = "multi"


@router.get("/shopping/settings")
def shopping_settings(user=CurrentUser):
    return shopping_prices.get_settings(user)


@router.put("/shopping/settings")
def put_shopping_settings(body: ShoppingSettingsIn, user=CurrentUser):
    return shopping_prices.set_settings(user, body.model_dump())


@router.post("/shopping/prices/refresh")
def refresh_prices(body: RefreshPricesIn, user=CurrentUser):
    return shopping_prices.refresh(user, body.force, body.itemIds, body.strategy)


@router.get("/shopping/prices/status")
def refresh_status(user=CurrentUser):
    return {"latest": shopping_prices.status(user)}
