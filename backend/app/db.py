from __future__ import annotations
import sqlite3
from app.config import DB_PATH

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  kind TEXT NOT NULL DEFAULT 'redeem',
  ref_fact_id INTEGER,
  void_event_id INTEGER
);
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  note TEXT NOT NULL DEFAULT ''
);
'''

# redeem_facts 单一事实源约定：
#   status: open（待钉）/ sealed（已钉，永不回改）/ voided（未钉冲销，行保留审计）
#   kind:   redeem（核销）/ return（已钉退回的负向事实，落在另一业务日，ref_fact_id 指向原核销事实）
# 券码唯一性不再靠 UNIQUE 约束，而由服务层在写事务内保证：
#   同一 coupon_code 至多一条 status != 'voided' 的 kind='redeem' 事实。


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _fact_columns(conn: sqlite3.Connection) -> set[str]:
    return {str(r["name"]) for r in conn.execute("PRAGMA table_info(redeem_facts)")}


def _migrate(conn: sqlite3.Connection) -> None:
    # 旧表 coupon_code 带 UNIQUE 自动索引 → 重建表去掉它（退回事实与原核销事实同券码）
    has_unique = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND tbl_name='redeem_facts'"
        " AND name LIKE 'sqlite_autoindex%' LIMIT 1"
    ).fetchone()
    if has_unique:
        conn.execute("ALTER TABLE redeem_facts RENAME TO redeem_facts_old")
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO redeem_facts(id, coupon_code, campaign_code, amount, business_day, event_id, batch_id, status)"
            " SELECT id, coupon_code, campaign_code, amount, business_day, event_id, batch_id, status FROM redeem_facts_old"
        )
        conn.execute("DROP TABLE redeem_facts_old")
    cols = _fact_columns(conn)
    for col, ddl in (
        ("kind", "TEXT NOT NULL DEFAULT 'redeem'"),
        ("ref_fact_id", "INTEGER"),
        ("void_event_id", "INTEGER"),
    ):
        if col not in cols:
            conn.execute(f"ALTER TABLE redeem_facts ADD COLUMN {col} {ddl}")


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()
