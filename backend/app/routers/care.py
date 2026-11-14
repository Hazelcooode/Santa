"""Companionship, health and safety."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from .. import db
from ..auth import CurrentUser
from ..errors import ApiError
from ..services import companion, health, messaging, safety

router = APIRouter(prefix="/api/v1", tags=["companion", "health", "safety"])


class ChatIn(BaseModel):
    text: str = Field(..., max_length=1000)
    memoryConsent: Optional[bool] = None


class MemoryIn(BaseModel):
    text: str = Field(..., max_length=200)
    tag: str = "chat"


class SocialIn(BaseModel):
    linked: bool
    handle: Optional[str] = None


class CallIn(BaseModel):
    kind: str = "voice"


class Verification(BaseModel):
    method: str = Field(..., description="fingerprint | face | password")
    challenge: Optional[str] = None
    password: Optional[str] = None


class CheckinIn(BaseModel):
    verification: Verification


class CheckinConfigIn(BaseModel):
    every: Optional[int] = None
    grace: Optional[int] = None
    nextHour: Optional[int] = None


class LocationIn(BaseModel):
    lat: float
    lng: float
    accuracy: Optional[float] = None
    label: Optional[str] = None
    at: Optional[str] = None


class SosIn(BaseModel):
    verification: Verification
    type: Optional[str] = None
    police: bool = False
    location: Optional[Dict[str, float]] = None


class ResolveIn(BaseModel):
    verification: Verification


class DoorReviewIn(BaseModel):
    action: str


class DoorEventIn(BaseModel):
    detections: List[Dict[str, Any]]


class DoorSettingsIn(BaseModel):
    loiterSeconds: Optional[int] = Field(None, ge=15, le=900)
    alerts: Optional[bool] = None


class ContactIn(BaseModel):
    name: str = Field(..., max_length=60)
    via: str = Field("invite pending", max_length=80)


class ContactPatch(BaseModel):
    on: Optional[bool] = None
    name: Optional[str] = None
    via: Optional[str] = None


class ReachOutIn(BaseModel):
    contactId: Optional[str] = None
    confirmed: bool = False


class VitalsIn(BaseModel):
    samples: List[Dict[str, Any]]


class MoodIn(BaseModel):
    mood: str


class MedicineIn(BaseModel):
    symptom: str


class MedOrderIn(BaseModel):
    proposalId: str
    index: int


class ApptIn(BaseModel):
    suggestionId: str


class RideIn(BaseModel):
    destination: str


# ---------------------------------------------------------------- companion
@router.post("/chat")
def chat(body: ChatIn, user=CurrentUser):
    return companion.chat(user, body.text, {"memoryConsent": body.memoryConsent})


@router.get("/chat/history")
def chat_history(user=CurrentUser):
    return {"items": companion.history(user)}


@router.post("/chat/reach-out")
def reach_out(body: ReachOutIn, user=CurrentUser):
    """Only after the user explicitly said yes in the care prompt."""
    if not body.confirmed:
        raise ApiError(400, "CONFIRMATION_REQUIRED", "I'll only reach out if you say yes.")
    contacts = messaging.contacts(user)
    c = next((x for x in contacts if x["id"] == body.contactId), contacts[0] if contacts else None)
    if not c:
        raise ApiError(422, "NO_CONTACTS", "Add someone you trust under Me first.")
    msg = "Hi %s, it's Sola, %s's assistant. %s asked me to let you know they could use some company today. Maybe give them a call? 💛" % (
        c["name"], user["display_name"], user["display_name"])
    return {"sent": messaging.send(user, [c], msg, "reach_out", None), "message": msg}


@router.get("/memories")
def memories(user=CurrentUser):
    return {"items": companion.memories(user), "consent": companion.has_consent(user, "memory")}


@router.post("/memories", status_code=201)
def add_memory(body: MemoryIn, user=CurrentUser):
    return companion.add_memory(user, body.text, body.tag, "user")


@router.delete("/memories/{mid}")
def del_memory(mid: str, user=CurrentUser):
    companion.delete_memory(user, mid)
    return {"ok": True}


@router.get("/companion/posts")
def posts(user=CurrentUser):
    return {"items": companion.posts(user)}


@router.post("/companion/posts/refresh")
def refresh_posts(force: bool = False, user=CurrentUser):
    """Background interest research (also run by the scheduler, max every 12 h)."""
    return companion.refresh_posts(user, force)


@router.get("/social")
def social(user=CurrentUser):
    return {"items": companion.social(user)}


@router.patch("/social/{sid}")
def set_social(sid: str, body: SocialIn, user=CurrentUser):
    return {"items": companion.set_social(user, sid, body.linked, body.handle)}


@router.post("/calls")
def call(body: CallIn, user=CurrentUser):
    return companion.start_call(user, body.kind)


# ------------------------------------------------------------------- health
@router.get("/health/summary")
def health_summary(user=CurrentUser):
    return health.summary(user)


@router.post("/health/vitals")
def vitals(body: VitalsIn, user=CurrentUser):
    if not companion.has_consent(user, "health_device"):
        raise ApiError(403, "CONSENT_REQUIRED", "Connect your health device first (consent: health_device).")
    return health.ingest_vitals(user, body.samples)


@router.post("/health/wellbeing")
def wellbeing(body: MoodIn, user=CurrentUser):
    return health.wellbeing(user, body.mood)


@router.post("/health/medicine")
def medicine(body: MedicineIn, user=CurrentUser):
    return health.find_medicine(user, body.symptom)


@router.post("/health/medicine/orders", status_code=202)
def med_order(body: MedOrderIn, user=CurrentUser, idempotency_key: Optional[str] = Header(None)):
    return health.order_medicine(user, body.proposalId, body.index, idempotency_key)


@router.get("/health/appointments/suggestions")
def appt_suggestions(user=CurrentUser):
    return health.appointment_suggestions(user)


@router.post("/health/appointments", status_code=201)
def appt_book(body: ApptIn, user=CurrentUser):
    return health.book_appointment(user, body.suggestionId)


@router.get("/health/rides/options")
def ride_options(user=CurrentUser):
    return health.ride_options(user)


@router.post("/health/rides", status_code=201)
def ride(body: RideIn, user=CurrentUser):
    return health.book_ride(user, body.destination)


# ------------------------------------------------------------------- safety
@router.get("/safety/checkin")
def checkin_status(user=CurrentUser):
    return safety.status(user)


@router.post("/safety/checkin")
def checkin(body: CheckinIn, user=CurrentUser):
    return safety.checkin(user, body.verification.model_dump())


@router.patch("/safety/checkin")
def checkin_config(body: CheckinConfigIn, user=CurrentUser):
    return safety.set_config(user, body.every, body.grace, body.nextHour)


@router.get("/safety/checkin/missed-preview")
def missed_preview(user=CurrentUser):
    return safety.preview_missed(user)


@router.post("/safety/checkin/evaluate")
def evaluate(user=CurrentUser):
    """Runs the missed-check-in rule now (the scheduler does this every minute)."""
    return {"escalation": safety.evaluate(user), "status": safety.status(user)}


@router.post("/safety/locations", status_code=201)
def location(body: LocationIn, user=CurrentUser):
    return safety.record_location(user, body.lat, body.lng, body.accuracy, body.label, body.at)


@router.get("/safety/locations")
def locations(user=CurrentUser):
    return {"items": safety.trail(user)}


@router.post("/safety/sos", status_code=201)
def sos(body: SosIn, user=CurrentUser):
    return safety.sos(user, body.verification.model_dump(), body.type, body.location, body.police)


@router.get("/safety/sos/active")
def sos_active(user=CurrentUser):
    return {"sos": safety.active_sos(user), "types": safety.SOS_TYPES}


@router.post("/safety/sos/{sos_id}/resolve")
def sos_resolve(sos_id: str, body: ResolveIn, user=CurrentUser):
    return safety.resolve_sos(user, sos_id, body.verification.model_dump())


@router.get("/safety/door/events")
def door_events(user=CurrentUser):
    return {"items": safety.door_events(user), "settings": safety.door_settings(user)}


@router.post("/safety/door/events", status_code=201)
def door_ingest(body: DoorEventIn, user=CurrentUser):
    """On-device detector posts derived events: {person: unknown|known|courier|none, dwell_s, knocked}."""
    return {"items": safety.ingest_door_frame(user, {"detections": body.detections})}


@router.post("/safety/door/events/{event_id}/review")
def door_review(event_id: str, body: DoorReviewIn, user=CurrentUser):
    return safety.review_door(user, event_id, body.action)


@router.patch("/safety/door/settings")
def door_settings(body: DoorSettingsIn, user=CurrentUser):
    s = safety.door_settings(user)
    s.update({k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None})
    db.set_state(user["id"], "door_settings", s)
    return s


@router.get("/contacts")
def contacts(user=CurrentUser):
    return {"items": [{"id": c["id"], "name": c["name"], "via": c["via"], "on": bool(c["enabled"]), "police": bool(c["police"])}
                      for c in db.q("SELECT * FROM contacts WHERE user_id=? ORDER BY sort, name", (user["id"],))]}


@router.post("/contacts", status_code=201)
def add_contact(body: ContactIn, user=CurrentUser):
    cid = db.new_id("c_")
    db.run("INSERT INTO contacts(id,user_id,name,via,enabled,police,sort) VALUES(?,?,?,?,?,?,?)",
           (cid, user["id"], body.name.strip(), body.via.strip(), 1, 0, 100))
    messaging.send(user, [{"name": body.name, "via": body.via}], "%s added you as a trusted contact on Sola. Reply YES to confirm." % user["display_name"],
                   "contact_invite", cid)
    return {"id": cid, "name": body.name, "via": body.via, "on": True, "invite": "sent (simulated)"}


@router.patch("/contacts/{cid}")
def patch_contact(cid: str, body: ContactPatch, user=CurrentUser):
    row = db.q1("SELECT * FROM contacts WHERE id=? AND user_id=?", (cid, user["id"]))
    if not row:
        raise ApiError(404, "NOT_FOUND", "Contact not found.")
    d = body.model_dump(exclude_unset=True)
    db.run("UPDATE contacts SET enabled=?, name=?, via=? WHERE id=?",
           (int(d.get("on", bool(row["enabled"]))), d.get("name") or row["name"], d.get("via") or row["via"], cid))
    return {"ok": True}


@router.delete("/contacts/{cid}")
def del_contact(cid: str, user=CurrentUser):
    row = db.q1("SELECT * FROM contacts WHERE id=? AND user_id=?", (cid, user["id"]))
    if row and row["police"]:
        raise ApiError(400, "INVALID_INPUT", "Emergency services can be switched off, not removed.")
    db.run("DELETE FROM contacts WHERE id=? AND user_id=?", (cid, user["id"]))
    return {"ok": True}


@router.get("/outbox")
def outbox(user=CurrentUser):
    """Every message Sola sent (or would send) on your behalf."""
    return {"items": messaging.outbox(user)}
