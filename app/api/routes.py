"""Item CRUD REST endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.schemas import ItemCreate, ItemListResponse, ItemResponse
from app.db import repository

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(payload: ItemCreate):
    """Create a new item."""
    item = await repository.create_item(name=payload.name, description=payload.description)
    return item


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: uuid.UUID):
    """Retrieve a single item by ID."""
    item = await repository.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.get("/", response_model=ItemListResponse)
async def list_items(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List items with pagination."""
    items = await repository.list_items(limit=limit, offset=offset)
    return ItemListResponse(items=items, count=len(items))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(item_id: uuid.UUID):
    """Delete an item by ID."""
    deleted = await repository.delete_item(item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
