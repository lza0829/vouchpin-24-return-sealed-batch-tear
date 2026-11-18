from __future__ import annotations
from datetime import datetime
from typing import Any
from fastapi import HTTPException
from app.db import connect
from app.repositories import settings as settings_repo
from app.repositories import events as event_repo
from app.repositories import facts as fact_repo
from app.repositories import batches as batch_repo


def list_facts(business_day: str | None = None) -> list[dict[str, Any]]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        return fact_repo.list_facts(conn, day)
    finally:
        conn.close()


def preview(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        day = business_day or settings_repo.get(conn, "business_day")
        opens = fact_repo.open_facts_for_day(conn, day)
        # 钉扎预览与钉扎写闸同源：负向 return open 行必须入列、入合计，
        # 钉扎结果才与预览一致（负向行不漏钉）。
        returns = [f for f in opens if (f.get("kind") or "") == "return"]
        total = round(sum(float(f["amount"]) for f in opens), 2)
        return {
            "business_day": day,
            "open_count": len(opens),
            "open_total": total,
            "return_open_count": len(returns),
            "return_open_total": round(sum(float(f["amount"]) for f in returns), 2),
            "already_sealed": fact_repo.day_is_sealed(conn, day),
            "facts": opens,
        }
    finally:
        conn.close()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    conn = connect(immediate=True)
    try:
        day = body.get("business_day") or settings_repo.get(conn, "business_day")
        if fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 已有 sealed 钉扎批")
        opens = fact_repo.open_facts_for_day(conn, day)
        if not opens:
            raise HTTPException(400, "无可钉扎的 open 核销事实")
        total = round(sum(float(f["amount"]) for f in opens), 2)
        bid = batch_repo.create_batch(
            conn,
            business_day=day,
            status="sealed",
            fact_count=len(opens),
            total_amount=total,
            sealed_at=datetime.now().replace(microsecond=0).isoformat(),
            note=body.get("note") or "",
        )
        fact_repo.mark_batched(conn, [int(f["id"]) for f in opens], bid)
        conn.commit()
        return {
            "batch_id": bid,
            "business_day": day,
            "fact_count": len(opens),
            "total_amount": total,
            "status": "sealed",
        }
    finally:
        conn.close()


def return_redemption(body: dict[str, Any]) -> dict[str, Any]:
    """核销后退回的唯一入口。两条策略按事实钉扎态全局互斥，只走一条：

    - open 事实 → 未钉冲销：写 void 事件（负额）并作废该事实（行保留审计），
      预览合计同步减少；只能落在事实原业务日。
    - sealed 事实 → 已钉只追加：原批笔数/合计/事实行永不回改；在另一业务日写
      return 事件并物化负向退回事实（open，供后续钉扎），原批仍为现行凭证。
    """
    conn = connect(immediate=True)
    try:
        code = (body.get("coupon_code") or "").strip()
        if not code:
            raise HTTPException(400, "coupon_code 必填")
        fact = fact_repo.latest_redeem_fact(conn, code)
        if not fact:
            raise HTTPException(404, f"券 {code} 无核销事实，无可退回")
        if fact["status"] == "voided":
            raise HTTPException(409, f"券 {code} 的核销事实 #{fact['id']} 已冲销，不可重复退回")
        note = (body.get("note") or "").strip()
        occurred = datetime.now().replace(microsecond=0).isoformat()
        amount = -round(float(fact["amount"]), 2)

        if fact["status"] == "open":
            # 策略一：未钉冲销——只能落在事实原业务日
            day = str(fact["business_day"])
            req_day = (body.get("business_day") or "").strip()
            if req_day and req_day != day:
                raise HTTPException(400, f"未钉事实只能在原业务日 {day} 冲销")
            if fact_repo.day_is_sealed(conn, day):
                raise HTTPException(409, f"业务日 {day} 已钉扎，存在 open 事实属异常，拒绝冲销")
            eid = event_repo.insert_event(
                conn,
                event_type="void",
                coupon_code=code,
                campaign_code=fact["campaign_code"],
                amount=amount,
                business_day=day,
                occurred_at=occurred,
                note=note or f"冲销核销事件 #{fact['event_id']}（事实 #{fact['id']}）",
            )
            if not fact_repo.mark_voided(conn, int(fact["id"]), eid):
                raise HTTPException(409, f"事实 #{fact['id']} 非 open，冲销被拒绝")
            conn.commit()
            return {
                "policy": "void",
                "event_id": eid,
                "fact_id": int(fact["id"]),
                "business_day": day,
                "amount": amount,
            }

        if fact["status"] != "sealed":
            raise HTTPException(409, f"事实 #{fact['id']} 状态 {fact['status']} 不可退回")

        # 策略二：已钉只追加——原批笔数/合计/已钉事实行永不回改；
        # return 事件与负向退回事实（kind='return'，open）同事务齐套落地。
        day = (body.get("business_day") or "").strip() or settings_repo.get(conn, "business_day")
        if day == fact["business_day"]:
            raise HTTPException(409, f"已钉日 {day} 不可回改，退回只能落到其它业务日")
        if fact_repo.day_is_sealed(conn, day):
            raise HTTPException(409, f"业务日 {day} 已钉扎，退回无法落账，请换未钉扎业务日")
        if fact_repo.active_return_for(conn, int(fact["id"])):
            raise HTTPException(409, f"券 {code} 已存在在效退回事实，不可重复退回")
        from app.services import return_side
        eid = event_repo.insert_event(
            conn,
            event_type="return",
            coupon_code=code,
            campaign_code=fact["campaign_code"],
            amount=amount,
            business_day=day,
            occurred_at=occurred,
            note=note or f"退回已钉事实 #{fact['id']}（批次 #{fact['batch_id']}，原业务日 {fact['business_day']}）",
        )
        fid = fact_repo.insert_fact(
            conn,
            coupon_code=code,
            campaign_code=fact["campaign_code"],
            amount=amount,
            business_day=day,
            event_id=eid,
            status="open",
            kind="return",
            ref_fact_id=int(fact["id"]),
        )
        # 收口自检（原批只读闸 + 负向事实链）：任一未对齐，整事务回滚，回执不得成功。
        if fact.get("batch_id"):
            fp = return_side.verify_batch_fingerprint(conn, int(fact["batch_id"]))
            if not fp["intact"]:
                raise HTTPException(
                    500,
                    f"原批 #{fact['batch_id']} 钉时指纹校验失败（批头 {fp['fact_count']}笔/{fp['total_amount']} "
                    f"vs 明细 {fp['sealed_fact_count']}笔/{fp['sealed_facts_total']}），退回已整体回滚",
                )
        if not return_side.return_fact_for_event(conn, eid):
            raise HTTPException(500, f"return 事件 #{eid} 已入湖但负向事实缺失，退回已整体回滚")
        conn.commit()
        return {
            "policy": "return",
            "success": True,
            "event_id": eid,
            "fact_id": fid,
            "ref_fact_id": int(fact["id"]),
            "original_batch_id": fact.get("batch_id"),
            "original_batch_intact": True,
            "return_chain_aligned": True,
            "business_day": day,
            "amount": amount,
        }
    finally:
        conn.close()


def list_batches() -> list[dict[str, Any]]:
    conn = connect()
    try:
        from app.services import return_side
        rows = batch_repo.list_batches(conn)
        for row in rows:
            # 批次列表如实给出退回关联与指纹校验，原批可点开对照。
            row.update(return_side.batch_return_links(conn, int(row["id"])))
            row["fingerprint_intact"] = return_side.verify_batch_fingerprint(conn, int(row["id"]))["intact"]
        return rows
    finally:
        conn.close()


def batch_detail(batch_id: int) -> dict[str, Any]:
    """原批对照：批头 + 钉时指纹校验 + sealed 明细 + 关联退回事实。"""
    conn = connect()
    try:
        from app.services import return_side
        batch = batch_repo.get_batch(conn, batch_id)
        if not batch:
            raise HTTPException(404, f"批次 #{batch_id} 不存在")
        facts = fact_repo.facts_for_batch(conn, batch_id)
        returns = fact_repo.returns_for_batch(conn, batch_id)
        return {
            "batch": batch,
            "fingerprint": return_side.verify_batch_fingerprint(conn, batch_id),
            "facts": facts,
            "return_links": return_side.batch_return_links(conn, batch_id),
            "return_facts": returns,
        }
    finally:
        conn.close()


def preview_returns(business_day: str | None = None) -> dict[str, Any]:
    conn = connect()
    try:
        from app.services import return_side
        day = business_day or settings_repo.get(conn, "business_day")
        hint = return_side.dashboard_return_hint(conn, day)
        opens = fact_repo.open_facts_for_day(conn, day)
        hint["return_facts"] = [f for f in opens if (f.get("kind") or "") == "return"]
        return hint
    finally:
        conn.close()
