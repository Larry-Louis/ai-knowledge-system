"""Persistent FIFO queue backed by SQLite for memory pipeline events.

Designed for single-worker, survives process restart.
"""
import json
import sqlite3
import threading
import time
import uuid
import os

DB_PATH = "/app/data/memory_queue.db"


class PersistentQueue:
    def __init__(self, db_path: str = DB_PATH):
        self._local = threading.local()
        self._db_path = db_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_db(self):
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                retries INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                error TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_queue_status
            ON queue(status, created_at)
        """)
        conn.commit()
        conn.close()

    def enqueue(self, data: dict, max_retries: int = 3) -> str:
        """Add an item to the queue. Returns item ID."""
        item_id = str(uuid.uuid4())
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO queue (id, data, status, max_retries, created_at, updated_at) VALUES (?, ?, 'pending', ?, ?, ?)",
            (item_id, json.dumps(data, ensure_ascii=False), max_retries, now, now),
        )
        conn.commit()
        return item_id

    def dequeue(self, batch_size: int = 1) -> list[dict]:
        """Get next pending items and mark them as processing."""
        conn = self._get_conn()
        with conn:
            rows = conn.execute(
                "SELECT * FROM queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT ?",
                (batch_size,),
            ).fetchall()
            if not rows:
                return []
            ids = [r["id"] for r in rows]
            now = time.time()
            conn.execute(
                f"UPDATE queue SET status = 'processing', updated_at = ? WHERE id IN ({','.join('?' for _ in ids)})",
                (now, *ids),
            )
        return [{"id": r["id"], "data": json.loads(r["data"]), "retries": r["retries"]} for r in rows]

    def mark_done(self, item_id: str):
        """Mark an item as completed."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE queue SET status = 'done', updated_at = ? WHERE id = ?",
            (time.time(), item_id),
        )
        conn.commit()

    def mark_failed(self, item_id: str, error: str):
        """Mark as failed. Will retry if retries < max_retries."""
        conn = self._get_conn()
        row = conn.execute("SELECT retries, max_retries FROM queue WHERE id = ?", (item_id,)).fetchone()
        if not row:
            return
        retries = row["retries"] + 1
        if retries >= row["max_retries"]:
            status = "dead"
        else:
            status = "pending"  # Will be picked up again
        conn.execute(
            "UPDATE queue SET status = ?, retries = ?, error = ?, updated_at = ? WHERE id = ?",
            (status, retries, error[:500], time.time(), item_id),
        )
        conn.commit()

    def recover_stale(self, timeout: int = 30):
        """Recover items stuck in 'processing' status (e.g. after crash)."""
        conn = self._get_conn()
        cutoff = time.time() - timeout
        conn.execute(
            "UPDATE queue SET status = 'pending', updated_at = ? WHERE status = 'processing' AND updated_at < ?",
            (time.time(), cutoff),
        )
        conn.commit()

    def stats(self) -> dict:
        """Get queue statistics."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM queue GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def cleanup(self, max_age: int = 86400):
        """Remove completed items older than max_age seconds."""
        conn = self._get_conn()
        cutoff = time.time() - max_age
        conn.execute(
            "DELETE FROM queue WHERE status IN ('done', 'dead') AND updated_at < ?",
            (cutoff,),
        )
        conn.commit()
