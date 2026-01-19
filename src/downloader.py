"""Download workflow for Discord storage bot."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import shutil
from pathlib import Path
from typing import Callable, Dict, List, Optional

import aiofiles
from tqdm import tqdm

from .config import Config
from .database import get_batch, get_chunks
from .discord_client import download_chunks_concurrent
from .encryption import decrypt_file, derive_key
from .file_processor import extract_archive, merge_chunks
from .utils import StorageBotError, format_bytes, get_io_buffer_size


logger = logging.getLogger(__name__)


def _temp_dir(batch_id: str) -> Path:
    base = Path(__file__).resolve().parents[1]
    temp = base / f"temp_download_{batch_id}"
    temp.mkdir(parents=True, exist_ok=True, mode=0o700)  # Owner-only permissions
    return temp


def show_download_summary(metadata: Dict[str, object]) -> None:
    """
    Display pre-download summary.

    Args:
        metadata: Summary metadata.
    """
    print("\n📥 Download preview")
    print(f"Name: {metadata['original_name']}")
    print(
        f"Size: {format_bytes(metadata['total_size'])} "
        f"({metadata['chunk_count']} chunks)"
    )


async def verify_chunk_async(path: Path, expected_hash: str) -> None:
    """
    Validate a single chunk integrity with SHA-256 hash (async).

    Args:
        path: Chunk file path.
        expected_hash: Expected hash.
    """
    buffer_size = get_io_buffer_size()
    digest = hashlib.sha256()
    
    async with aiofiles.open(path, "rb") as infile:
        while True:
            chunk = await infile.read(buffer_size)
            if not chunk:
                break
            digest.update(chunk)
    
    if not hmac.compare_digest(digest.hexdigest(), expected_hash):
        raise StorageBotError(f"Chunk integrity check failed: {path.name}")


async def verify_chunks_parallel(chunk_paths: List[Path], hashes: List[str]) -> None:
    """
    Validate chunk integrity with SHA-256 hashes in parallel.

    Args:
        chunk_paths: List of chunk file paths.
        hashes: Expected hashes.
    """
    await asyncio.gather(*[
        verify_chunk_async(path, expected_hash)
        for path, expected_hash in zip(chunk_paths, hashes)
    ])


async def download(batch_id: str, output_path: str, progress_callback: Optional[callable] = None) -> Path:
    """
    Download and restore a batch.

    Args:
        batch_id: Batch identifier.
        output_path: Destination directory.
        progress_callback: Optional callback(done, total) for download progress.

    Returns:
        Path to restored data.
    """
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")

    chunks = get_chunks(batch_id)
    if not chunks:
        raise StorageBotError("No chunks found for this batch.")

    summary = {
        "original_name": batch["original_name"],
        "total_size": batch["total_size"],
        "chunk_count": batch["chunk_count"],
    }
    show_download_summary(summary)
    
    # Show storage channel if available
    if batch.get("storage_channel_name"):
        print(f"Storage channel: #{batch['storage_channel_name']}")

    temp_dir = _temp_dir(batch_id)
    base_output = Path(output_path).expanduser().resolve()
    restore_dir = (
        base_output / batch["original_name"]
        if batch.get("is_directory")
        else base_output
    )
    print(f"Destination: {restore_dir}")
    encrypted_path = temp_dir / f"{batch['original_name']}.tar.gz.enc"
    archive_path = temp_dir / f"{batch['original_name']}.tar.gz"

    progress = tqdm(total=len(chunks), desc="Downloading", unit="chunk")

    def _progress(done: int, total: int) -> None:
        progress.n = done
        progress.total = total
        progress.refresh()
        # Call API progress callback if provided
        if progress_callback:
            progress_callback(done, total)

    try:
        chunk_paths = await download_chunks_concurrent(
            chunks,
            temp_dir,
            max_concurrency=Config.get_instance().concurrent_downloads,
            progress_callback=_progress,
        )
        progress.close()

        print("✓ Verifying integrity...")
        # Parallel verification for better performance
        await verify_chunks_parallel(chunk_paths, [chunk["file_hash"] for chunk in chunks])

        print("✓ Merging chunks...")
        await merge_chunks(chunk_paths, encrypted_path)

        if not batch.get("encryption_salt"):
            raise StorageBotError(
                "Missing encryption metadata in local database. "
                "Sync from Discord is incomplete for this batch."
            )
        print("✓ Decrypting archive...")
        key = derive_key(Config.get_instance().encryption_key,
                         batch["encryption_salt"])
        await decrypt_file(encrypted_path, archive_path, key)

        print("✓ Extracting files...")
        await asyncio.to_thread(extract_archive, archive_path, restore_dir)
    except Exception:
        await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
        raise

    await asyncio.to_thread(shutil.rmtree, temp_dir, ignore_errors=True)
    return restore_dir
