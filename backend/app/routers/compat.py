"""Endpoints the mobile app already calls when USE_BACKEND is on (mobile/data.js).
Request and response shapes match FigmentAPI exactly; extra fields (mode,
notice, proposalId, ...) are additive and ignored by the current UI."""
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from ..auth import CurrentUser
from ..services import companion, health, organiser, treats

router = APIRouter(prefix="/api", tags=["mobile-compatible"])


class Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class DealsIn(Loose):
    items: Optional[List[Dict[str, Any]]] = None
    strategy: str = "multi"


class ExploreIn(Loose):
    query: Optional[str] = ""
    kind: str = "events"
    interests: Optional[List[str]] = None


class ProductsIn(Loose):
    query: Optional[str] = ""
    image: Optional[Union[bool, str, List[str]]] = None
    imageFeatures: Optional[List[str]] = None
    keys: Optional[List[str]] = None
    liked: List[str] = Field(default_factory=list)
    disliked: List[str] = Field(default_factory=list)
    round: int = 1


class MedicineIn(Loose):
    symptom: str


class WellbeingIn(Loose):
    mood: str = "tired"


class ChatIn(Loose):
    text: str
    memoryConsent: Optional[bool] = None
    memories: Optional[List[str]] = None


@router.post("/deals")
def deals(body: DealsIn, user=CurrentUser):
    """{ items, strategy } -> { total, saved, note, plan[], sources[] }"""
    return organiser.find_deals(user, body.strategy, body.items)


@router.post("/explore")
def explore(body: ExploreIn, user=CurrentUser):
    """{ query, kind: events|travel, interests[] } -> { results[] }"""
    return treats.explore(user, body.query, body.kind, body.interests)


@router.post("/products")
def products(body: ProductsIn, user=CurrentUser):
    """{ query, image?, keys[], liked[], disliked[], round } -> { keys[], results[], strategy }"""
    return treats.find_products(user, body.query, body.keys, body.liked, body.disliked, body.round, body.image, body.imageFeatures)


@router.post("/medicine")
def medicine(body: MedicineIn, user=CurrentUser):
    """{ symptom } -> { results[] }"""
    return health.find_medicine(user, body.symptom)


@router.post("/wellbeing")
def wellbeing(body: WellbeingIn, user=CurrentUser):
    """{ mood } -> { meals[], activities[], sources[] }"""
    return health.wellbeing(user, body.mood)


@router.post("/chat")
def chat(body: ChatIn, user=CurrentUser):
    """{ text, memoryConsent, memories[] } -> { replies[], memory? }"""
    return companion.chat(user, body.text, {"memoryConsent": body.memoryConsent, "memories": body.memories})
