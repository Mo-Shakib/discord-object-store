"""Discord client operations for storage bot."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import aiohttp
import aiofiles
import discord

from .utils import DownloadError, UploadError, format_bytes


logger = logging.getLogger(__name__)


def setup_bot(token: str) -> discord.Client:
    """
    Initialize a Discord client with required intents.

    Args:
        token: Discord bot token.

    Returns:
        Configured Discord client instance.
    """
    intents = discord.Intents(guilds=True, messages=True, message_content=True)
    client = discord.Client(intents=intents)
    return client


async def ensure_channels(
    guild: discord.Guild,
    storage_name: str,
    archive_name: str,
    index_name: str,
    backup_name: str,
) -> Tuple[discord.TextChannel, discord.TextChannel, discord.TextChannel, discord.TextChannel]:
    """
    Ensure storage and archive channels exist.

    Args:
        guild: Discord guild.
        storage_name: Storage channel name.
        archive_name: Archive channel name.

    Returns:
        Tuple of (storage_channel, archive_channel).
    """
    storage_channel = discord.utils.get(guild.text_channels, name=storage_name)
    archive_channel = discord.utils.get(guild.text_channels, name=archive_name)
    index_channel = discord.utils.get(guild.text_channels, name=index_name)
    backup_channel = discord.utils.get(guild.text_channels, name=backup_name)

    if storage_channel is None:
        storage_channel = await guild.create_text_channel(storage_name)
    if archive_channel is None:
        archive_channel = await guild.create_text_channel(archive_name)
    if index_channel is None:
        index_channel = await guild.create_text_channel(index_name)
    if backup_channel is None:
        backup_channel = await guild.create_text_channel(backup_name)

    return storage_channel, archive_channel, index_channel, backup_channel


async def create_archive_card(
    index_channel: discord.TextChannel, batch_metadata: Dict[str, Any]
) -> discord.Message:
    """
    Post archive summary message.

    Args:
        archive_channel: Channel to post in.
        batch_metadata: Batch metadata.

    Returns:
        Discord message created.
    """
    title = batch_metadata.get("title") or "Untitled Batch"
    tags = batch_metadata.get("tags") or "none"
    description = batch_metadata.get("description") or "No description"
    uploaded_at = batch_metadata.get("upload_date") or "just now"
    thread_id = batch_metadata.get("thread_id")

    def _truncate(value: str, limit: int = 1024) -> str:
        if len(value) <= limit:
            return value
        return value[: limit - 3] + "..."

    embed = discord.Embed(
        title="New Batch Uploaded",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Batch ID",
                    value=f"`{batch_metadata['batch_id']}`", inline=False)
    embed.add_field(name="Title", value=_truncate(title, 256), inline=True)
    embed.add_field(name="Tags", value=_truncate(tags, 256), inline=True)
    embed.add_field(name="Files", value=str(
        batch_metadata["file_count"]), inline=True)
    embed.add_field(
        name="Size", value=format_bytes(int(batch_metadata["total_size"])), inline=True
    )
    embed.add_field(name="Chunks", value=str(
        batch_metadata["chunk_count"]), inline=True)
    embed.add_field(name="Uploaded", value=uploaded_at, inline=True)
    embed.add_field(name="Description", value=_truncate(
        description), inline=False)
    if thread_id:
        embed.add_field(name="Thread", value=f"`{thread_id}`", inline=False)
    embed.set_footer(text="Discord Storage Bot")
    return await index_channel.send(content="📦 **New Batch Uploaded**", embed=embed)


async def create_thread(message: discord.Message, name: str) -> discord.Thread:
    """
    Create a thread under the given message.

    Args:
        message: Parent message.
        name: Thread name.

    Returns:
        Created thread.
    """
    return await message.create_thread(name=name, auto_archive_duration=1440)


async def upload_chunk(
    thread: discord.Thread, chunk_path: Path, index: int, retries: int = 3
) -> Dict[str, Any]:
    """
    Upload a single chunk to a Discord thread.

    Args:
        thread: Discord thread.
        chunk_path: Path to chunk file.
        index: Chunk index.
        retries: Number of retries.

    Returns:
        Chunk metadata dictionary.

    Raises:
        UploadError: If upload fails after retries.
    """
    delay = 1.0
    for attempt in range(1, retries + 1):
        try:
            message = await thread.send(file=discord.File(chunk_path))
            attachment = message.attachments[0]
            return {
                "chunk_id": f"{thread.id}_{index}",
                "chunk_index": index,
                "discord_message_id": str(message.id),
                "discord_attachment_url": attachment.url,
                "size": chunk_path.stat().st_size,
            }
        except discord.HTTPException as exc:
            logger.warning("Upload attempt %s failed: %s", attempt, exc)
            if attempt >= retries:
                raise UploadError(f"Failed to upload chunk {index}.") from exc
            await asyncio.sleep(delay)
            delay *= 2
        except Exception as exc:
            raise UploadError(
                f"Unexpected error uploading chunk {index}.") from exc
    raise UploadError(f"Failed to upload chunk {index}.")


async def upload_chunks_concurrent(
    thread: discord.Thread,
    chunk_paths: Iterable[Union[Path, Tuple[int, Path]]],
    max_concurrency: int = 5,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Dict[str, Any]]:
    """
    Upload chunks concurrently with a semaphore.

    Args:
        thread: Discord thread.
        chunk_paths: Iterable of chunk file paths.
        max_concurrency: Max concurrent uploads.

    Returns:
        List of chunk metadata.
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    results: List[Dict[str, Any]] = []

    paths: List[Tuple[int, Path]] = []
    for idx, item in enumerate(chunk_paths):
        if isinstance(item, tuple):
            paths.append((item[0], item[1]))
        else:
            paths.append((idx, item))
    total = len(paths)

    async def _upload(index: int, path: Path) -> None:
        async with semaphore:
            metadata = await upload_chunk(thread, path, index)
            results.append(metadata)
            if progress_callback:
                progress_callback(len(results), total)

    tasks = [asyncio.create_task(_upload(idx, path)) for idx, path in paths]
    await asyncio.gather(*tasks)
    return sorted(results, key=lambda item: item["chunk_index"])


