"""Pydantic request / response schemas for items."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ItemCreate(BaseModel):
    """Payload for creating a new item."""

    name: str = Field(..., min_length=1, max_length=255, examples=["Widget X"])
    description: str | None = Field(None, max_length=2000, examples=["A high-quality widget"])


class ItemResponse(BaseModel):
    """Serialised item returned by the API."""

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ItemListResponse(BaseModel):
    """Paginated list wrapper."""

    items: list[ItemResponse]
    count: int
