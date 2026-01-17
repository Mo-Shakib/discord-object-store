"""Management commands cog."""

import os
from typing import Optional

from discord.ext import commands

from ...config import config
from ...common.utils import format_bytes, normalize_archive_id
from ...services.file_system import FileSystemService
from ..ui.archive_card import (
    parse_archive_card,
    search_archives,
    create_archive_card,
    update_archive_card,
)
from ..utils import (
    get_archive_channel,
    get_storage_channel,
    get_database_channel,
    find_archive_card_by_id,
    build_database_entry_text,
)


class ManagementCog(commands.Cog):
    """Cog for management commands."""
    
    def __init__(self, bot):
        self.bot = bot
        self.fs = FileSystemService()
    
    @commands.command()
    async def status(self, ctx):
        """Show bot status."""
        drive_ok = os.path.exists('/Volumes/Local Drive')
        upload_files = self.fs.list_upload_files()
        upload_total_size = self.fs.calculate_total_size(upload_files)
        logs = self.fs.load_logs()
        failed_count = len([l for l in logs if l.get("status") == "failed"])
        last_entry = logs[-1] if logs else None
        last_archive = self.fs.get_archive_id_from_entry(last_entry) if last_entry else "none"
        last_status = last_entry.get("status") if last_entry else "n/a"
        encryption_enabled = "✅ Enabled" if config.USER_KEY else "❌ Disabled (USER_KEY not set)"
        
        await ctx.send(
            "📊 **Bot Status**\n"
            f"💾 Drive: {'✅ Ready' if drive_ok else '❌ Missing'}\n"
            f"🔒 Encryption: {encryption_enabled}\n"
            f"📤 Upload queue: {len(upload_files)} file(s) • {format_bytes(upload_total_size)}\n"
            f"📚 Logs: {len(logs)} entries • ❗ Failed: {failed_count}\n"
            f"🗂️ Last Archive: {last_archive} • Status: {last_status}"
        )
    
    @commands.command()
    async def history(self, ctx):
        """Show recent archive history."""
        logs = self.fs.load_logs()
        if not logs:
            await ctx.send("📭 No history found yet.")
            return
        
        recent = logs[-5:]
        lines = ["📜 **Recent Archives**"]
        for entry in recent:
            archive_id = self.fs.get_archive_id_from_entry(entry)
            status = entry.get("status", "unknown")
            file_count = entry.get("file_count")
            if file_count is None:
                uploaded = entry.get("uploaded_files", [])
                failed = entry.get("failed_files", [])
                file_count = len(set(uploaded + failed)) if (uploaded or failed) else "?"
            total_size_bytes = entry.get("total_size_bytes")
            size_text = format_bytes(total_size_bytes) if total_size_bytes is not None else "Unknown size"
            timestamp = entry.get("timestamp", "unknown time")
            status_emoji = "✅" if status == "success" else ("⚠️" if status == "failed" else "❔")
            lines.append(
                f"{status_emoji} {archive_id} • {file_count} files • {size_text} • {timestamp}"
            )
        
        await ctx.send("\n".join(lines))
    
    @commands.command()
    async def archives(self, ctx, *, query: Optional[str] = None):
        """List or search archives."""
        archive_channel = await get_archive_channel(self.bot)
        if archive_channel is None:
            await ctx.send("⚠️ Archive channel unavailable.")
            return
        
        messages = await search_archives(archive_channel, query)
        if not messages:
            await ctx.send("📭 No archives found.")
            return
        
        lines = ["📚 **Archives**"]
        for message in messages:
            metadata = parse_archive_card(message) or {}
            archive_id = metadata.get("archive_id") or "unknown"
            size_text = (
                format_bytes(metadata.get("total_size_bytes"))
                if metadata.get("total_size_bytes") is not None
                else "Unknown size"
            )
            status = metadata.get("status") or "unknown"
            lines.append(f"{archive_id} • {size_text} • {status}")
        
        await ctx.send("\n".join(lines))
    
    @commands.command()
    async def verify(self, ctx, archive_id: str):
        """Verify archive thread chunks."""
        archive_message = await find_archive_card_by_id(self.bot, archive_id)
        if archive_message is None:
            await ctx.send(f"⚠️ Archive {archive_id} not found.")
            return
        
        metadata = parse_archive_card(archive_message) or {}
        thread_id = metadata.get("thread_id")
        if not thread_id:
            await ctx.send(f"⚠️ Archive {archive_id} has no thread metadata.")
            return
        
        try:
            thread = await self.bot.fetch_channel(thread_id)
        except Exception as e:
            await ctx.send(f"⚠️ Could not fetch archive thread: {e}")
            return
        
        attachment_names = set()
        async for msg in thread.history(limit=None, oldest_first=True):
            for attachment in msg.attachments:
                attachment_names.add(attachment.filename)
        
        uploaded_files = metadata.get("uploaded_files")
        expected_files: list[str] = uploaded_files if isinstance(uploaded_files, list) else []
        missing_files = [name for name in expected_files if name not in attachment_names]
        chunk_count = metadata.get("chunk_count")
        
        if missing_files:
            await ctx.send(
                f"⚠️ Archive {archive_id} missing {len(missing_files)} chunk(s).\n"
                + "\n".join(missing_files[:20])
            )
            return
        
        if isinstance(chunk_count, int) and len(attachment_names) != chunk_count:
            await ctx.send(
                f"⚠️ Archive {archive_id} chunk count mismatch. "
                f"Expected {chunk_count}, found {len(attachment_names)}."
            )
            return
        
        await ctx.send(f"✅ Archive {archive_id} verified. {len(attachment_names)} chunks present.")
    
    @commands.command(name="rebuild-log")
    async def rebuild_log_command(self, ctx, confirm: Optional[str] = None):
        """Rebuild local log from archive channel (admin only)."""
        if not self._is_admin(ctx):
            await ctx.send("⛔ Admin permissions required.")
            return
        
        archive_channel = await get_archive_channel(self.bot)
        new_logs, warning = await self.collect_logs_from_archive_channel(archive_channel)
        if warning:
            await ctx.send(warning)
            return
        
        old_logs = self.fs.load_logs()
        if confirm != "confirm":
            await ctx.send(
                f"🧾 Rebuild preview: local {len(old_logs)} entries, "
                f"archive channel {len(new_logs)} entries.\n"
                "Run `!rebuild-log confirm` to overwrite the local log."
            )
            return
        
        self.fs.write_logs(new_logs)
        await ctx.send(f"✅ Rebuilt local log from archive channel ({len(new_logs)} entries).")
    
    @commands.command(name="migrate-legacy")
    async def migrate_legacy_command(self, ctx):
        """Migrate legacy logs to archive cards (admin only)."""
        if not self._is_admin(ctx):
            await ctx.send("⛔ Admin permissions required.")
            return
        
        migrated = await self._migrate_legacy_archives(ctx)
        if migrated:
            await ctx.send("✅ Legacy archives migrated to archive cards and threads.")
        else:
            await ctx.send("⚠️ No legacy archives migrated.")
    
    @commands.command()
    async def cleanup(self, ctx, archive_id: str):
        """Remove thread and mark archive deleted (admin only)."""
        if not self._is_admin(ctx):
            await ctx.send("⛔ Admin permissions required.")
            return
        
        archive_message = await find_archive_card_by_id(self.bot, archive_id)
        if archive_message is None:
            await ctx.send(f"⚠️ Archive {archive_id} not found.")
            return
        
        metadata = parse_archive_card(archive_message) or {}
        thread_id = metadata.get("thread_id")
        if thread_id:
            try:
                thread = await self.bot.fetch_channel(thread_id)
                await thread.delete()
            except Exception as e:
                await ctx.send(f"⚠️ Could not delete archive thread: {e}")
                return
        
        metadata["status"] = "deleted"
        try:
            await update_archive_card(archive_message, metadata)
        except Exception as e:
            print(f"⚠️ Failed to update archive card: {e}")
        
        logs = self.fs.load_logs()
        logs = [
            entry for entry in logs
            if normalize_archive_id(entry.get("archive_id")) != normalize_archive_id(archive_id)
        ]
        self.fs.write_logs(logs)
        await ctx.send(f"🗑️ Archive {archive_id} cleaned up.")
    
    @staticmethod
    def _is_admin(ctx):
        """Check if user is admin."""
        perms = getattr(ctx.author, "guild_permissions", None)
        if not perms:
            return False
        return perms.administrator or perms.manage_guild
    
    @staticmethod
    async def collect_logs_from_archive_channel(channel):
        """Collect logs from archive channel."""
        if channel is None:
            return [], "⚠️ Archive channel unavailable; using local log."
        
        rebuilt_logs = []
        seen_keys = {}
        
        async for message in channel.history(limit=None):
            metadata = parse_archive_card(message)
            if not metadata:
                continue
            
            archive_id = normalize_archive_id(metadata.get("archive_id")) or metadata.get("archive_id")
            if not archive_id:
                continue
            
            lot = metadata.get("lot")
            entry = {
                "lot": lot,
                "archive_id": archive_id,
                "timestamp": metadata.get("timestamp"),
                "message_ids": metadata.get("message_ids", []),
                "status": metadata.get("status") or "unknown",
                "file_count": metadata.get("file_count"),
                "total_size_bytes": metadata.get("total_size_bytes"),
                "uploaded_files": metadata.get("uploaded_files", []),
                "failed_files": metadata.get("failed_files", []),
                "thread_id": metadata.get("thread_id"),
                "archive_message_id": metadata.get("archive_message_id", message.id),
                "archive_channel_id": config.ARCHIVE_CHANNEL_ID,
                "storage_channel_id": metadata.get("storage_channel_id"),
                "chunk_count": metadata.get("chunk_count"),
            }
            
            key = archive_id
            existing = seen_keys.get(key)
            if existing:
                existing["entry"].update(entry)
                continue
            
            rebuilt_logs.append(entry)
            seen_keys[key] = {"entry": entry}
        
        return rebuilt_logs, None
    
    async def _migrate_legacy_archives(self, ctx):
        """Migrate legacy archives to archive cards."""
        archive_channel = await get_archive_channel(self.bot)
        if archive_channel is None:
            print("⚠️ Archive channel unavailable; migration skipped.")
            return False
        
        logs = self.fs.load_logs()
        if not logs:
            print("⚠️ No logs found for migration.")
            return False
        
        storage_channel = await get_storage_channel(self.bot, ctx) if ctx else None
        updated = False
        
        for entry in logs:
            if entry.get("archive_message_id"):
                continue
            
            archive_id = self.fs.get_archive_id_from_entry(entry)
            metadata = {
                "lot": entry.get("lot"),
                "archive_id": archive_id,
                "timestamp": entry.get("timestamp"),
                "status": entry.get("status") or "unknown",
                "file_count": entry.get("file_count"),
                "total_size_bytes": entry.get("total_size_bytes"),
                "uploaded_files": entry.get("uploaded_files", []),
                "failed_files": entry.get("failed_files", []),
                "message_ids": [],
                "chunk_count": entry.get("chunk_count") or entry.get("file_count"),
                "files_display": entry.get("uploaded_files", []),
                "uploader": "Legacy Import",
                "archive_channel_id": config.ARCHIVE_CHANNEL_ID,
                "storage_channel_id": config.STORAGE_CHANNEL_ID,
                "legacy": True,
            }
            
            archive_message = await create_archive_card(archive_channel, archive_id, metadata)
            try:
                thread = await archive_message.create_thread(
                    name=f"{archive_id} legacy",
                    auto_archive_duration=1440,
                )
            except Exception as e:
                print(f"⚠️ Failed to create legacy thread for {archive_id}: {e}")
                continue
            
            legacy_message_ids = entry.get("message_ids", [])
            migrated_ids = []
            if storage_channel and legacy_message_ids:
                for msg_id in legacy_message_ids:
                    try:
                        msg = await storage_channel.fetch_message(msg_id)
                    except Exception as e:
                        print(f"⚠️ Could not fetch legacy message {msg_id}: {e}")
                        continue
                    
                    for attachment in msg.attachments:
                        try:
                            file_obj = await attachment.to_file()
                            migrated = await thread.send(file=file_obj)
                            migrated_ids.append(migrated.id)
                        except Exception as e:
                            print(f"⚠️ Failed to migrate attachment {attachment.filename}: {e}")
            
            metadata.update({"thread_id": thread.id, "message_ids": migrated_ids[:150]})
            try:
                await update_archive_card(archive_message, metadata)
            except Exception as e:
                print(f"⚠️ Failed to update legacy archive card: {e}")
            
            entry["archive_message_id"] = archive_message.id
            entry["thread_id"] = thread.id
            if migrated_ids:
                entry["message_ids"] = migrated_ids
            updated = True
        
        if updated:
            self.fs.write_logs(logs)
        return updated


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(ManagementCog(bot))
