"""Download command cog."""

import asyncio
import os
from typing import Optional

from discord.ext import commands

from ...config import config
from ...common.utils import format_bytes
from ...services.file_system import FileSystemService
from ..ui.archive_card import parse_archive_card
from ..utils import (
    get_storage_channel,
    find_archive_card_by_id,
    download_from_thread,
    reassemble_archive,
    prevent_sleep,
    send_mac_notification,
)


class DownloadCog(commands.Cog):
    """Cog for download command."""
    
    def __init__(self, bot):
        self.bot = bot
        self.fs = FileSystemService()
    
    @commands.command()
    async def download(self, ctx, start: str, end: Optional[str] = None):
        """Download archives from Discord."""
        async def _run_download():
            print(f"📥 Download command received from {ctx.author} in {ctx.channel}.")
            
            if not os.path.exists(config.LOG_FILE):
                print("❌ No log file found; cannot download.")
                await ctx.send("No log file found.")
                return
            
            logs = self.fs.load_logs()
            if not logs:
                from ..utils import get_archive_channel
                from .management import ManagementCog
                archive_channel = await get_archive_channel(self.bot)
                if archive_channel:
                    rebuilt_logs, _ = await ManagementCog.collect_logs_from_archive_channel(archive_channel)
                    if rebuilt_logs:
                        self.fs.write_logs(rebuilt_logs)
                        logs = rebuilt_logs
            
            lot_start, start_id, error = self._resolve_download_target(start, logs)
            if error:
                await ctx.send(f"⚠️ {error}\n\nUse `!help` for command usage.")
                return
            
            lot_end = None
            end_id = None
            if end is not None:
                lot_end, end_id, error = self._resolve_download_target(end, logs)
                if error:
                    await ctx.send(f"⚠️ {error}\n\nUse `!help` for command usage.")
                    return
            
            if lot_end is None:
                lot_end = lot_start
            
            if lot_start > lot_end:
                lot_start, lot_end = lot_end, lot_start
            
            start_label = start_id or self.fs.get_archive_id_by_lot(logs, lot_start)
            end_label = end_id or self.fs.get_archive_id_by_lot(logs, lot_end)
            
            # Filter logs for the requested range
            target_lots = []
            for entry in logs:
                lot_value = entry.get("lot")
                if lot_value is None:
                    continue
                try:
                    lot_number = int(lot_value)
                except (TypeError, ValueError):
                    continue
                if lot_start <= lot_number <= lot_end:
                    target_lots.append(entry)
            
            if not target_lots:
                print(f"⚠️ No data found for download range {lot_start}-{lot_end}.")
                await ctx.send("⚠️ No data found for the requested range.")
                return
            
            total_expected_files = sum(
                entry.get("file_count", 0) for entry in target_lots
                if isinstance(entry.get("file_count"), int)
            )
            total_expected_text = (
                f"{total_expected_files} files"
                if total_expected_files > 0
                else "unknown file count"
            )
            await ctx.send(
                f"📥 Starting download {start_label} to {end_label} "
                f"({len(target_lots)} archive(s), {total_expected_text})."
            )
            
            print(f"📦 Preparing download for {len(target_lots)} lot(s) into {config.DOWNLOAD_FOLDER}...")
            total_lots = len(target_lots)
            
            for index, lot_data in enumerate(target_lots, start=1):
                archive_id = self.fs.get_archive_id_from_entry(lot_data)
                print(f"⏳ Processing {index}/{total_lots} Lots (Archive {archive_id})...")
                
                archive_folder = f"[Archive] {archive_id}"
                lot_dir = os.path.join(config.DOWNLOAD_FOLDER, archive_folder)
                legacy_dir = os.path.join(config.DOWNLOAD_FOLDER, f"Lot_{lot_data['lot']}")
                
                if not os.path.exists(lot_dir) and os.path.exists(legacy_dir):
                    try:
                        os.rename(legacy_dir, lot_dir)
                    except OSError as e:
                        print(f"⚠️ Could not rename {legacy_dir} to {lot_dir}: {e}")
                
                os.makedirs(lot_dir, exist_ok=True)
                
                archive_message = await find_archive_card_by_id(self.bot, archive_id)
                archive_metadata = parse_archive_card(archive_message) if archive_message else None
                
                archive_size_bytes = (
                    (archive_metadata or {}).get("total_size_bytes")
                    if archive_metadata
                    else lot_data.get("total_size_bytes")
                )
                archive_size_text = format_bytes(archive_size_bytes) if archive_size_bytes is not None else "Unknown size"
                
                archive_file_count = (
                    (archive_metadata or {}).get("file_count")
                    if archive_metadata
                    else lot_data.get("file_count")
                )
                archive_file_text = (
                    f"{archive_file_count} files" if isinstance(archive_file_count, int)
                    else "Unknown file count"
                )
                
                await ctx.send(
                    f"📦 **Downloading Archive: {archive_id}**\n"
                    f"📄 {archive_file_text} • 📦 {archive_size_text}"
                )
                
                expected_total_files = (
                    (archive_metadata or {}).get("chunk_count")
                    or lot_data.get("chunk_count")
                    or lot_data.get("file_count")
                )
                
                thread_id = (
                    (archive_metadata or {}).get("thread_id")
                    if archive_metadata
                    else lot_data.get("thread_id")
                )
                
                if thread_id:
                    try:
                        thread = await self.bot.fetch_channel(thread_id)
                    except Exception as e:
                        print(f"⚠️ Could not fetch archive thread {thread_id}: {e}")
                        thread = None
                else:
                    thread = None
                
                if thread is not None:
                    success_count, failed_count, skipped_count, final_total = await download_from_thread(
                        thread, lot_dir, expected_total_files
                    )
                else:
                    # Legacy fallback
                    success_count, failed_count, skipped_count, final_total = await self._legacy_download(
                        ctx, lot_data, lot_dir, expected_total_files
                    )
                
                print(
                    f"✅ Archive {archive_id} complete "
                    f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • 📦 {final_total} total)"
                )
                
                if failed_count == 0:
                    await ctx.send(
                        f"✅ Archive {archive_id} downloaded successfully.\n"
                        f"📥 Downloaded: {success_count} • ⏭️ Skipped: {skipped_count} • 📦 Total: {final_total}"
                    )
                    if archive_message:
                        try:
                            await archive_message.add_reaction("📥")
                        except Exception:
                            pass
                    await reassemble_archive(lot_dir, archive_id, ctx)
                else:
                    await ctx.send(
                        f"⚠️ Archive {archive_id} downloaded with errors.\n"
                        f"✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • 📦 {final_total}\n"
                        "🔁 Re-run `!download` to resume."
                    )
            
            print(f"✅ Download complete for {start_label} to {end_label}.")
            await ctx.send(f"✅ Downloaded {start_label} to {end_label} to your local folder.")
            send_mac_notification(
                "Discord Drive Download Complete",
                f"{start_label} → {end_label} finished",
            )
        
        with prevent_sleep("download"):
            await _run_download()
    
    def _resolve_download_target(self, arg: str, logs: list):
        """Resolve a download target (archive ID or lot number)."""
        from ...common.utils import normalize_archive_id
        
        if arg is None:
            return None, None, None
        
        candidate = str(arg).strip()
        archive_id = normalize_archive_id(candidate)
        
        if archive_id:
            for entry in logs:
                entry_id = self.fs.get_archive_id_from_entry(entry)
                if entry_id == archive_id:
                    lot_value = entry.get("lot")
                    if lot_value is None:
                        return None, None, f"Archive {archive_id} has no lot number in logs."
                    return int(lot_value), archive_id, None
            return None, None, f"Archive {archive_id} not found in logs."
        
        if candidate.isdigit():
            return int(candidate), None, None
        
        return None, None, f"Invalid download target `{candidate}`. Use `#DDMMYY-01`."
    
    async def _legacy_download(self, ctx, lot_data: dict, lot_dir: str, expected_total_files: Optional[int]):
        """Legacy download method using message IDs."""
        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_files_known = 0
        
        storage_channel = await get_storage_channel(self.bot, ctx)
        if storage_channel is None:
            storage_channel = ctx.channel
        
        for msg_id in lot_data.get("message_ids", []):
            try:
                msg = await storage_channel.fetch_message(msg_id)
                if expected_total_files is None:
                    total_files_known += len(msg.attachments)
                
                for attachment in msg.attachments:
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
            except Exception as e:
                print(f"❌ Error downloading message {msg_id}: {e}")
        
        final_total = expected_total_files if expected_total_files is not None else total_files_known
        return success_count, failed_count, skipped_count, final_total


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(DownloadCog(bot))
