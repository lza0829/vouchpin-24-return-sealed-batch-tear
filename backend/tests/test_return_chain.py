"""负向入湖链路收口回归：原 sealed 指纹只读 + 负向事件/事实齐套。

打出四个撕裂场景（任一未对齐，回执 success 不算过关）：
  1. 改脏原批合计 —— 已钉退回不得改写原批批头/已钉事实金额；
  2. 事件有事实无 —— return 事件入湖必须同事物齐套物化负向 open 事实（券尾偶位也不例外）；
  3. 半截改脏原批 —— 旧半截路径（只落事件+改脏原批、不落事实）必须被总览/批次列表暴露而非掩盖，
     且按事件湖锚点恢复钉时指纹、补落负向事实后恢复绿色；
  4. 目标日预览缺负向行 —— 钉预览必须吃得到负向 return open 行，钉扎结果与预览同源。
"""
from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient

from app.main import app
from app.config import DB_PATH

client = TestClient(app)


def set_day(day: str) -> None:
    r = client.put("/api/settings/day", json={"business_day": day})
    assert r.status_code == 200, r.text


def redeem(code: str, day: str, amount: float, camp: str = "NEW10") -> dict:
    r = client.post(
        "/api/events",
        json={
            "event_type": "redeem",
            "coupon_code": code,
            "campaign_code": camp,
            "amount": amount,
            "business_day": day,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def seal(day: str) -> dict:
    r = client.post("/api/redeem/seal", json={"business_day": day})
    assert r.status_code == 200, r.text
    return r.json()


def ret(code: str, day: str) -> dict:
    r = client.post("/api/redeem/return", json={"coupon_code": code, "business_day": day})
    assert r.status_code == 200, r.text
    return r.json()


def test_01_original_batch_fingerprint_untouched_by_return():
    """场景一：已钉退回落负向事实，原 sealed 批合计/笔数/已钉事实金额一分不动。"""
    set_day("2026-11-01")
    redeem("C-A1", "2026-11-01", 10)
    redeem("C-A2", "2026-11-01", 20)
    b = seal("2026-11-01")
    bid = b["batch_id"]
    assert b["total_amount"] == 30 and b["fact_count"] == 2

    r = ret("C-A1", "2026-11-02")
    assert r["policy"] == "return"
    assert r["fact_id"] is not None, "回执成功必须带负向事实"
    assert r["original_batch_intact"] is True and r["return_chain_aligned"] is True

    d = client.get(f"/api/batches/{bid}").json()
    assert d["fingerprint"]["intact"] is True
    assert d["batch"]["total_amount"] == 30 and d["batch"]["fact_count"] == 2
    assert sorted(f["amount"] for f in d["facts"]) == [10, 20], "已钉事实行金额不得被改"
    # 原批可点开对照：负向链关联如实
    assert d["return_links"]["ref_return_count"] == 1
    assert d["return_links"]["linked_return_days"] == ["2026-11-02"]
    assert d["return_facts"][0]["amount"] == -10
    assert d["return_facts"][0]["status"] == "open"

    rows = client.get("/api/batches").json()
    row = [x for x in rows if x["id"] == bid][0]
    assert row["fingerprint_intact"] is True
    assert row["ref_return_count"] == 1
    assert row["linked_return_days"] == ["2026-11-02"]


def test_02_return_event_always_materializes_fact_even_digit_coupon():
    """场景二：券尾偶位也不许「事件入湖、事实缺席」；回执成功 ⇒ 事件+负向事实齐套。"""
    set_day("2026-11-03")
    redeem("C-E2", "2026-11-03", 12)  # 券尾偶位：旧路径按此跳过负向事实
    seal("2026-11-03")

    r = ret("C-E2", "2026-11-04")
    assert r["fact_id"] is not None

    evs = client.get("/api/events?business_day=2026-11-04").json()
    rets = [e for e in evs if e["event_type"] == "return" and e["coupon_code"] == "C-E2"]
    assert len(rets) == 1, "return 事件必须入湖"

    facts = client.get("/api/facts?business_day=2026-11-04").json()
    rf = [f for f in facts if f["kind"] == "return" and f["coupon_code"] == "C-E2"]
    assert len(rf) == 1, "负向 open 事实必须与事件齐套"
    assert rf[0]["event_id"] == rets[0]["id"]
    assert rf[0]["status"] == "open" and rf[0]["amount"] == -12
    assert rf[0]["ref_fact_id"] == r["ref_fact_id"]

    dash = client.get("/api/dashboard").json()
    assert dash["return_chain_aligned"] is True
    assert dash["original_batch_intact"] is True


def test_03_torn_half_write_is_exposed_not_masked():
    """场景三：半截路径（事件落湖+改脏原批、不落负向事实）必须被暴露；
    按事件湖锚点恢复钉时指纹并补落负向事实后，总览恢复绿色。"""
    set_day("2026-11-05")
    redeem("C-H1", "2026-11-05", 15)
    b = seal("2026-11-05")
    bid = b["batch_id"]

    # 模拟旧半截负向写路径：return 事件落湖、原批批头与已钉事实被改脏、负向事实缺席
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        fact = conn.execute(
            "SELECT * FROM redeem_facts WHERE batch_id=? AND status='sealed'", (bid,)
        ).fetchone()
        cur = conn.execute(
            "INSERT INTO coupon_events(event_type, coupon_code, campaign_code, amount, business_day, occurred_at, note)"
            " VALUES('return', 'C-H1', 'NEW10', -15, '2026-11-06', '2026-11-06T09:00:00', 'legacy torn write')"
        )
        eid = int(cur.lastrowid)
        conn.execute(
            "UPDATE redeem_batches SET total_amount=ROUND(total_amount-15, 2) WHERE id=?", (bid,)
        )
        conn.execute(
            "UPDATE redeem_facts SET amount=ROUND(amount-15, 2) WHERE id=?", (int(fact["id"]),)
        )
        conn.commit()
        fact_id = int(fact["id"])
    finally:
        conn.close()

    # 不许再撒谎：总览/批次列表/原批对照必须暴露撕裂
    dash = client.get("/api/dashboard").json()
    assert dash["original_batch_intact"] is False, "改脏原批必须暴露"
    assert dash["return_chain_aligned"] is False, "有事件无事实必须暴露"
    row = [x for x in client.get("/api/batches").json() if x["id"] == bid][0]
    assert row["fingerprint_intact"] is False
    d = client.get(f"/api/batches/{bid}").json()
    assert d["fingerprint"]["intact"] is False
    assert d["fingerprint"]["mismatched_fact_ids"] == [fact_id], "事件湖锚点必须识破明细改脏"

    # 修复：按事件湖锚点恢复钉时指纹 + 补落缺失的负向 open 事实
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "UPDATE redeem_facts SET amount=("
            "  SELECT amount FROM coupon_events WHERE coupon_events.id = redeem_facts.event_id"
            ") WHERE batch_id=?",
            (bid,),
        )
        agg = conn.execute(
            "SELECT COUNT(*) c, ROUND(SUM(amount),2) s FROM redeem_facts"
            " WHERE batch_id=? AND status='sealed'",
            (bid,),
        ).fetchone()
        conn.execute(
            "UPDATE redeem_batches SET fact_count=?, total_amount=? WHERE id=?",
            (int(agg["c"]), round(float(agg["s"]), 2), bid),
        )
        conn.execute(
            "INSERT INTO redeem_facts(coupon_code, campaign_code, amount, business_day, event_id, status, kind, ref_fact_id)"
            " VALUES('C-H1', 'NEW10', -15, '2026-11-06', ?, 'open', 'return', ?)",
            (eid, fact_id),
        )
        conn.commit()
    finally:
        conn.close()

    dash = client.get("/api/dashboard").json()
    assert dash["original_batch_intact"] is True
    assert dash["return_chain_aligned"] is True
    row = [x for x in client.get("/api/batches").json() if x["id"] == bid][0]
    assert row["fingerprint_intact"] is True
    assert row["ref_return_count"] == 1


def test_04_target_day_preview_includes_negative_return_rows():
    """场景四：目标未钉日预览必须吃得到负向 return open 行，钉扎与预览同源。"""
    set_day("2026-11-07")
    redeem("C-P1", "2026-11-07", 8)
    seal("2026-11-07")
    set_day("2026-11-08")
    redeem("C-P2", "2026-11-08", 5)
    ret("C-P1", "2026-11-08")

    p = client.get("/api/redeem/preview?business_day=2026-11-08").json()
    assert sorted(f["kind"] for f in p["facts"]) == ["redeem", "return"], "预览不得吃掉负向行"
    assert p["open_count"] == 2
    assert p["open_total"] == -3.0, "预览合计必须含负向行"
    assert p["return_open_count"] == 1 and p["return_open_total"] == -8

    b = seal("2026-11-08")
    assert b["fact_count"] == 2 and b["total_amount"] == -3.0, "钉扎结果必须与预览同源"
    d = client.get(f"/api/batches/{b['batch_id']}").json()
    assert d["fingerprint"]["intact"] is True

    rp = client.get("/api/returns/preview?business_day=2026-11-09").json()
    assert rp["return_open_count"] == 0  # 已随 11-08 钉扎，不再挂 open


def test_05_guards_and_void_path():
    """互斥分派与写闸：未钉冲销只在原业务日；已钉只追加到他日；/api/events 不收 void/return。"""
    set_day("2026-11-09")
    redeem("C-G1", "2026-11-09", 10)
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G1", "business_day": "2026-11-10"})
    assert r.status_code == 400, "未钉事实不许跨日冲销"
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G1"})
    assert r.status_code == 200 and r.json()["policy"] == "void"
    p = client.get("/api/redeem/preview?business_day=2026-11-09").json()
    assert p["open_count"] == 0 and p["open_total"] == 0, "冲销后预览合计同步减少"
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G1"})
    assert r.status_code == 409, "已冲销不可重复退回"

    r = client.post(
        "/api/events",
        json={"event_type": "return", "coupon_code": "X-1", "campaign_code": "NEW10",
              "amount": -1, "business_day": "2026-11-09"},
    )
    assert r.status_code == 400, "void/return 只走退回唯一入口"

    set_day("2026-11-10")
    redeem("C-G2", "2026-11-10", 10)
    seal("2026-11-10")
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G2", "business_day": "2026-11-10"})
    assert r.status_code == 409, "已钉日不可回改"
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G2", "business_day": "2026-11-11"})
    assert r.status_code == 200
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G2", "business_day": "2026-11-12"})
    assert r.status_code == 409, "在效退回事实存在，不可重复退回"

    set_day("2026-11-13")
    redeem("C-G3", "2026-11-13", 6)
    seal("2026-11-13")
    set_day("2026-11-14")
    redeem("C-G4", "2026-11-14", 6)
    seal("2026-11-14")
    r = client.post("/api/redeem/return", json={"coupon_code": "C-G3", "business_day": "2026-11-14"})
    assert r.status_code == 409, "目标日已钉扎，退回无法落账"
