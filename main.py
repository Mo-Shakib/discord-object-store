"""Main entry point for Discord Object Store."""

import sys
import asyncio

from src.config import config
from src.bot.client import create_bot
from src.services.archive_manager import ArchiveManager


def run_bot():
    """Run the Discord bot."""
    print("🚀 Starting Discord Drive Bot...")
    
    bot = create_bot()
    
    # Load cogs
    async def load_cogs():
        await bot.load_extension("src.bot.cogs.upload")
        await bot.load_extension("src.bot.cogs.download")
        await bot.load_extension("src.bot.cogs.management")
        await bot.load_extension("src.bot.cogs.help")
    
    # Run bot
    async def main():
        async with bot:
            await load_cogs()
            await bot.start(config.DISCORD_BOT_TOKEN)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")


def run_slicer():
    """Run the CLI slicer tool."""
    print("--- Discord Secure Bulk Slicer & Assembler ---")
    print("1. Slice all files in a FOLDER (Generates Key)")
    print("2. Reassemble files from a CHUNKS folder (Requires Key)")
    
    choice = input("\nSelect an option (1 or 2): ").strip()
    
    if choice == '1':
        path = input("Enter path to the folder containing LARGE files: ").strip()
        ArchiveManager.slice_folder(path)
    elif choice == '2':
        path = input(
            "Enter path to the processed CHUNKS folder (manifest .json in name): "
        ).strip()
        ArchiveManager.assemble_from_manifest(path)
    else:
        print("Invalid selection.")


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        if command == "slice":
            run_slicer()
        elif command == "bot":
            run_bot()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python main.py [bot|slice]")
            sys.exit(1)
    else:
        # Default to bot
        run_bot()


if __name__ == "__main__":
    main()
