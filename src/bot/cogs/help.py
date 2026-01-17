"""Help command cog."""

from discord.ext import commands

from ...config import config


class HelpCog(commands.Cog):
    """Cog for help command."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="help")
    async def help_command(self, ctx):
        """Show help message."""
        help_text = self._build_help_text()
        await ctx.send(help_text)
    
    @staticmethod
    def _build_help_text():
        """Build help text."""
        return (
            "## Discord Drive Bot Help\n"
            "\n"
            "**Overview**\n"
            "- Uploads files from your local upload folder to Discord as an archive.\n"
            "- Tracks every archive in `lot_history.json` for download and resume.\n"
            "\n"
            "**Folders**\n"
            f"- Uploads: `{config.UPLOAD_FOLDER}`\n"
            f"- Downloads: `{config.DOWNLOAD_FOLDER}`\n"
            "\n"
            "**Commands**\n"
            "- `!upload` — Create a new archive and upload all `.bin` files plus `*-manifest_*.json`.\n"
            "- `!download #DDMMYY-01 [#DDMMYY-02]` — Download a single archive or a range.\n"
            "- `!resume [archive_id]` — Resume the most recent failed archive, or a specific archive ID.\n"
            "- `!status` — Show bot status, queue size, and last archive info.\n"
            "- `!history` — Show the 5 most recent archives.\n"
            "- `!archives [query]` — List recent archives or search by ID/filename.\n"
            "- `!verify <archive_id>` — Verify archive thread chunks.\n"
            "- `!rebuild-log` — Rebuild local log from archive channel (admin).\n"
            "- `!migrate-legacy` — Migrate legacy logs to archive cards (admin).\n"
            "- `!cleanup <archive_id>` — Remove thread and mark archive deleted (admin).\n"
            "- `!help` — Show this help message.\n"
            "\n"
            "**Archive ID format**\n"
            "- `#DDMMYY-01` (example: `#120225-07`).\n"
            "\n"
            "**Tips**\n"
            "- If an upload fails, fix the issue and run `!resume`.\n"
            "- Downloads are resumable: re-run `!download` and existing files will be skipped.\n"
            "- Keep `DISCORD_BOT_TOKEN` in your `.env` file.\n"
        )


async def setup(bot):
    """Setup function for loading the cog."""
    await bot.add_cog(HelpCog(bot))
