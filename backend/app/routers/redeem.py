from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Query
from app.services import redeem_service as svc

router = APIRouter(tags=["redeem"])


@router.get("/facts")
def facts(business_day: str | None = Query(None)):
    return svc.list_facts(business_day)


@router.get("/redeem/preview")
def preview(business_day: str | None = Query(None)):
    return svc.preview(business_day)


@router.post("/redeem/seal")
def seal(body: dict[str, Any]):
    return svc.seal(body)


@router.post("/redeem/return")
def return_(body: dict[str, Any]):
    return svc.return_redemption(body)


@router.get("/batches")
def batches():
    return svc.list_batches()


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: int):
    return svc.batch_detail(batch_id)


@router.get("/returns/preview")
def returns_preview(business_day: str | None = None):
    return svc.preview_returns(business_day)