async def download_chunk(
    session: aiohttp.ClientSession, url: str, output_path: Path
) -> None:
    """
    Download a single chunk to disk.

    Args:
        url: Attachment URL.
        output_path: Destination path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise DownloadError(f"Failed to download chunk: {resp.status}")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(output_path, "wb") as outfile:
                async for chunk in resp.content.iter_chunked(1024 * 1024):
                    await outfile.write(chunk)
    except Exception as exc:
        raise DownloadError("Download failed.") from exc


async def download_chunks_concurrent(
    chunk_data: Iterable[Dict[str, Any]],
    output_dir: Path,
    max_concurrency: int = 5,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Path]:
    """
    Download chunks concurrently with a semaphore.

    Args:
        chunk_data: Iterable of chunk metadata containing url and chunk_index.
        output_dir: Directory for downloads.
        max_concurrency: Max concurrent downloads.

    Returns:
        List of downloaded chunk paths.
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    results: Dict[int, Path] = {}

    items = list(chunk_data)
    total = len(items)

    async def _download(session: aiohttp.ClientSession, data: Dict[str, Any]) -> None:
        async with semaphore:
            chunk_path = output_dir / f"chunk_{data['chunk_index']}.bin"
            await download_chunk(session, data["discord_attachment_url"], chunk_path)
            results[data["chunk_index"]] = chunk_path
            if progress_callback:
                progress_callback(len(results), total)

    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.create_task(_download(session, item))
                 for item in items]
        await asyncio.gather(*tasks)
    return [results[index] for index in sorted(results.keys())]


async def delete_thread(client: discord.Client, thread_id: int) -> None:
    """
    Delete a thread and its messages.

    Args:
        client: Discord client.
        thread_id: Thread ID.
    """
    thread = client.get_channel(thread_id)
    if isinstance(thread, discord.Thread):
        await thread.delete()


async def upload_backup_file(
    client: discord.Client, channel_name: str, backup_path: Path
) -> None:
    """
    Upload a database backup file to a Discord channel.

    Args:
        client: Discord client.
        channel_name: Backup channel name.
        backup_path: Path to backup file.
    """
    if not client.guilds:
        raise UploadError("Bot is not connected to any guild.")
    guild = client.guilds[0]
    channel = discord.utils.get(guild.text_channels, name=channel_name)
    if channel is None:
        channel = await guild.create_text_channel(channel_name)
    await channel.send(
        content=f"🧾 DB Backup: `{backup_path.name}`",
        file=discord.File(backup_path),
    )
