"""Download workflow for Discord storage bot."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Dict, List

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
    return base / f"temp_download_{batch_id}"


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


def verify_chunks(chunk_paths: List[Path], hashes: List[str]) -> None:
    """
    Validate chunk integrity with SHA-256 hashes.

    Args:
        chunk_paths: List of chunk file paths.
        hashes: Expected hashes.
    """
    import hashlib
    import hmac

    buffer_size = get_io_buffer_size()
    for path, expected in zip(chunk_paths, hashes):
        digest = hashlib.sha256()
        with open(path, "rb") as infile:
            while True:
                chunk = infile.read(buffer_size)
                if not chunk:
                    break
                digest.update(chunk)
        if not hmac.compare_digest(digest.hexdigest(), expected):
            raise StorageBotError(f"Chunk integrity check failed: {path.name}")


async def download(batch_id: str, output_path: str) -> Path:
    """
    Download and restore a batch.

    Args:
        batch_id: Batch identifier.
        output_path: Destination directory.

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

    temp_dir = _temp_dir(batch_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
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

    try:
        chunk_paths = await download_chunks_concurrent(
            chunks,
            temp_dir,
            max_concurrency=Config.get_instance().concurrent_downloads,
            progress_callback=_progress,
        )
        progress.close()

        print("✓ Verifying integrity...")
        verify_chunks(chunk_paths, [chunk["file_hash"] for chunk in chunks])

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
        await asyncio.to_thread(decrypt_file, encrypted_path, archive_path, key)

        print("✓ Extracting files...")
        await asyncio.to_thread(extract_archive, archive_path, restore_dir)
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    shutil.rmtree(temp_dir, ignore_errors=True)
    return restore_dir
