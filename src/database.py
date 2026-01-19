"""SQLite database operations for Discord storage bot."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from queue import Queue
from threading import Lock
from typing import Any, Dict, Iterator, List, Optional

from .utils import DatabaseError

logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "storage.db"
_POOL_LOCK = Lock()
_POOLS: Dict[Path, "ConnectionPool"] = {}


class ConnectionPool:
    """Simple SQLite connection pool with hard limit."""

    def __init__(self, db_path: Path, maxsize: int = 5) -> None:
        self.db_path = db_path
        self.maxsize = maxsize
        self._queue: Queue[sqlite3.Connection] = Queue(maxsize=maxsize)
        self._active_count: int = 0
        self._count_lock = Lock()

    def acquire(self) -> sqlite3.Connection:
        try:
            return self._queue.get_nowait()
        except Exception:
            with self._count_lock:
                if self._active_count >= self.maxsize:
                    # Block until a connection is available
                    return self._queue.get(block=True, timeout=30)
                self._active_count += 1
            return self._create_connection()

    def release(self, conn: sqlite3.Connection) -> None:
        try:
            self._queue.put_nowait(conn)
        except Exception:
            with self._count_lock:
                self._active_count -= 1
            conn.close()

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn


def _get_pool(db_path: Path) -> ConnectionPool:
    with _POOL_LOCK:
        if db_path not in _POOLS:
            _POOLS[db_path] = ConnectionPool(db_path)
        return _POOLS[db_path]


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """
    Get a pooled database connection with transaction management.

    Args:
        db_path: Optional path override for database file.
    """
    path = db_path or DEFAULT_DB_PATH
    pool = _get_pool(path)
    conn = pool.acquire()
    try:
        conn.execute("BEGIN")
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(str(exc)) from exc
    finally:
        pool.release(conn)


def init_database(db_path: Optional[Path] = None) -> None:
    """
    Initialize the SQLite database schema.

    Args:
        db_path: Optional path override for database file.
    """
    path = db_path or DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if database exists and is readable
    if path.exists():
        try:
            import os
            if not os.access(path, os.R_OK | os.W_OK):
                raise DatabaseError(f"Database file exists but is not readable/writable: {path}")
        except Exception as e:
            if not isinstance(e, DatabaseError):
                raise DatabaseError(f"Error accessing database file: {e}")
    schema = """
    CREATE TABLE IF NOT EXISTS batches (
        batch_id TEXT PRIMARY KEY,
        original_path TEXT NOT NULL,
        original_name TEXT NOT NULL,
        total_size INTEGER NOT NULL,
        compressed_size INTEGER NOT NULL,
        chunk_count INTEGER NOT NULL,
        file_count INTEGER NOT NULL,
        encryption_salt TEXT NOT NULL,
        is_directory INTEGER DEFAULT 1,
        title TEXT,
        tags TEXT,
        description TEXT,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'complete',
        archive_message_id TEXT,
        thread_id TEXT,
        storage_channel_id TEXT,
        storage_channel_name TEXT
    );

    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        chunk_index INTEGER NOT NULL,
        discord_message_id TEXT NOT NULL,
        discord_attachment_url TEXT NOT NULL,
        file_hash TEXT NOT NULL,
        size INTEGER NOT NULL,
        upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS files (
        file_id TEXT PRIMARY KEY,
        batch_id TEXT NOT NULL,
        relative_path TEXT NOT NULL,
        original_size INTEGER NOT NULL,
        modified_time REAL,
        FOREIGN KEY (batch_id) REFERENCES batches(batch_id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_batch_id ON chunks(batch_id);
    CREATE INDEX IF NOT EXISTS idx_chunk_index ON chunks(batch_id, chunk_index);
    CREATE INDEX IF NOT EXISTS idx_file_batch ON files(batch_id);
    """

    # Migration columns (hardcoded constant for security)
    MIGRATION_COLUMNS = ("title", "tags", "description", "storage_channel_id", "storage_channel_name")

    with get_connection(path) as conn:
        conn.executescript(schema)
        try:
            conn.execute(
                "ALTER TABLE batches ADD COLUMN is_directory INTEGER DEFAULT 1")
        except sqlite3.Error:
            pass
        for column in MIGRATION_COLUMNS:
            try:
                # Safe: column is from hardcoded constant
                conn.execute(f"ALTER TABLE batches ADD COLUMN {column} TEXT")
            except sqlite3.Error:
                pass


def create_batch(metadata: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """
    Insert a new batch record.

    Args:
        metadata: Batch metadata.
        db_path: Optional path override for database file.
    """
    query = """
    INSERT INTO batches (
        batch_id, original_path, original_name, total_size, compressed_size,
        chunk_count, file_count, encryption_salt, is_directory, title, tags,
        description, status, archive_message_id, thread_id, storage_channel_id,
        storage_channel_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        metadata["batch_id"],
        metadata["original_path"],
        metadata["original_name"],
        metadata["total_size"],
        metadata["compressed_size"],
        metadata["chunk_count"],
        metadata["file_count"],
        metadata["encryption_salt"],
        metadata.get("is_directory", 1),
        metadata.get("title"),
        metadata.get("tags"),
        metadata.get("description"),
        metadata.get("status", "complete"),
        metadata.get("archive_message_id"),
        metadata.get("thread_id"),
        metadata.get("storage_channel_id"),
        metadata.get("storage_channel_name"),
    )
    with get_connection(db_path) as conn:
        conn.execute(query, values)


def add_chunk(chunk_data: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """
    Insert a chunk record.

    Args:
        chunk_data: Chunk metadata.
        db_path: Optional path override for database file.
    """
    query = """
    INSERT INTO chunks (
        chunk_id, batch_id, chunk_index, discord_message_id,
        discord_attachment_url, file_hash, size
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    values = (
        chunk_data["chunk_id"],
        chunk_data["batch_id"],
        chunk_data["chunk_index"],
        chunk_data["discord_message_id"],
        chunk_data["discord_attachment_url"],
        chunk_data["file_hash"],
        chunk_data["size"],
    )
    with get_connection(db_path) as conn:
        conn.execute(query, values)


def add_file(file_data: Dict[str, Any], db_path: Optional[Path] = None) -> None:
    """
    Insert a file record.

    Args:
        file_data: File metadata.
        db_path: Optional path override for database file.
    """
    query = """
    INSERT INTO files (
        file_id, batch_id, relative_path, original_size, modified_time
    ) VALUES (?, ?, ?, ?, ?)
    """
    values = (
        file_data["file_id"],
        file_data["batch_id"],
        file_data["relative_path"],
        file_data["original_size"],
        file_data.get("modified_time"),
    )
    with get_connection(db_path) as conn:
        conn.execute(query, values)


def get_batch(batch_id: str, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve batch metadata.

    Args:
        batch_id: Batch identifier.
        db_path: Optional path override for database file.

    Returns:
        Batch metadata dict or None.
    """
    query = "SELECT * FROM batches WHERE batch_id = ?"
    with get_connection(db_path) as conn:
        row = conn.execute(query, (batch_id,)).fetchone()
    return dict(row) if row else None


def get_chunks(batch_id: str, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Retrieve chunks for a batch.

    Args:
        batch_id: Batch identifier.
        db_path: Optional path override for database file.

    Returns:
        List of chunk metadata dicts.
    """
    query = "SELECT * FROM chunks WHERE batch_id = ? ORDER BY chunk_index"
    with get_connection(db_path) as conn:
        rows = conn.execute(query, (batch_id,)).fetchall()
    return [dict(row) for row in rows]


def update_batch_status(batch_id: str, status: str, db_path: Optional[Path] = None) -> None:
    """
    Update batch status.

    Args:
        batch_id: Batch identifier.
        status: New status value.
        db_path: Optional path override for database file.
    """
    query = "UPDATE batches SET status = ? WHERE batch_id = ?"
    with get_connection(db_path) as conn:
        conn.execute(query, (status, batch_id))


def delete_batch(batch_id: str, db_path: Optional[Path] = None) -> None:
    """
    Delete a batch and associated chunks.

    Args:
        batch_id: Batch identifier.
        db_path: Optional path override for database file.
    """
    query = "DELETE FROM batches WHERE batch_id = ?"
    with get_connection(db_path) as conn:
        conn.execute(query, (batch_id,))


def list_batches(db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    List all batches with summary info.

    Args:
        db_path: Optional path override for database file.

    Returns:
        List of batch summaries.
    """
    query = """
    SELECT batch_id, original_name, title, tags, description,
           total_size, compressed_size, chunk_count, file_count,
           upload_date, status, storage_channel_id, storage_channel_name
    FROM batches
    ORDER BY upload_date DESC
    """
    with get_connection(db_path) as conn:
        rows = conn.execute(query).fetchall()
    return [dict(row) for row in rows]


def get_storage_stats(db_path: Optional[Path] = None) -> Dict[str, int]:
    """
    Calculate storage statistics.

    Args:
        db_path: Optional path override for database file.

    Returns:
        Stats dictionary.
    """
    query = """
    SELECT COUNT(*) AS batch_count,
           COALESCE(SUM(total_size), 0) AS total_size,
           COALESCE(SUM(compressed_size), 0) AS compressed_size,
           COALESCE(SUM(chunk_count), 0) AS chunk_count
    FROM batches
    """
    with get_connection(db_path) as conn:
        row = conn.execute(query).fetchone()
    return dict(row) if row else {"batch_count": 0, "total_size": 0, "compressed_size": 0, "chunk_count": 0}
