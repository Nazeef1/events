from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from .models import EventCategory, EventStatus


class TicketTypeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    price: Decimal = Field(ge=0)
    quantity_total: int = Field(gt=0)
    sale_starts_at: datetime
    sale_ends_at: datetime

    @field_validator("sale_ends_at")
    @classmethod
    def _sale_window_valid(cls, v, info):
        start = info.data.get("sale_starts_at")
        if start and v <= start:
            raise ValueError("sale_ends_at must be after sale_starts_at")
        return v


class TicketTypeOut(BaseModel):
    id: str
    event_id: str
    name: str
    description: str
    price: Decimal
    quantity_total: int
    quantity_available: int
    sale_starts_at: datetime
    sale_ends_at: datetime

    model_config = {"from_attributes": True}


class EventCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    description: str = ""
    category: EventCategory = EventCategory.OTHER
    cover_image_url: str | None = None
    venue_name: str = ""
    venue_address: str = ""
    city: str = ""
    starts_at: datetime
    ends_at: datetime
    ticket_types: list[TicketTypeCreate] = Field(default_factory=list)

    @field_validator("ends_at")
    @classmethod
    def _window_valid(cls, v, info):
        start = info.data.get("starts_at")
        if start and v <= start:
            raise ValueError("ends_at must be after starts_at")
        return v


class EventUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    category: EventCategory | None = None
    cover_image_url: str | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    city: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class EventOut(BaseModel):
    id: str
    organizer_id: str
    title: str
    slug: str
    description: str
    category: EventCategory
    status: EventStatus
    cover_image_url: str | None
    venue_name: str
    venue_address: str
    city: str
    starts_at: datetime
    ends_at: datetime
    created_at: datetime
    ticket_types: list[TicketTypeOut]

    model_config = {"from_attributes": True}


class EventSummaryOut(BaseModel):
    id: str
    organizer_id: str
    title: str
    slug: str
    category: EventCategory
    status: EventStatus
    cover_image_url: str | None
    city: str
    starts_at: datetime
    min_price: Decimal | None
    max_price: Decimal | None

    model_config = {"from_attributes": True}


class PaginatedEvents(BaseModel):
    items: list[EventSummaryOut]
    total: int
    page: int
    page_size: int


class AdjustAvailabilityRequest(BaseModel):
    quantity: int
    idempotency_key: str
