"""Utility functions for Discord bot operations."""

import asyncio
import datetime
import os
import subprocess
from contextlib import contextmanager
from typing import Optional

import discord

from ..config import config
from ..common.utils import format_bytes, normalize_archive_id
from ..services.file_system import FileSystemService


async def get_log_channel(bot) -> Optional[discord.TextChannel]:
    """Get the log channel."""
    if not config.LOG_CHANNEL_ID:
        return None
    
    channel = bot.get_channel(config.LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(config.LOG_CHANNEL_ID)
        except Exception as e:
            print(f"⚠️ Could not fetch log channel {config.LOG_CHANNEL_ID}: {e}")
            return None
    return channel


async def get_archive_channel(bot) -> Optional[discord.TextChannel]:
    """Get the archive channel."""
    if not config.ARCHIVE_CHANNEL_ID:
        return None
    
    channel = bot.get_channel(config.ARCHIVE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(config.ARCHIVE_CHANNEL_ID)
        except Exception as e:
            print(f"⚠️ Could not fetch archive channel {config.ARCHIVE_CHANNEL_ID}: {e}")
            return None
    return channel


async def get_database_channel(bot) -> Optional[discord.TextChannel]:
    """Get the database channel."""
    if not config.DATABASE_CHANNEL_ID:
        return None
    
    channel = bot.get_channel(config.DATABASE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(config.DATABASE_CHANNEL_ID)
        except Exception as e:
            print(f"⚠️ Could not fetch database channel {config.DATABASE_CHANNEL_ID}: {e}")
            return None
    return channel


async def get_storage_channel(bot, ctx) -> Optional[discord.TextChannel]:
    """Get the storage channel."""
    if config.STORAGE_CHANNEL_ID:
        channel = bot.get_channel(config.STORAGE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(config.STORAGE_CHANNEL_ID)
            except Exception as e:
                print(f"⚠️ Could not fetch storage channel {config.STORAGE_CHANNEL_ID}: {e}")
                return None
        return channel
    return ctx.channel


def send_mac_notification(title: str, message: str):
    """Send a macOS system notification."""
    try:
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message}" with title "{title}"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


@contextmanager
def prevent_sleep(reason: str):
    """Context manager to prevent system sleep during operations."""
    proc = None
    try:
        proc = subprocess.Popen(
            ["caffeinate", "-dimsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        yield
    finally:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


async def download_latest_log_from_channel(bot):
    """Download the latest log backup from the log channel."""
    channel = await get_log_channel(bot)
    if channel is None:
        return
    
    target_name = os.path.basename(config.LOG_FILE)
    try:
        async for msg in channel.history(limit=50):
            for attachment in msg.attachments:
                if attachment.filename == target_name:
                    await attachment.save(config.LOG_FILE)
                    print(f"⬇️ Restored log from channel {config.LOG_CHANNEL_ID}: {target_name}")
                    return
        print(f"⚠️ No log backup found in channel {config.LOG_CHANNEL_ID}; using local copy.")
    except Exception as e:
        print(f"⚠️ Failed to download log backup: {e}")


async def upload_log_backup(bot):
    """Upload a log backup to the log channel."""
    if not os.path.exists(config.LOG_FILE):
        print(f"⚠️ Log file not found at {config.LOG_FILE}; skipping backup upload.")
        return
    
    channel = await get_log_channel(bot)
    if channel is None:
        return
    
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        await channel.send(
            content=f"🗂️ discord-drive-history.json backup @ {timestamp}",
            file=discord.File(config.LOG_FILE, filename=os.path.basename(config.LOG_FILE)),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(f"⬆️ Uploaded log backup to channel {config.LOG_CHANNEL_ID}.")
    except Exception as e:
        print(f"⚠️ Failed to upload log backup: {e}")


async def persist_logs(logs):
    """Persist logs to file and upload backup."""
    fs = FileSystemService()
    fs.write_logs(logs)
    # Note: we need to pass bot instance, so this should be called from cog methods


async def append_log(entry):
    """Append a log entry."""
    fs = FileSystemService()
    logs = fs.load_logs()
    logs.append(entry)
    fs.write_logs(logs)
    # Note: log backup upload should be called separately with bot instance


def build_database_entry_text(archive_id: str, timestamp: str, file_count: int, total_size_bytes: Optional[int]) -> str:
    """Build database entry text."""
    date_text = timestamp or "unknown"
    file_text = f"{file_count}" if isinstance(file_count, int) else "unknown"
    size_text = format_bytes(total_size_bytes) if total_size_bytes is not None else "Unknown size"
    return (
        "**📤 New archive uploaded**\n"
        "────────────────────────\n"
        f"📅 **Date:** {date_text}\n"
        f"🆔 **Archive ID:** `{archive_id}`\n"
        f"📄 **Files:** {file_text}\n"
        f"📦 **Total Size:** {size_text}"
    )


async def find_archive_card_by_id(bot, archive_id: str):
    """Find an archive card by ID."""
    from .ui.archive_card import parse_archive_card
    
    archive_channel = await get_archive_channel(bot)
    if archive_channel is None:
        return None
    
    target = normalize_archive_id(archive_id) or archive_id
    async for message in archive_channel.history(limit=500):
        metadata = parse_archive_card(message)
        if not metadata:
            continue
        candidate = normalize_archive_id(metadata.get("archive_id")) or metadata.get("archive_id")
        if candidate == target:
            return message
    
    return None


async def download_from_thread(thread, lot_dir: str, expected_total_files: Optional[int]):
    """Download files from a thread."""
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_files_known = 0
    
    async for msg in thread.history(limit=None, oldest_first=True):
        for attachment in msg.attachments:
            if expected_total_files is None:
                total_files_known += 1
            
            file_path = os.path.join(lot_dir, attachment.filename)
            if os.path.exists(file_path):
                skipped_count += 1
                total_files = expected_total_files if expected_total_files is not None else total_files_known
                left = max(total_files - (success_count + failed_count + skipped_count), 0)
                print(
                    f"📥 Downloaded {success_count}/{total_files} files "
                    f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
                )
                continue
            
            saved = False
            for attempt in range(3):
                try:
                    await attachment.save(file_path)
                    saved = True
                    success_count += 1
                    break
                except Exception as e:
                    print(f"❌ Failed to save {attachment.filename} (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(2 ** attempt)
            
            if not saved:
                failed_count += 1
            
            total_files = expected_total_files if expected_total_files is not None else total_files_known
            left = max(total_files - (success_count + failed_count + skipped_count), 0)
            print(
                f"📥 Downloaded {success_count}/{total_files} files "
                f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
            )
    
    final_total = expected_total_files if expected_total_files is not None else total_files_known
    return success_count, failed_count, skipped_count, final_total


async def reassemble_archive(lot_dir: str, archive_id: str, ctx=None):
    """Reassemble an archive from downloaded chunks."""
    from ..services.archive_manager import ArchiveManager
    
    if not lot_dir or not os.path.isdir(lot_dir):
        return
    
    try:
        print(f"🛠️ Reassembling archive {archive_id} from {lot_dir}...")
        if ctx:
            await ctx.send(f"🛠️ Reassembling {archive_id} locally...")
        await asyncio.to_thread(ArchiveManager.assemble_from_manifest, lot_dir)
        if ctx:
            await ctx.send(f"✅ Reassembly complete for {archive_id}.")
        print(f"✅ Reassembly complete for {archive_id}.")
    except Exception as e:
        print(f"⚠️ Reassembly failed for {archive_id}: {e}")
        if ctx:
            await ctx.send(f"⚠️ Reassembly failed for {archive_id}: {e}")
