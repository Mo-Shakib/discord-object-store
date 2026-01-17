"""Utility functions used throughout the application."""

import datetime
import re
from typing import Any, Optional


def format_bytes(num_bytes: Optional[int]) -> str:
    """Convert bytes to human readable format."""
    if num_bytes is None:
        return "Unknown size"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num_bytes)} B"


def build_archive_id(lot_num: int, timestamp_str: Optional[str] = None) -> str:
    """Build an archive ID from lot number and timestamp."""
    if timestamp_str:
        try:
            dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            date_code = dt.strftime("%d%m%y")
        except ValueError:
            date_code = datetime.datetime.now().strftime("%d%m%y")
    else:
        date_code = datetime.datetime.now().strftime("%d%m%y")
    return f"#{date_code}-{int(lot_num):02d}"


def normalize_archive_id(archive_id: Optional[str]) -> Optional[str]:
    """Normalize an archive ID to standard format (#DDMMYY-01)."""
    if not archive_id:
        return None
    
    candidate = str(archive_id).strip()
    if candidate.startswith("#"):
        candidate = candidate[1:]
    
    match = re.match(r"^(\d{6})-(\d+)$", candidate)
    if not match:
        return None
    
    date_code, number = match.groups()
    return f"#{date_code}-{int(number):02d}"


def safe_str(value: Any) -> str:
    """Convert any value to a safe string representation."""
    if value is None:
        return "unknown"
    return str(value)


def clean_path(path_str: str) -> str:
    """Clean input paths from quotes and extra spaces."""
    import os
    cleaned = str(path_str).strip().strip("'").strip('"')
    cleaned = cleaned.replace("\\ ", " ")
    cleaned = os.path.expanduser(cleaned)
    return cleaned


def dedupe_paths(paths: list[str]) -> list[str]:
    """Remove duplicate paths while preserving order."""
    import os
    seen = set()
    unique_paths = []
    for path in paths:
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths
