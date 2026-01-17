"""Upload command cog."""

import asyncio
import datetime
import os
import time
from typing import Optional

import discord
from discord.ext import commands

from ...config import config
from ...common.utils import format_bytes, build_archive_id
from ...common.constants import (
    MAX_CONCURRENT_UPLOADS,
    ARCHIVE_CARD_UPDATE_RATE_LIMIT,
)
from ...services.file_system import FileSystemService
from ..ui.archive_card import create_archive_card, update_archive_card
from ..utils import (
    get_archive_channel,
    get_database_channel,
    append_log,
    send_mac_notification,
    prevent_sleep,
    build_database_entry_text,
)


class UploadCog(commands.Cog):
    """Cog for upload and resume commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.fs = FileSystemService()
    
    @commands.command()
    async def upload(self, ctx):
        """Upload files from the upload folder to Discord."""
        async def _run_upload():
            print(f"📤 Upload command received from {ctx.author} in {ctx.channel}.")
            lot_num = self.fs.get_next_lot()
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            archive_id = build_archive_id(lot_num, timestamp)
            
            archive_channel = await get_archive_channel(self.bot)
            if archive_channel is None:
                await ctx.send("⚠️ Archive channel unavailable. Upload aborted.")
                return
            
            files_to_upload = self.fs.list_upload_files()
            if not files_to_upload:
                print("⚠️ No files found to upload.")
                await ctx.send("⚠️ No files found in the upload folder.")
                return
            
            original_names = self.fs.read_manifest_original_names(config.UPLOAD_FOLDER)
            files_display = original_names if original_names else [
                os.path.basename(p) for p in files_to_upload
            ]
            total_size_bytes = self.fs.calculate_total_size(files_to_upload)
            chunk_count = len(files_to_upload)
            file_count = len(original_names) if original_names else None
            
            metadata = {
                "lot": lot_num,
                "archive_id": archive_id,
                "timestamp": timestamp,
                "status": "partial",
                "file_count": file_count,
                "total_size_bytes": total_size_bytes,
                "uploaded_files": [],
                "failed_files": [],
                "message_ids": [],
                "chunk_count": chunk_count,
                "files_display": files_display,
                "uploader": str(ctx.author),
                "archive_channel_id": config.ARCHIVE_CHANNEL_ID,
                "storage_channel_id": config.STORAGE_CHANNEL_ID,
            }
            
            archive_message = await create_archive_card(
                archive_channel, archive_id, metadata
            )
            try:
                thread = await archive_message.create_thread(
                    name=f"{archive_id} chunks",
                    auto_archive_duration=1440,
                )
            except Exception as e:
                await ctx.send(f"⚠️ Failed to create archive thread: {e}")
                return
            
            await ctx.send(
                f"📦 Archive card created: {archive_id}. Uploading {chunk_count} chunk(s) "
                f"({format_bytes(total_size_bytes)})..."
            )
            
            uploaded_message_ids = []
            uploaded_files = []
            failed_files = []
            errors = {}
            uploaded_bytes = 0
            last_edit = 0.0
            completed_count = 0
            upload_lock = asyncio.Lock()
            semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)
            
            async def upload_chunk(file_path):
                nonlocal uploaded_bytes, last_edit, completed_count
                file_name = os.path.basename(file_path)
                print(f"⬆️ Uploading file: {file_name}")
                async with semaphore:
                    try:
                        discord_file = discord.File(file_path)
                        msg = await thread.send(file=discord_file)
                        size_bytes = None
                        try:
                            size_bytes = os.path.getsize(file_path)
                        except OSError:
                            pass
                        try:
                            os.remove(file_path)
                            print(f"🗑️ Removed uploaded file: {file_name}")
                        except OSError as e:
                            print(f"⚠️ Could not delete {file_name} after upload: {e}")
                    except Exception as e:
                        async with upload_lock:
                            failed_files.append(file_name)
                            errors[file_name] = str(e)
                            completed_count += 1
                            now = time.monotonic()
                            if now - last_edit > ARCHIVE_CARD_UPDATE_RATE_LIMIT or completed_count == chunk_count:
                                metadata.update({
                                    "uploaded_files": uploaded_files,
                                    "failed_files": failed_files,
                                    "message_ids": uploaded_message_ids[:150],
                                    "thread_id": thread.id,
                                    "progress_text": self._build_progress_text(
                                        completed_count, chunk_count,
                                        uploaded_bytes, total_size_bytes,
                                    ),
                                })
                                try:
                                    await update_archive_card(archive_message, metadata)
                                    last_edit = now
                                except Exception as exc:
                                    print(f"⚠️ Failed to update archive card: {exc}")
                        print(f"❌ Failed to upload {file_name}: {e}")
                        return
                
                async with upload_lock:
                    uploaded_message_ids.append(msg.id)
                    uploaded_files.append(file_name)
                    if size_bytes is not None:
                        uploaded_bytes += size_bytes
                    completed_count += 1
                    now = time.monotonic()
                    if now - last_edit > ARCHIVE_CARD_UPDATE_RATE_LIMIT or completed_count == chunk_count:
                        metadata.update({
                            "uploaded_files": uploaded_files,
                            "failed_files": failed_files,
                            "message_ids": uploaded_message_ids[:150],
                            "thread_id": thread.id,
                            "progress_text": self._build_progress_text(
                                completed_count, chunk_count,
                                uploaded_bytes, total_size_bytes,
                            ),
                        })
                        try:
                            await update_archive_card(archive_message, metadata)
                            last_edit = now
                        except Exception as exc:
                            print(f"⚠️ Failed to update archive card: {exc}")
            
            print(f"📦 Uploading {chunk_count} file(s) to thread {thread.id}...")
            tasks = [upload_chunk(file_path) for file_path in files_to_upload]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            if failed_files:
                status = "partial" if uploaded_files else "failed"
            else:
                status = "success"
            
            metadata.update({
                "status": status,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "message_ids": uploaded_message_ids[:150],
                "thread_id": thread.id,
            })
            metadata.pop("progress_text", None)
            if errors:
                metadata["errors"] = errors
            
            try:
                await update_archive_card(archive_message, metadata)
            except Exception as e:
                print(f"⚠️ Failed to finalize archive card: {e}")
            
            entry = {
                "lot": lot_num,
                "archive_id": archive_id,
                "timestamp": timestamp,
                "message_ids": uploaded_message_ids,
                "status": status,
                "file_count": file_count,
                "total_size_bytes": total_size_bytes,
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "thread_id": thread.id,
                "archive_message_id": archive_message.id,
                "archive_channel_id": config.ARCHIVE_CHANNEL_ID,
                "storage_channel_id": config.STORAGE_CHANNEL_ID,
                "chunk_count": chunk_count,
            }
            if errors:
                entry["errors"] = errors
            
            await append_log(entry)
            send_mac_notification(
                "Discord Drive Upload Complete",
                f"{archive_id}: {status.upper()} • {len(uploaded_files)}/{chunk_count} uploaded",
            )
            
            if status == "success":
                print(f"✅ Upload complete for Archive {archive_id}.")
                database_channel = await get_database_channel(self.bot)
                if database_channel is not None:
                    try:
                        await database_channel.send(
                            build_database_entry_text(
                                archive_id, timestamp,
                                file_count or len(uploaded_files),
                                total_size_bytes,
                            )
                        )
                    except Exception as e:
                        print(f"⚠️ Failed to write database entry: {e}")
                try:
                    await archive_message.pin()
                except Exception:
                    pass
                await ctx.send(
                    f"✅ Archive {archive_id} uploaded successfully.\n"
                    f"🔒 Encryption: {'Enabled' if config.USER_KEY else 'Disabled'}\n"
                    f"📦 Chunks: {chunk_count} • Size: {format_bytes(total_size_bytes)}"
                )
            else:
                print(f"⚠️ Upload completed with errors for Archive {archive_id}.")
                await ctx.send(
                    f"⚠️ Archive {archive_id} uploaded with errors.\n"
                    f"✅ Uploaded: {len(uploaded_files)}/{chunk_count} • "
                    f"Size: {format_bytes(total_size_bytes)}\n"
                    "🔁 Use `!resume` to continue."
                )
        
        with prevent_sleep("upload"):
            await _run_upload()
    
    @commands.command()
    async def resume(self, ctx, archive_id: Optional[str] = None):
        """Resume a failed upload."""
        print(f"🔁 Resume command received from {ctx.author} in {ctx.channel}.")
        logs = self.fs.load_logs()
        if not logs:
            await ctx.send("⚠️ No log file found.")
            return
        
        target_index = None
        if archive_id:
            target_index = self.fs.find_log_index(logs, archive_id=archive_id)
            if target_index is None:
                await ctx.send(f"⚠️ Archive {archive_id} not found in logs.")
                return
        else:
            for i in range(len(logs) - 1, -1, -1):
                if logs[i].get("status") == "failed":
                    target_index = i
                    break
            if target_index is None:
                await ctx.send("✅ No failed uploads to resume.")
                return
        
        entry = logs[target_index]
        archive_id = self.fs.get_archive_id_from_entry(entry)
        file_names = entry.get("failed_files") or []
        if not file_names:
            file_names = [os.path.basename(p) for p in self.fs.list_upload_files()]
            print("⚠️ No failed_files list; falling back to current upload folder.")
        
        file_paths = []
        missing_files = []
        total_size_bytes = 0
        for name in file_names:
            path = name if os.path.isabs(name) else os.path.join(config.UPLOAD_FOLDER, name)
            if os.path.exists(path):
                file_paths.append(path)
                total_size_bytes += os.path.getsize(path)
            else:
                missing_files.append(name)
        
        if not file_paths:
            await ctx.send(f"⚠️ No files found to resume for Archive {archive_id}.")
            return
        
        await ctx.send(
            f"🔁 Resuming Archive {archive_id} with {len(file_paths)} file(s) "
            f"({format_bytes(total_size_bytes)})..."
        )
        
        from ..ui.archive_card import parse_archive_card
        from ..utils import find_archive_card_by_id
        
        uploaded_files = entry.get("uploaded_files", [])
        failed_files = []
        errors = entry.get("errors", {})
        message_ids = entry.get("message_ids", [])
        
        archive_message = await find_archive_card_by_id(self.bot, archive_id)
        archive_metadata = parse_archive_card(archive_message) if archive_message else None
        thread_id = (archive_metadata or {}).get("thread_id") or entry.get("thread_id")
        thread = None
        if thread_id:
            try:
                thread = await self.bot.fetch_channel(thread_id)
            except Exception as e:
                print(f"⚠️ Could not fetch thread {thread_id}: {e}")
        elif archive_message:
            try:
                thread = await archive_message.create_thread(
                    name=f"{archive_id} chunks",
                    auto_archive_duration=1440,
                )
            except Exception as e:
                print(f"⚠️ Failed to create thread for resume: {e}")
        
        target_channel = thread or ctx.channel
        
        for file_path in file_paths:
            file_name = os.path.basename(file_path)
            print(f"⬆️ Resuming upload: {file_name}")
            try:
                discord_file = discord.File(file_path)
                msg = await target_channel.send(file=discord_file)
                message_ids.append(msg.id)
                if file_name not in uploaded_files:
                    uploaded_files.append(file_name)
            except Exception as e:
                failed_files.append(file_name)
                errors[file_name] = str(e)
                print(f"❌ Failed to upload {file_name}: {e}")
        
        if missing_files:
            for name in missing_files:
                errors[name] = "file missing from upload folder"
            failed_files.extend(missing_files)
        
        entry["message_ids"] = message_ids
        entry["uploaded_files"] = uploaded_files
        entry["failed_files"] = failed_files
        if thread is not None:
            entry["thread_id"] = thread.id
        if errors:
            entry["errors"] = errors
        
        original_count = entry.get("file_count")
        if original_count is None:
            entry["file_count"] = len(set(uploaded_files + failed_files))
        
        if entry.get("total_size_bytes") is None:
            entry["total_size_bytes"] = total_size_bytes
        
        entry["status"] = "success" if not failed_files else "failed"
        logs[target_index] = entry
        
        from ..utils import persist_logs
        await persist_logs(logs)
        
        if archive_message:
            archive_metadata = archive_metadata or {}
            archive_metadata.update({
                "status": entry["status"],
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "message_ids": message_ids[:150],
                "thread_id": entry.get("thread_id"),
                "file_count": entry.get("file_count"),
                "total_size_bytes": entry.get("total_size_bytes"),
            })
            try:
                await update_archive_card(archive_message, archive_metadata)
            except Exception as e:
                print(f"⚠️ Failed to update archive card on resume: {e}")
        
        if entry["status"] == "success":
            database_channel = await get_database_channel(self.bot)
            if database_channel is not None:
                try:
                    await database_channel.send(
                        build_database_entry_text(
                            archive_id,
                            entry.get("timestamp"),
                            entry.get("file_count"),
                            entry.get("total_size_bytes"),
                        )
                    )
                except Exception as e:
                    print(f"⚠️ Failed to write database entry: {e}")
            await ctx.send(
                f"✅ Archive {archive_id} successfully completed.\n"
                f"📦 Files: {entry['file_count']} • "
                f"Size: {format_bytes(entry['total_size_bytes'])}"
            )
        else:
            await ctx.send(
                f"⚠️ Archive {archive_id} still has failed uploads.\n"
                f"✅ Uploaded: {len(uploaded_files)}/{entry['file_count']} • "
                f"Size: {format_bytes(entry['total_size_bytes'])}\n"
                "🔁 Run `!resume` again after fixing issues."
            )
    
    @staticmethod
    def _build_progress_text(current, total, uploaded_bytes=None, total_bytes=None):
        """Build progress text for upload status."""
        if total is None or total == 0:
            return f"Uploading... {current} chunks"
        progress = f"Uploading... {current}/{total} chunks"
        if uploaded_bytes is not None and total_bytes is not None:
            progress += f" ({format_bytes(uploaded_bytes)} / {format_bytes(total_bytes)})"
        return progress


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(UploadCog(bot))
