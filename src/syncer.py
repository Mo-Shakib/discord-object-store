"""Discord to SQLite sync utilities."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import discord

from .config import Config
from .database import DEFAULT_DB_PATH, add_chunk, create_batch, get_batch, init_database
from .discord_client import setup_bot
from .utils import StorageBotError


BATCH_ID_RE = re.compile(r"Batch ID:\s*`([^`]+)`")
THREAD_ID_RE = re.compile(r"Thread ID:\s*`([^`]+)`")
PART_RE = re.compile(r"\.part(\d+)$")


def _parse_attachment_index(filename: str, fallback: int) -> int:
    match = PART_RE.search(filename)
    if match:
        return int(match.group(1))
    return fallback


def _derive_original_name(filename: str) -> str:
    name = PART_RE.sub("", filename)
    if name.endswith(".tar.gz.enc"):
        name = name[: -len(".tar.gz.enc")]
    elif name.endswith(".enc"):
        name = name[: -len(".enc")]
    return name


async def _collect_thread_data(
    thread: discord.Thread,
) -> Tuple[Optional[Dict[str, Any]], List[Tuple[int, discord.Attachment, discord.Message]]]:
    meta: Optional[Dict[str, Any]] = None
    attachments: List[Tuple[int, discord.Attachment, discord.Message]] = []

    async for message in thread.history(limit=None, oldest_first=True):
        content = message.content.strip()
        if content.startswith("META:") or content.startswith("🧾 META:"):
            try:
                payload = content.split("META:", 1)[1].strip()
                meta = json.loads(payload)
            except json.JSONDecodeError:
                pass
        for attachment in message.attachments:
            index = _parse_attachment_index(
                attachment.filename, len(attachments))
            attachments.append((index, attachment, message))

    attachments.sort(key=lambda item: item[0])
    return meta, attachments


async def sync_from_discord(reset_db: bool = False) -> int:
    """
    Sync local database from Discord archive channel.

    Args:
        reset_db: If True, resets the local database before syncing.

    Returns:
        Number of batches synced.
    """
    config = Config.get_instance()
    if reset_db and DEFAULT_DB_PATH.exists():
        DEFAULT_DB_PATH.unlink()
    init_database()

    client = setup_bot(config.discord_bot_token)
    synced = 0
    done: asyncio.Future[int] = asyncio.Future()

    @client.event
    async def on_ready() -> None:
        nonlocal synced
        try:
            if not client.guilds:
                raise StorageBotError("Bot is not connected to any guild.")
            guild = client.guilds[0]
            index_channel = discord.utils.get(
                guild.text_channels, name=config.batch_index_channel_name
            )
            if index_channel is None:
                raise StorageBotError("Batch index channel not found.")

            async for message in index_channel.history(limit=None, oldest_first=True):
                match = BATCH_ID_RE.search(message.content or "")
                if not match:
                    continue
                batch_id = match.group(1)
                if get_batch(batch_id):
                    continue
                thread_id_match = THREAD_ID_RE.search(message.content or "")
                if not thread_id_match:
                    continue
                thread_id = int(thread_id_match.group(1))
                thread = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
                if not isinstance(thread, discord.Thread):
                    continue

                meta, attachments = await _collect_thread_data(thread)
                if not attachments:
                    continue

                first_attachment = attachments[0][1]
                original_name = (
                    meta.get("original_name")
                    if meta
                    else _derive_original_name(first_attachment.filename)
                )
                is_directory = int(meta.get("is_directory", 1)) if meta else 1
                total_size = int(meta.get("total_size", 0)) if meta else 0
                file_count = int(meta.get("file_count", 0)) if meta else 0
                chunk_count = len(attachments)
                compressed_size = sum(att.size for _, att, _ in attachments)
                encryption_salt = meta.get(
                    "encryption_salt", "") if meta else ""
                title = meta.get("title") if meta else None
                tags = meta.get("tags") if meta else None
                description = meta.get("description") if meta else None

                if total_size == 0:
                    total_size = compressed_size

                create_batch(
                    {
                        "batch_id": batch_id,
                        "original_path": original_name,
                        "original_name": original_name,
                        "total_size": total_size,
                        "compressed_size": compressed_size,
                        "chunk_count": chunk_count,
                        "file_count": file_count,
                        "encryption_salt": encryption_salt,
                        "is_directory": is_directory,
                        "title": title,
                        "tags": tags,
                        "description": description,
                        "status": "complete" if encryption_salt else "incomplete",
                        "archive_message_id": str(message.id),
                        "thread_id": str(thread.id),
                    }
                )

                for index, attachment, msg in attachments:
                    add_chunk(
                        {
                            "chunk_id": f"{thread.id}_{index}",
                            "batch_id": batch_id,
                            "chunk_index": index,
                            "discord_message_id": str(msg.id),
                            "discord_attachment_url": attachment.url,
                            "file_hash": "",
                            "size": attachment.size,
                        }
                    )

                synced += 1

            done.set_result(synced)
        except Exception as exc:
            done.set_exception(exc)
        finally:
            await client.close()

    await client.start(config.discord_bot_token)
    return await done
