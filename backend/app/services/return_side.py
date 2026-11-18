from __future__ import annotations

from typing import Any
import sqlite3

# 负向入湖链路的同源约束（唯一真相来源）：
#   1. 原 sealed 批指纹只读——批头笔数/合计与其 sealed 事实明细永不回改；
#   2. 负向写路径（void/return）必须事件湖与事实物化同事务齐套；
#   3. 总览/批次列表的退回关联、指纹完好性一律由本模块实时重算，禁止硬编码撒谎。


def verify_batch_fingerprint(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    """原批只读闸：钉时指纹 = 批头(笔数/合计) 与本批 sealed 事实明细重算值一致，
    且每条 sealed 事实金额与其源事件（只增不改的事件湖）金额一致——
    连批头带明细一起改脏也能被事件湖锚点识破。"""
    row = conn.execute(
        "SELECT id, business_day, status, fact_count, total_amount, sealed_at FROM redeem_batches WHERE id=?",
        (int(batch_id),),
    ).fetchone()
    if not row:
        return {"batch_id": int(batch_id), "exists": False, "intact": False}
    facts = conn.execute(
        """
        SELECT f.id, f.amount, e.amount AS event_amount
        FROM redeem_facts f LEFT JOIN coupon_events e ON e.id = f.event_id
        WHERE f.batch_id=? AND f.status='sealed'
        """,
        (int(batch_id),),
    ).fetchall()
    sealed_count = len(facts)
    sealed_total = round(sum(float(f["amount"]) for f in facts), 2)
    mismatched = [
        int(f["id"])
        for f in facts
        if f["event_amount"] is None
        or round(float(f["event_amount"]), 2) != round(float(f["amount"]), 2)
    ]
    intact = (
        row["status"] == "sealed"
        and int(row["fact_count"]) == sealed_count
        and round(float(row["total_amount"]), 2) == sealed_total
        and not mismatched
    )
    return {
        "batch_id": int(batch_id),
        "exists": True,
        "intact": intact,
        "business_day": row["business_day"],
        "fact_count": int(row["fact_count"]),
        "sealed_fact_count": sealed_count,
        "total_amount": round(float(row["total_amount"]), 2),
        "sealed_facts_total": sealed_total,
        "mismatched_fact_ids": mismatched,
    }


def all_batches_intact(conn: sqlite3.Connection) -> bool:
    ids = [
        int(r["id"])
        for r in conn.execute("SELECT id FROM redeem_batches WHERE status='sealed'").fetchall()
    ]
    return all(verify_batch_fingerprint(conn, bid)["intact"] for bid in ids)


def return_chain_gaps(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """负向事实链缺口：湖里有 void/return 事件，却缺对应事实物化（半截路径）。"""
    gaps: list[dict[str, Any]] = []
    for ev in conn.execute(
        "SELECT id, coupon_code, business_day FROM coupon_events WHERE event_type='return' ORDER BY id"
    ).fetchall():
        hit = conn.execute(
            "SELECT 1 FROM redeem_facts WHERE kind='return' AND event_id=? LIMIT 1",
            (ev["id"],),
        ).fetchone()
        if not hit:
            gaps.append(
                {
                    "event_id": int(ev["id"]),
                    "event_type": "return",
                    "coupon_code": ev["coupon_code"],
                    "business_day": ev["business_day"],
                }
            )
    for ev in conn.execute(
        "SELECT id, coupon_code, business_day FROM coupon_events WHERE event_type='void' ORDER BY id"
    ).fetchall():
        hit = conn.execute(
            "SELECT 1 FROM redeem_facts WHERE status='voided' AND void_event_id=? LIMIT 1",
            (ev["id"],),
        ).fetchone()
        if not hit:
            gaps.append(
                {
                    "event_id": int(ev["id"]),
                    "event_type": "void",
                    "coupon_code": ev["coupon_code"],
                    "business_day": ev["business_day"],
                }
            )
    return gaps


def return_fact_for_event(conn: sqlite3.Connection, event_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM redeem_facts WHERE kind='return' AND event_id=? LIMIT 1",
        (int(event_id),),
    ).fetchone()
    return dict(row) if row else None


def batch_return_links(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any]:
    """原批对照：指向本批 sealed 事实的在效退回事实、落账业务日与退回事件。"""
    rows = conn.execute(
        """
        SELECT rf.id, rf.coupon_code, rf.amount, rf.business_day, rf.event_id, rf.status, rf.ref_fact_id
        FROM redeem_facts rf
        JOIN redeem_facts src ON src.id = rf.ref_fact_id
        WHERE rf.kind='return' AND rf.status!='voided' AND src.batch_id=?
        ORDER BY rf.id
        """,
        (int(batch_id),),
    ).fetchall()
    items = [dict(r) for r in rows]
    days = sorted({str(r["business_day"]) for r in items})
    return {
        "ref_return_count": len(items),
        "linked_return_days": days,
        "linked_return_day": days[-1] if days else None,
        "return_event_ids": [int(r["event_id"]) for r in items],
        "return_open_total": round(
            sum(float(r["amount"]) for r in items if r["status"] == "open"), 2
        ),
    }


def dashboard_return_hint(conn: sqlite3.Connection, day: str) -> dict[str, Any]:
    """总览退回提示：负向 open 行实时重算；原批指纹与负向事实链分开如实上报。"""
    agg = conn.execute(
        "SELECT COUNT(*) c, COALESCE(ROUND(SUM(amount),2),0) s FROM redeem_facts"
        " WHERE kind='return' AND status='open' AND business_day=?",
        (day,),
    ).fetchone()
    gaps = return_chain_gaps(conn)
    return {
        "business_day": day,
        "return_open_count": int(agg["c"]),
        "return_open_total": round(float(agg["s"]), 2),
        "original_batch_intact": all_batches_intact(conn),
        "return_chain_aligned": not gaps,
        "return_chain_gaps": gaps,
    }
