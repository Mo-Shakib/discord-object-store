"""Bot setup and event listeners."""

import discord
from discord.ext import commands

from ..config import config
from .utils import download_latest_log_from_channel, upload_log_backup
from .ui.archive_card import parse_archive_card
from ..services.file_system import FileSystemService


def create_bot():
    """Create and configure the Discord bot."""
    intents = discord.Intents.default()
    intents.message_content = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    bot.remove_command("help")
    
    @bot.event
    async def on_ready():
        """Called when the bot is ready."""
        print(f"🟢 Bot online as {bot.user.name} (ID: {bot.user.id})")
        
        # Try to rebuild log from archive channel
        rebuilt = await rebuild_log_from_archive_channel(bot)
        if not rebuilt:
            # Fall back to downloading latest log backup
            await download_latest_log_from_channel(bot)
        
        print("🤖 Ready and listening for commands.")
    
    @bot.event
    async def on_command_error(ctx, error):
        """Handle command errors."""
        if isinstance(error, commands.CommandNotFound):
            print(f"⚠️ Invalid command: {ctx.message.content}")
            await ctx.send(
                "⚠️ **Invalid command.**\n"
                "Use one of the commands below:\n\n"
                f"{_build_commands_markdown()}"
            )
            return
        print(f"❌ Command error: {error}")
        raise error
    
    return bot


async def rebuild_log_from_archive_channel(bot):
    """Rebuild log from archive channel."""
    from .utils import get_archive_channel
    from .cogs.management import ManagementCog
    
    archive_channel = await get_archive_channel(bot)
    if archive_channel is None:
        return False
    
    rebuilt_logs, warning = await ManagementCog.collect_logs_from_archive_channel(archive_channel)
    if warning:
        print(warning)
        return False
    
    if not rebuilt_logs:
        print("⚠️ No archive cards found; using local log.")
        return False
    
    fs = FileSystemService()
    fs.write_logs(rebuilt_logs)
    print(f"🧾 Rebuilt log from archive channel ({len(rebuilt_logs)} entries).")
    return True


def _build_commands_markdown():
    """Build commands markdown."""
    return (
        "### Available Commands\n"
        "- `!upload`\n"
        "- `!download #DDMMYY-01 [#DDMMYY-02]`\n"
        "- `!resume [archive_id]`\n"
        "- `!status`\n"
        "- `!history`\n"
        "- `!archives [query]`\n"
        "- `!verify <archive_id>`\n"
        "- `!rebuild-log`\n"
        "- `!migrate-legacy`\n"
        "- `!cleanup <archive_id>`\n"
        "- `!help`\n"
    )
