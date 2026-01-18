"""File processing utilities: scanning, archiving, chunking."""

from __future__ import annotations

import asyncio
import tarfile
import time
import warnings
from pathlib import Path
from typing import Callable, Dict, List, Optional

import aiofiles

from .config import MAX_CHUNK_SIZE_CAP
from .utils import StorageBotError, get_io_buffer_size


ProgressCallback = Callable[[int, int, Optional[str]], None]
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}
IGNORED_DIRS = {"__MACOSX"}


def _report_progress(
    callback: Optional[ProgressCallback],
    current: int,
    total: int,
    name: Optional[str],
    last_report: float,
) -> float:
    if not callback:
        return last_report
    now = time.monotonic()
    if now - last_report >= 1 or current >= total:
        callback(current, total, name)
        return now
    return last_report


def _is_within_directory(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
        return True
    except ValueError:
        return False


def _safe_extract(archive: tarfile.TarFile, output_path: Path) -> None:
    base = output_path.resolve()
    for member in archive.getmembers():
        if member.islnk() or member.issym():
            raise StorageBotError(
                f"Blocked unsafe link in archive: {member.name}"
            )
        target_path = (output_path / member.name).resolve()
        if not _is_within_directory(base, target_path):
            raise StorageBotError(
                f"Blocked path traversal in archive: {member.name}"
            )
        archive.extract(member, output_path)


def scan_path(path: Path) -> List[Dict[str, object]]:
    """
    Recursively scan files and collect metadata.

    Args:
        path: File or directory to scan.

    Returns:
        List of file metadata dictionaries.
    """
    if not path.exists():
        raise StorageBotError(f"Path not found: {path}")

    base = path if path.is_dir() else path.parent
    files: List[Dict[str, object]] = []

    if path.is_file():
        stat = path.stat()
        files.append(
            {
                "path": path,
                "relative_path": path.name,
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
            }
        )
        return files

    for item in sorted(path.rglob("*")):
        if item.name in IGNORED_NAMES:
            continue
        if any(part in IGNORED_DIRS for part in item.parts):
            continue
        if item.is_symlink() or not item.is_file():
            continue
        stat = item.stat()
        files.append(
            {
                "path": item,
                "relative_path": str(item.relative_to(base)),
                "size": stat.st_size,
                "modified_time": stat.st_mtime,
            }
        )

    return files


def create_archive(file_list: List[Dict[str, object]], output_path: Path) -> None:
    """
    Create a gzip-compressed tar archive.

    Args:
        file_list: List of file metadata.
        output_path: Path to output archive.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output_path, "w:gz") as tar:
        for item in file_list:
            file_path = Path(item["path"])
            arcname = item["relative_path"]
            tar.add(file_path, arcname=arcname, recursive=False)


def extract_archive(archive_path: Path, output_path: Path) -> None:
    """
    Extract a gzip-compressed tar archive.

    Args:
        archive_path: Path to archive.
        output_path: Destination directory.
    """
    output_path.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        try:
            tar.extractall(output_path, filter="data")
        except TypeError:
            _safe_extract(tar, output_path)


async def split_file(
    file_path: Path,
    chunk_size: int,
    progress_callback: Optional[ProgressCallback] = None,
) -> List[Path]:
    """
    Split a file into chunks.

    Args:
        file_path: Path to file.
        chunk_size: Size per chunk in bytes.
        progress_callback: Optional progress callback.

    Returns:
        List of chunk paths.
    """
    if chunk_size <= 0:
        raise StorageBotError("Chunk size must be greater than 0.")
    if chunk_size > MAX_CHUNK_SIZE_CAP:
        warnings.warn(
            f"Chunk size capped at {MAX_CHUNK_SIZE_CAP} bytes (<10 MB).",
            RuntimeWarning,
        )
        chunk_size = MAX_CHUNK_SIZE_CAP

    total = file_path.stat().st_size
    processed = 0
    last_report = 0.0
    chunk_paths: List[Path] = []

    async with aiofiles.open(file_path, "rb") as infile:
        index = 0
        while True:
            chunk = await infile.read(chunk_size)
            if not chunk:
                break
            chunk_path = file_path.parent / f"{file_path.name}.part{index}"
            async with aiofiles.open(chunk_path, "wb") as outfile:
                await outfile.write(chunk)
            chunk_paths.append(chunk_path)
            processed += len(chunk)
            last_report = _report_progress(
                progress_callback, processed, total, str(file_path), last_report
            )
            index += 1

    return chunk_paths


async def merge_chunks(
    chunk_paths: List[Path],
    output_path: Path,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    Merge chunks into a single file.

    Args:
        chunk_paths: List of chunk paths.
        output_path: Destination file path.
        progress_callback: Optional progress callback.
    """
    total = sum(path.stat().st_size for path in chunk_paths)
    processed = 0
    last_report = 0.0

    buffer_size = get_io_buffer_size()
    async with aiofiles.open(output_path, "wb") as outfile:
        for chunk_path in chunk_paths:
            async with aiofiles.open(chunk_path, "rb") as infile:
                while True:
                    data = await infile.read(buffer_size)
                    if not data:
                        break
                    await outfile.write(data)
                    processed += len(data)
                    last_report = _report_progress(
                        progress_callback, processed, total, str(output_path), last_report
                    )


async def calculate_file_hash(
    file_path: Path, progress_callback: Optional[ProgressCallback] = None
) -> str:
    """
    Calculate SHA-256 hash for a file.

    Args:
        file_path: File path to hash.
        progress_callback: Optional progress callback.

    Returns:
        SHA-256 hex digest.
    """
    import hashlib

    total = file_path.stat().st_size
    processed = 0
    last_report = 0.0
    digest = hashlib.sha256()
    buffer_size = get_io_buffer_size()

    async with aiofiles.open(file_path, "rb") as infile:
        while True:
            chunk = await infile.read(buffer_size)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            last_report = _report_progress(
                progress_callback, processed, total, str(file_path), last_report
            )

    return digest.hexdigest()
