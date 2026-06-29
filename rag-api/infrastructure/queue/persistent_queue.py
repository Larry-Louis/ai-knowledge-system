"""
持久化 FIFO 队列，基于 SQLite，用于记忆管道事件。

为单工作线程设计，支持进程重启后继续运行。
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
        """获取线程本地的数据库连接。"""
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
        """
        [S1-3] 入队：将记忆管道事件添加到持久化队列

        主要工作流：
        1. 生成唯一 item_id
        2. 将数据序列化为 JSON
        3. 插入到 SQLite 队列表中，状态为 pending
        4. 返回 item_id
        """
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
        """
        [S1-3] 出队：获取下一个待处理事件并标记为 processing

        主要工作流：
        1. 按创建时间升序获取指定数量的 pending 事件
        2. 将状态更新为 processing
        3. 返回事件列表（包含 id、data、retries）
        """
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
        """
        [S1-3] 标记事件为完成

        主要工作流：
        1. 将指定事件的状态更新为 done
        2. 记录完成时间
        """
        conn = self._get_conn()
        conn.execute(
            "UPDATE queue SET status = 'done', updated_at = ? WHERE id = ?",
            (time.time(), item_id),
        )
        conn.commit()

    def mark_failed(self, item_id: str, error: str):
        """
        [S1-3] 标记事件为失败，支持重试

        主要工作流：
        1. 获取当前重试次数和最大重试次数
        2. 如果重试次数未达上限，将状态重置为 pending（可重新处理）
        3. 如果已达上限，标记为 dead
        4. 记录错误信息
        """
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
        """
        [S1-1] 宕机恢复：将卡在 processing 状态的事件重置为 pending

        主要工作流：
        1. 查找所有状态为 processing 且更新时间早于 timeout 秒前的事件
        2. 将其状态重置为 pending，以便重新处理
        """
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
        """
        [S1-2] 定期清理：删除超过指定时间的已完成/死亡事件

        主要工作流：
        1. 计算截止时间（当前时间 - max_age）
        2. 删除所有状态为 done 或 dead 且更新时间早于截止时间的记录
        """
        conn = self._get_conn()
        cutoff = time.time() - max_age
        conn.execute(
            "DELETE FROM queue WHERE status IN ('done', 'dead') AND updated_at < ?",
            (cutoff,),
        )
        conn.commit()
