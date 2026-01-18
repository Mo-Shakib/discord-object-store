"""Upload workflow for Discord storage bot."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional

import discord
from tqdm import tqdm

from .config import Config
from .database import add_chunk, add_file, create_batch, get_batch, get_chunks, update_batch_status
from .discord_client import create_archive_card, create_thread, ensure_channels, setup_bot, upload_chunks_concurrent
from .encryption import derive_key, encrypt_file, generate_salt
from .file_processor import calculate_file_hash, create_archive, scan_path, split_file
from .system_integration import SleepInhibitor, send_notification
from .utils import StorageBotError, format_bytes, generate_batch_id


logger = logging.getLogger(__name__)


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _temp_dir(batch_id: str) -> Path:
    return _base_dir() / f"temp_{batch_id}"


def _chunk_index_from_path(path: Path) -> int:
    parts = path.name.split(".part")
    if len(parts) < 2:
        raise StorageBotError(f"Invalid chunk filename: {path.name}")
    return int(parts[-1])


def show_upload_summary(metadata: Dict[str, object]) -> None:
    """
    Display pre-upload summary.

    Args:
        metadata: Summary metadata.
    """
    print("\n📤 Upload preview")
    print(f"Path: {metadata['original_path']}")
    print(
        f"Files: {metadata['file_count']} "
        f"({format_bytes(metadata['total_size'])})"
    )
    print("Tip: add a title/tags so the Discord card is easier to scan.")


def prompt_optional_metadata() -> Dict[str, str]:
    """
    Prompt for optional title/tags/description.

    Returns:
        Metadata dictionary.
    """
    title = input("Title (optional, shown on Discord card): ").strip()
    tags_input = input("Tags (comma separated, optional): ").strip()
    description = input("Description (optional, short summary): ").strip()
    tags = ", ".join([tag.strip()
                     for tag in tags_input.split(",") if tag.strip()])
    return {
        "title": title,
        "tags": tags,
        "description": description,
    }


def _normalize_metadata(metadata: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not metadata:
        return {"title": "", "tags": "", "description": ""}
    title = (metadata.get("title") or "").strip()
    tags_input = (metadata.get("tags") or "").strip()
    description = (metadata.get("description") or "").strip()
    tags = ", ".join([tag.strip()
                     for tag in tags_input.split(",") if tag.strip()])
    return {
        "title": title,
        "tags": tags,
        "description": description,
    }


def cleanup_temp_files(temp_dir: Path) -> None:
    """
    Remove temporary directory.

    Args:
        temp_dir: Temporary directory to remove.
    """
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


async def _prepare_chunks(
    source_path: Path,
    batch_id: str,
    key: str,
    confirm: bool,
    metadata: Optional[Dict[str, str]],
) -> Dict[str, object]:
    if not source_path.exists():
        raise StorageBotError(f"Path not found: {source_path}")

    files = scan_path(source_path)
    total_size = sum(int(item["size"]) for item in files)
    file_count = len(files)

    summary = {
        "original_path": str(source_path),
        "original_name": source_path.name,
        "total_size": total_size,
        "file_count": file_count,
    }
    show_upload_summary(summary)
    meta_inputs = _normalize_metadata(metadata)
    if not metadata:
        meta_inputs = prompt_optional_metadata()
    if confirm:
        proceed = input("Continue with upload? [y/N]: ").strip().lower() == "y"
        if not proceed:
            raise StorageBotError("Upload cancelled by user.")

    temp_dir = _temp_dir(batch_id)
    temp_dir.mkdir(parents=True, exist_ok=True)
    archive_path = temp_dir / f"{source_path.name}.tar.gz"
    encrypted_path = temp_dir / f"{source_path.name}.tar.gz.enc"

    print("✓ Creating archive...")
    await asyncio.to_thread(create_archive, files, archive_path)
    print("✓ Encrypting archive...")
    await asyncio.to_thread(encrypt_file, archive_path, encrypted_path, key)
    print("✓ Splitting into chunks...")

    config = Config.get_instance()
    chunk_paths = await split_file(encrypted_path, config.max_chunk_size)

    chunk_hashes = []
    for chunk_path in chunk_paths:
        digest = await calculate_file_hash(chunk_path)
        chunk_hashes.append(digest)

    return {
        "files": files,
        "temp_dir": temp_dir,
        "archive_path": archive_path,
        "encrypted_path": encrypted_path,
        "chunk_paths": chunk_paths,
        "chunk_hashes": chunk_hashes,
        "summary": summary,
        "meta_inputs": meta_inputs,
    }


async def upload(
    path: str, confirm: bool = True, metadata: Optional[Dict[str, str]] = None
) -> str:
    """
    Upload a file or folder to Discord storage.

    Args:
        path: Path to file or folder.
        confirm: Require confirmation before upload.

    Returns:
        Batch ID.
    """
    source_path = Path(path).expanduser().resolve()
    batch_id = generate_batch_id()
    config = Config.get_instance()
    salt = generate_salt()
    key = derive_key(config.encryption_key, salt)

    sleep_inhibitor = SleepInhibitor()
    sleep_inhibitor.start()
    try:
        prepared = await _prepare_chunks(source_path, batch_id, key, confirm, metadata)
        chunk_paths = prepared["chunk_paths"]
        chunk_hashes = prepared["chunk_hashes"]
        temp_dir = prepared["temp_dir"]
        summary = prepared["summary"]
        meta_inputs = prepared["meta_inputs"]

        client = setup_bot(config.discord_bot_token)
        result_future: asyncio.Future[str] = asyncio.Future()

        @client.event
        async def on_ready() -> None:
            try:
                if not client.guilds:
                    raise StorageBotError("Bot is not connected to any guild.")
                guild = client.guilds[0]
                storage_channel, _, index_channel, _ = await ensure_channels(
                    guild,
                    config.storage_channel_name,
                    config.archive_channel_name,
                    config.batch_index_channel_name,
                    config.backup_channel_name,
                )
                storage_message = await storage_channel.send(f"📦 Batch `{batch_id}` chunks")
                thread = await create_thread(storage_message, f"Batch {batch_id}")
                archive_message = await create_archive_card(
                    index_channel,
                    {
                        "batch_id": batch_id,
                        "file_count": summary["file_count"],
                        "total_size": summary["total_size"],
                        "chunk_count": len(chunk_paths),
                        "title": meta_inputs["title"],
                        "tags": meta_inputs["tags"],
                        "description": meta_inputs["description"],
                        "upload_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                        "thread_id": str(thread.id),
                    },
                )

                batch_metadata = {
                    "batch_id": batch_id,
                    "original_path": str(source_path),
                    "original_name": summary["original_name"],
                    "total_size": summary["total_size"],
                    "compressed_size": prepared["archive_path"].stat().st_size,
                    "chunk_count": len(chunk_paths),
                    "file_count": summary["file_count"],
                    "encryption_salt": salt,
                    "is_directory": 1 if source_path.is_dir() else 0,
                    "title": meta_inputs["title"],
                    "tags": meta_inputs["tags"],
                    "description": meta_inputs["description"],
                    "status": "uploading",
                    "archive_message_id": str(archive_message.id),
                    "thread_id": str(thread.id),
                }
                create_batch(batch_metadata)

                await thread.send(f"🧾 META:{json.dumps(batch_metadata)}")

                for index, file_info in enumerate(prepared["files"]):
                    add_file(
                        {
                            "file_id": f"{batch_id}_{index}",
                            "batch_id": batch_id,
                            "relative_path": file_info["relative_path"],
                            "original_size": file_info["size"],
                            "modified_time": file_info.get("modified_time"),
                        }
                    )

                progress = tqdm(total=len(chunk_paths),
                                desc="Uploading", unit="chunk")

                def _progress(done: int, total: int) -> None:
                    progress.n = done
                    progress.total = total
                    progress.refresh()

                chunk_metadata = await upload_chunks_concurrent(
                    thread,
                    chunk_paths,
                    max_concurrency=config.concurrent_uploads,
                    progress_callback=_progress,
                )
                progress.close()

                for meta, file_hash in zip(chunk_metadata, chunk_hashes):
                    add_chunk(
                        {
                            **meta,
                            "batch_id": batch_id,
                            "file_hash": file_hash,
                        }
                    )

                update_batch_status(batch_id, "complete")
                cleanup_temp_files(temp_dir)
                result_future.set_result(batch_id)
            except Exception as exc:
                logger.exception("Upload failed")
                try:
                    update_batch_status(batch_id, "failed")
                except Exception:
                    logger.warning("Failed to update batch status to failed.")
                result_future.set_exception(exc)
            finally:
                await client.close()

        await client.start(config.discord_bot_token)
        result = await result_future
        send_notification("Upload complete", f"Batch {result} uploaded.")
        return result
    except Exception as exc:
        send_notification("Upload failed", f"Batch {batch_id} failed: {exc}")
        raise
    finally:
        sleep_inhibitor.stop()


async def resume_upload(batch_id: str) -> str:
    """
    Resume an interrupted upload.

    Args:
        batch_id: Batch identifier.

    Returns:
        Batch ID.
    """
    config = Config.get_instance()
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")
    if batch["status"] == "complete":
        return batch_id

    sleep_inhibitor = SleepInhibitor()
    sleep_inhibitor.start()
    try:
        temp_dir = _temp_dir(batch_id)
        if not temp_dir.exists():
            raise StorageBotError("Temporary data not found for resume.")

        chunk_paths = sorted(temp_dir.glob("*.part*"))
        indexed_paths = sorted(
            ((_chunk_index_from_path(path), path) for path in chunk_paths),
            key=lambda item: item[0],
        )
        uploaded = {chunk["chunk_index"] for chunk in get_chunks(batch_id)}
        remaining = [item for item in indexed_paths if item[0] not in uploaded]
        if not remaining:
            update_batch_status(batch_id, "complete")
            cleanup_temp_files(temp_dir)
            return batch_id

        client = setup_bot(config.discord_bot_token)
        result_future: asyncio.Future[str] = asyncio.Future()

        @client.event
        async def on_ready() -> None:
            try:
                thread_id = int(batch["thread_id"])
                thread = client.get_channel(thread_id)
                if thread is None:
                    thread = await client.fetch_channel(thread_id)
                if not isinstance(thread, discord.Thread):
                    raise StorageBotError("Thread not found for resume.")

                progress = tqdm(total=len(remaining),
                                desc="Resuming upload", unit="chunk")

                def _progress(done: int, total: int) -> None:
                    progress.n = done
                    progress.total = total
                    progress.refresh()

                chunk_metadata = await upload_chunks_concurrent(
                    thread,
                    remaining,
                    max_concurrency=config.concurrent_uploads,
                    progress_callback=_progress,
                )
                progress.close()

                for meta in chunk_metadata:
                    index = meta["chunk_index"]
                    path = dict(remaining).get(index)
                    file_hash = await calculate_file_hash(path) if path else ""
                    add_chunk(
                        {
                            **meta,
                            "batch_id": batch_id,
                            "file_hash": file_hash,
                        }
                    )

                update_batch_status(batch_id, "complete")
                cleanup_temp_files(temp_dir)
                result_future.set_result(batch_id)
            except Exception as exc:
                logger.exception("Resume upload failed")
                update_batch_status(batch_id, "failed")
                result_future.set_exception(exc)
            finally:
                await client.close()

        await client.start(config.discord_bot_token)
        result = await result_future
        send_notification("Upload complete",
                          f"Batch {result} resumed and uploaded.")
        return result
    except Exception as exc:
        send_notification("Upload failed", f"Batch {batch_id} failed: {exc}")
        raise
    finally:
        sleep_inhibitor.stop()
