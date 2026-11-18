from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import campaigns as camp_repo


def list_campaigns() -> list[dict[str, Any]]:
    conn = connect()
    try:
        return camp_repo.list_all(conn)
    finally:
        conn.close()


def list_events(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return event_repo.list_events(conn, day)
    finally:
        conn.close()


def add_event(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        et = body.get("event_type")
        if et in {"void", "return"}:
            raise HTTPException(
                400,
                "作废/退回须走唯一入口 POST /api/redeem/return，"
                "由其在同一事务内同步事件湖与事实状态，禁止只写事件不改事实",
            )
        if et not in {"issue", "redeem"}:
            raise HTTPException(400, "event_type 须为 issue/redeem（void/return 请走 /api/redeem/return）")
        code = (body.get("coupon_code") or "").strip()
        camp = (body.get("campaign_code") or "").strip()
        if not code or not camp:
            raise HTTPException(400, "coupon_code / campaign_code 必填")
        if et == "redeem" and fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 核销已钉扎，禁止再写入核销")
        if et == "redeem":
            prev = fact_repo.latest_redeem_fact(conn, code)
            if prev and prev["status"] != "voided":
                raise HTTPException(409, f"券 {code} 已核销（事实 #{prev['id']} 在效），禁止重复核销")
        amount = float(body.get("amount") or 0)
        if et == "redeem" and amount <= 0:
            # default face value from campaign
            camps = {c["code"]: c for c in camp_repo.list_all(conn)}
            if camp in camps:
                amount = float(camps[camp]["face_value"])
        occurred = body.get("occurred_at") or datetime.now().replace(microsecond=0).isoformat()
        eid = event_repo.insert_event(
            conn,
            event_type=et,
            coupon_code=code,
            campaign_code=camp,
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=body.get("note") or "",
        )
        fact_id = None
        if et == "redeem":
            fact_id = fact_repo.insert_fact(
                conn,
                coupon_code=code,
                campaign_code=camp,
                amount=amount,
                business_day=day,
                event_id=eid,
                status="open",
                kind="redeem",
            )
        conn.commit()
        return {"event_id": eid, "fact_id": fact_id, "business_day": day}
    finally:
        conn.close()
