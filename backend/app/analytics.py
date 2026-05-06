"""
analytics.py
------------
SQLite-based query logger for the admin dashboard.

Logs every /chat request so merchants can see:
  - What customers are searching for
  - Which queries went unanswered (no products found)
  - Top searched categories and brands
  - Average response time
"""

import os
import sqlite3
from datetime import datetime
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

_HERE    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HERE, os.getenv("DATA_DIR", "data"))
DB_PATH  = os.path.join(DATA_DIR, "analytics.db")


def init_db() -> None:
    """Create tables if they don't exist. Called once at server startup."""
    os.makedirs(DATA_DIR, exist_ok=True)
    with _conn() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS queries (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                ts             TEXT    NOT NULL,
                session_id     TEXT,
                message        TEXT    NOT NULL,
                category       TEXT,
                vendor         TEXT,
                products_found INTEGER DEFAULT 0,
                was_answered   INTEGER DEFAULT 1,
                fallback_used  INTEGER DEFAULT 0,
                response_ms    INTEGER DEFAULT 0
            )
        """)
        db.commit()


@contextmanager
def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def log_query(
    session_id:     str | None,
    message:        str,
    intent:         dict | None,
    products_found: int,
    was_answered:   bool,
    fallback_used:  bool,
    response_ms:    int,
) -> None:
    try:
        with _conn() as db:
            db.execute(
                """
                INSERT INTO queries
                    (ts, session_id, message, category, vendor,
                     products_found, was_answered, fallback_used, response_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                    session_id,
                    message[:500],
                    intent.get("category") if intent else None,
                    intent.get("vendor")   if intent else None,
                    products_found,
                    1 if was_answered else 0,
                    1 if fallback_used else 0,
                    response_ms,
                ),
            )
            db.commit()
    except Exception as exc:
        print(f"[analytics] log_query failed: {exc}")


def get_recent_queries(limit: int = 100, offset: int = 0) -> list[dict]:
    try:
        with _conn() as db:
            rows = db.execute(
                "SELECT * FROM queries ORDER BY ts DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception as exc:
        print(f"[analytics] get_recent_queries failed: {exc}")
        return []


def get_total_count() -> int:
    try:
        with _conn() as db:
            return db.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
    except Exception:
        return 0


def get_summary() -> dict:
    try:
        with _conn() as db:
            total      = db.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
            unanswered = db.execute(
                "SELECT COUNT(*) FROM queries WHERE was_answered = 0"
            ).fetchone()[0]
            avg_ms = db.execute(
                "SELECT AVG(response_ms) FROM queries"
            ).fetchone()[0] or 0

            top_categories = db.execute(
                """
                SELECT category AS label, COUNT(*) AS count
                FROM queries
                WHERE category IS NOT NULL AND category != ''
                GROUP BY category ORDER BY count DESC LIMIT 10
                """
            ).fetchall()

            top_vendors = db.execute(
                """
                SELECT vendor AS label, COUNT(*) AS count
                FROM queries
                WHERE vendor IS NOT NULL AND vendor != ''
                GROUP BY vendor ORDER BY count DESC LIMIT 10
                """
            ).fetchall()

            unanswered_msgs = db.execute(
                """
                SELECT message, ts
                FROM queries
                WHERE was_answered = 0
                ORDER BY ts DESC LIMIT 20
                """
            ).fetchall()

            return {
                "total_queries":      total,
                "unanswered_count":   unanswered,
                "answer_rate_pct":    round((total - unanswered) / total * 100, 1) if total else 0,
                "avg_response_ms":    round(avg_ms),
                "top_categories":     [dict(r) for r in top_categories],
                "top_vendors":        [dict(r) for r in top_vendors],
                "unanswered_queries": [dict(r) for r in unanswered_msgs],
            }
    except Exception as exc:
        print(f"[analytics] get_summary failed: {exc}")
        return {
            "total_queries": 0, "unanswered_count": 0,
            "answer_rate_pct": 0, "avg_response_ms": 0,
            "top_categories": [], "top_vendors": [], "unanswered_queries": [],
        }
