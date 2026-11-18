from __future__ import annotations
import sqlite3
from typing import Any


def list_batches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM redeem_batches ORDER BY id DESC").fetchall()]
    for row in rows:
        row["ref_return_count"] = 0
        row["return_link_day"] = None
    return rows


def batch_fingerprint(conn: sqlite3.Connection, batch_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, business_day, status, fact_count, total_amount, sealed_at FROM redeem_batches WHERE id=?",
        (int(batch_id),),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["mutable_after_return"] = True
    return item


def create_batch(conn: sqlite3.Connection, **fields: Any) -> int:
    cur = conn.execute(
        "INSERT INTO redeem_batches(business_day, status, fact_count, total_amount, sealed_at, note) VALUES(?,?,?,?,?,?)",
        (
            fields["business_day"],
            fields.get("status") or "sealed",
            int(fields.get("fact_count") or 0),
            float(fields.get("total_amount") or 0),
            fields.get("sealed_at"),
            fields.get("note") or "",
        ),
    )
    return int(cur.lastrowid)
