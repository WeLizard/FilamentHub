"""Pydantic contracts for the CRM-lite workspace."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.crm import CrmOrderStatus, CrmQuoteEventType, CrmQuoteStatus


class CrmCustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    contact_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=64)
    inn: str | None = Field(None, max_length=32)
    address: str | None = Field(None, max_length=1000)
    note: str | None = Field(None, max_length=5000)


class CrmCustomerUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    contact_name: str | None = Field(None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(None, max_length=64)
    inn: str | None = Field(None, max_length=32)
    address: str | None = Field(None, max_length=1000)
    note: str | None = Field(None, max_length=5000)
    archived: bool | None = None


class CrmCustomerResponse(BaseModel):
    id: int
    name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    inn: str | None
    address: str | None
    note: str | None
    archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrmCustomerListResponse(BaseModel):
    items: list[CrmCustomerResponse]
    total: int


class CrmQuoteLineCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    details: list[str] = Field(default_factory=list, max_length=32)
    quantity: float = Field(..., gt=0, le=1_000_000)
    unit: str = Field("pcs", min_length=1, max_length=32)
    unit_price: float = Field(..., ge=0, le=1_000_000_000)
    source_data: dict[str, Any] | None = None


class CrmQuoteLineResponse(BaseModel):
    id: int
    position: int
    title: str
    details: list[str]
    quantity: float
    unit: str
    unit_price: float
    total_price: float
    source_data: dict[str, Any] | None


class CrmQuoteVersionPayload(BaseModel):
    source_history_id: int | None = Field(None, ge=1)
    seller_snapshot: dict[str, Any] = Field(default_factory=dict)
    customer_snapshot: dict[str, Any] = Field(default_factory=dict)
    calculation_snapshot: dict[str, Any] | None = None
    payment_terms: str | None = Field(None, max_length=1000)
    disclaimer_mode: str = Field("not_offer", pattern=r"^(offer|not_offer)$")
    tax_total: float = Field(0, ge=0, le=1_000_000_000)
    html_content: str | None = Field(None, max_length=500_000)
    lines: list[CrmQuoteLineCreate] = Field(..., min_length=1, max_length=500)


class CrmQuoteCreate(CrmQuoteVersionPayload):
    customer_id: int | None = Field(None, ge=1)
    new_customer: CrmCustomerCreate | None = None
    number: str | None = Field(None, min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=255)
    currency: str = Field("RUB", pattern=r"^[A-Z]{3}$")
    valid_until: date | None = None

    @model_validator(mode="after")
    def validate_customer_source(self) -> "CrmQuoteCreate":
        if self.customer_id is not None and self.new_customer is not None:
            raise ValueError("customer_id and new_customer are mutually exclusive")
        return self


class CrmQuoteVersionCreate(CrmQuoteVersionPayload):
    pass


class CrmQuoteVersionResponse(BaseModel):
    id: int
    version_number: int
    source_history_id: int | None
    shared_quote_id: int | None
    seller_snapshot: dict[str, Any]
    customer_snapshot: dict[str, Any]
    calculation_snapshot: dict[str, Any] | None
    payment_terms: str | None
    disclaimer_mode: str
    subtotal: float
    tax_total: float
    grand_total: float
    html_content: str | None
    lines: list[CrmQuoteLineResponse]
    created_at: datetime


class CrmQuoteEventResponse(BaseModel):
    id: int
    event_type: CrmQuoteEventType
    from_status: str | None
    to_status: str | None
    details: dict[str, Any] | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CrmOrderResponse(BaseModel):
    id: int
    quote_id: int
    customer_id: int | None
    number: str
    title: str
    status: CrmOrderStatus
    currency: str
    total: float
    due_date: date | None
    note: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer: CrmCustomerResponse | None = None


class CrmQuoteResponse(BaseModel):
    id: int
    customer_id: int | None
    number: str
    title: str
    status: CrmQuoteStatus
    currency: str
    valid_until: date | None
    sent_at: datetime | None
    accepted_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime
    updated_at: datetime
    customer: CrmCustomerResponse | None
    current_version: CrmQuoteVersionResponse
    order: CrmOrderResponse | None


class CrmQuoteDetailResponse(CrmQuoteResponse):
    versions: list[CrmQuoteVersionResponse]
    events: list[CrmQuoteEventResponse]


class CrmQuoteListResponse(BaseModel):
    items: list[CrmQuoteResponse]
    total: int


class CrmQuoteUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    customer_id: int | None = Field(None, ge=1)
    valid_until: date | None = None


class CrmQuoteStatusUpdate(BaseModel):
    status: CrmQuoteStatus


class CrmOrderUpdate(BaseModel):
    status: CrmOrderStatus | None = None
    due_date: date | None = None
    note: str | None = Field(None, max_length=5000)


class CrmOrderListResponse(BaseModel):
    items: list[CrmOrderResponse]
    total: int


class CrmWorkspaceSummary(BaseModel):
    customers_total: int
    quotes_draft: int
    quotes_sent: int
    quotes_accepted: int
    orders_active: int
    orders_completed: int
    amount_awaiting_decision: dict[str, float]
    accepted_amount: dict[str, float]


class CrmShareQuoteResponse(BaseModel):
    uuid: str
    share_url: str
    expires_at: datetime | None
