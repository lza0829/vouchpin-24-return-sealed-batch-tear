from __future__ import annotations
import sqlite3
from typing import Any


def list_facts(conn: sqlite3.Connection, business_day: str | None = None) -> list[dict[str, Any]]:
    if business_day:
        rows = conn.execute(
            "SELECT * FROM redeem_facts WHERE business_day=? ORDER BY id",
            (business_day,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM redeem_facts ORDER BY id DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


def insert_fact(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, status, kind, ref_fact_id)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (
            fields["coupon_code"],
            fields["campaign_code"],
            float(fields["amount"]),
            fields["business_day"],
            int(fields["event_id"]),
            fields.get("status") or "open",
            fields.get("kind") or "redeem",
            fields.get("ref_fact_id"),
        ),
    )
    return int(cur.lastrowid)


def latest_redeem_fact(conn: sqlite3.Connection, coupon_code: str) -> dict[str, Any] | None:
    """券的最新一条核销事实（kind='redeem'，含已冲销）；退回事实不参与。"""
    row = conn.execute(
        "SELECT * FROM redeem_facts WHERE coupon_code=? AND kind='redeem' ORDER BY id DESC LIMIT 1",
        (coupon_code,),
    ).fetchone()
    return dict(row) if row else None


def active_return_for(conn: sqlite3.Connection, ref_fact_id: int) -> dict[str, Any] | None:
    """指向某核销事实的在效退回事实（未冲销即视为在效）。"""
    row = conn.execute(
        "SELECT * FROM redeem_facts WHERE kind='return' AND ref_fact_id=? AND status!='voided'"
        " ORDER BY id DESC LIMIT 1",
        (ref_fact_id,),
    ).fetchone()
    return dict(row) if row else None


def open_facts_for_day(conn: sqlite3.Connection, business_day: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM redeem_facts WHERE business_day=? AND status='open' ORDER BY id",
        (business_day,),
    ).fetchall()
    return [dict(r) for r in rows]


def mark_voided(conn: sqlite3.Connection, fact_id: int, void_event_id: int) -> bool:
    """未钉冲销：仅 open 事实可作废；sealed 行命中不了 WHERE，返回 False。"""
    cur = conn.execute(
        "UPDATE redeem_facts SET status='voided', void_event_id=? WHERE id=? AND status='open'",
        (void_event_id, fact_id),
    )
    return cur.rowcount == 1


def mark_batched(conn: sqlite3.Connection, fact_ids: list[int], batch_id: int) -> None:
    for fid in fact_ids:
        conn.execute(
            "UPDATE redeem_facts SET status='sealed', batch_id=? WHERE id=? AND status='open'",
            (batch_id, fid),
        )


def day_is_sealed(conn: sqlite3.Connection, business_day: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM redeem_batches WHERE business_day=? AND status='sealed' LIMIT 1",
        (business_day,),
    ).fetchone()
    return row is not None
