"""Billing usage and plan endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..core import get_store, now_iso

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@router.get("/usage")
async def usage():
    return {
        "current_plan": "free",
        "api_calls": {"used": 0, "limit": 10000},
        "storage_mb": {"used": 0, "limit": 10240},
        "billing_period": {"start": now_iso(), "end": now_iso()},
    }


class PlanIn(BaseModel):
    plan: str


@router.post("/plan")
async def plan(body: PlanIn):
    return {"success": True, "plan": body.plan, "effective_date": now_iso()}
