"""Shared utilities for the Discord storage bot."""

from __future__ import annotations

import logging
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


class StorageBotError(Exception):
    """Base exception for storage bot errors."""


class ConfigError(StorageBotError):
    """Raised when configuration is invalid or missing."""


class EncryptionError(StorageBotError):
    """Raised when encryption or decryption fails."""


class UploadError(StorageBotError):
    """Raised when uploads fail."""


class DownloadError(StorageBotError):
    """Raised when downloads fail."""


class DatabaseError(StorageBotError):
    """Raised when database operations fail."""


DEFAULT_IO_BUFFER_SIZE = 8 * 1024 * 1024


def setup_logging(log_level: int = logging.INFO) -> None:
    """
    Configure global logging.

    Args:
        log_level: Logging verbosity level.
    """
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )


def format_bytes(size: int) -> str:
    """
    Convert bytes to a human-readable string.

    Args:
        size: Size in bytes.

    Returns:
        Human-readable size string.
    """
    if size < 0:
        raise ValueError("Size must be non-negative.")

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"


def format_duration(seconds: float) -> str:
    """
    Convert seconds to a human-readable duration string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable duration string.
    """
    if seconds < 0:
        raise ValueError("Duration must be non-negative.")

    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def generate_batch_id(prefix: str = "BATCH") -> str:
    """
    Generate a unique batch ID.

    Args:
        prefix: Optional prefix for the batch ID.

    Returns:
        Unique batch identifier.
    """
    date_str = datetime.now().strftime("%Y%m%d")
    token = secrets.token_hex(2).upper()
    return f"{prefix}_{date_str}_{token}"


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to remove unsafe characters.

    Args:
        name: Original filename.

    Returns:
        Sanitized filename.
    """
    name = name.strip().replace(os.sep, "_").replace("/", "_")
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "file"


def get_io_buffer_size() -> int:
    """
    Read the IO buffer size from the environment.

    Returns:
        Buffer size in bytes.
    """
    value = os.getenv("IO_BUFFER_SIZE", "").strip()
    if not value:
        return DEFAULT_IO_BUFFER_SIZE
    try:
        parsed = int(value)
    except ValueError:
        return DEFAULT_IO_BUFFER_SIZE
    if parsed <= 0:
        return DEFAULT_IO_BUFFER_SIZE
    return parsed


def create_temp_dir(prefix: str = "temp_") -> Path:
    """
    Create a temporary directory.

    Args:
        prefix: Directory prefix.

    Returns:
        Path to the created temporary directory.
    """
    return Path(tempfile.mkdtemp(prefix=prefix))


def atomic_write(path: Path, data: str, mode: str = "w") -> None:
    """
    Write data atomically to a file.

    Args:
        path: Destination path.
        data: Data to write.
        mode: File mode.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    with open(temp_path, mode, encoding="utf-8") as file_handle:
        file_handle.write(data)
        file_handle.flush()
        os.fsync(file_handle.fileno())
    temp_path.replace(path)
