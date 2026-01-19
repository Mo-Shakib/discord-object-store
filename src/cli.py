"""Command-line interface for Discord storage bot."""

from __future__ import annotations

import argparse
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from colorama import Fore, Style, init as colorama_init
import discord

from .config import Config
from .database import (
    DEFAULT_DB_PATH,
    delete_batch,
    get_batch,
    get_chunks,
    get_storage_stats,
    init_database,
    list_batches,
)
from .discord_client import download_chunks_concurrent, setup_bot, upload_backup_file
from .file_processor import calculate_file_hash
from .uploader import resume_upload, upload
from .downloader import download
from .utils import StorageBotError, format_bytes
from .syncer import sync_from_discord
import aiohttp
import aiofiles


def _cli_header() -> str:
    return (
        "\n"
        f"{Fore.CYAN}"
        "██████╗ ███████╗██████╗ ██████╗  ██████╗ ██████╗ ██████╗\n"
        "██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔════╝██╔═══██╗██╔══██╗\n"
        "██████╔╝█████╗  ██████╔╝██████╔╝██║     ██║   ██║██████╔╝\n"
        "██╔═══╝ ██╔══╝  ██╔══██╗██╔══██╗██║     ██║   ██║██╔══██╗\n"
        "██║     ███████╗██║  ██║██║  ██║╚██████╗╚██████╔╝██║  ██║\n"
        "╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝  ╚═╝\n"
        f"{Style.RESET_ALL}"
        f"{Fore.WHITE}Discord Storage Bot — secure, encrypted storage on Discord.{Style.RESET_ALL}\n"
        f"{Fore.BLUE}Developer: Shakib | GitHub: https://github.com/Mo-Shakib/{Style.RESET_ALL}\n"
    )


def _command_showcase() -> List[Tuple[str, str, str]]:
    return [
        ("upload <path>", "Upload a file/folder", "Archive & encrypt files."),
        ("download <batch_id> <path>", "Download batch", "Restore files locally."),
        ("list", "List batches", "View stored batches."),
        ("info <batch_id>", "Batch details", "Inspect batch metadata."),
        ("delete <batch_id>", "Delete metadata", "Remove local + optional remote."),
        ("stats", "Storage statistics", "Quick usage summary."),
        ("channels", "List storage channels", "Show channel distribution."),
        ("verify <batch_id>", "Verify integrity", "Re-hash chunks and compare."),
        ("resume <batch_id>", "Resume upload", "Continue interrupted upload."),
        ("backup", "Backup database", "Create/upload DB backup."),
        ("restore [--backup-file]", "Restore database", "Download DB from Discord."),
        ("sync [--reset]", "Sync from Discord", "Rebuild DB from messages."),
    ]


def _print_command_help(title: str) -> None:
    print(_cli_header())
    print(title)
    print("Usage: python bot.py <command> [options]")
    print("\nAvailable commands:\n")
    for command, label, usecase in _command_showcase():
        print(f"  {command:<26} - {label} ({usecase})")
    print("\nExamples:")
    print("  python bot.py upload ./my-folder")
    print("  python bot.py download BATCH_20240101_ABCD ./downloads")
    print("  python bot.py restore                    # Restore latest backup from Discord")
    print("  python bot.py sync --reset               # Rebuild database from messages")
    print("")


class _FriendlyArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        _print_command_help(f"{Fore.RED}Error:{Style.RESET_ALL} {message}")
        print(f"{Fore.YELLOW}Tip:{Style.RESET_ALL} Run `python bot.py help` for examples.")
        raise SystemExit(2)


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = _FriendlyArgumentParser(description="Discord Storage Bot CLI")
    subparsers = parser.add_subparsers(dest="command")

    upload_parser = subparsers.add_parser("upload", help="Upload file/folder")
    upload_parser.add_argument("path", help="Path to file or folder")
    upload_parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    upload_parser.add_argument("--channel", type=str, help="Specific storage channel to use (default: auto round-robin)")

    download_parser = subparsers.add_parser("download", help="Download batch")
    download_parser.add_argument("batch_id", help="Batch ID")
    download_parser.add_argument("path", help="Destination path")

    subparsers.add_parser("list", help="List all batches")

    info_parser = subparsers.add_parser("info", help="Batch details")
    info_parser.add_argument("batch_id", help="Batch ID")

    delete_parser = subparsers.add_parser("delete", help="Delete batch metadata")
    delete_parser.add_argument("batch_id", help="Batch ID")

    subparsers.add_parser("stats", help="Storage statistics")
    
    subparsers.add_parser("channels", help="List storage channels and their usage")

    verify_parser = subparsers.add_parser("verify", help="Verify batch integrity")
    verify_parser.add_argument("batch_id", help="Batch ID")

    resume_parser = subparsers.add_parser("resume", help="Resume interrupted upload")
    resume_parser.add_argument("batch_id", help="Batch ID")

    subparsers.add_parser("backup", help="Backup database")

    sync_parser = subparsers.add_parser("sync", help="Sync database from Discord")
    sync_parser.add_argument(
        "--reset", action="store_true", help="Reset local database before syncing"
    )

    restore_parser = subparsers.add_parser("restore", help="Restore database from Discord backup")
    restore_parser.add_argument(
        "--backup-file", type=str, help="Specific backup filename to restore (default: latest)"
    )

    subparsers.add_parser("help", help="Show help and usage examples")

    return parser.parse_args()


def command_upload(args: argparse.Namespace) -> None:
    """
    Handle upload command.
    """
    # Show available channels if user wants to choose
    if hasattr(args, 'channel') and args.channel:
        channel_name = args.channel
    else:
        # Optionally show available channels
        config = Config.get_instance()
        available_channels = config.get_storage_channels()
        
        if len(available_channels) > 1 and not args.yes:
            print(f"\n{Fore.CYAN}Available Storage Channels:{Style.RESET_ALL}")
            print(f"  {'0.':<4} {'Auto (Round-robin)':<30} {Fore.YELLOW}[Default]{Style.RESET_ALL}")
            for i, channel in enumerate(available_channels, 1):
                print(f"  {f'{i}.':<4} #{channel}")
            
            choice = input(f"\n{Fore.CYAN}Select channel (0-{len(available_channels)}, Enter for auto):{Style.RESET_ALL} ").strip()
            
            if choice and choice.isdigit():
                choice_num = int(choice)
                if 1 <= choice_num <= len(available_channels):
                    channel_name = available_channels[choice_num - 1]
                    print(f"✓ Selected: #{channel_name}")
                else:
                    channel_name = None
                    print(f"✓ Using auto selection (round-robin)")
            else:
                channel_name = None
                print(f"✓ Using auto selection (round-robin)")
        else:
            channel_name = None
    
    batch_id = asyncio.run(upload(args.path, confirm=not args.yes, channel=channel_name))
    print(f"{Fore.GREEN}✅ Upload complete! Batch ID: {batch_id}{Style.RESET_ALL}")


def command_download(args: argparse.Namespace) -> None:
    """
    Handle download command.
    """
    restored_path = asyncio.run(download(args.batch_id, args.path))
    print(f"{Fore.GREEN}✅ Restored to: {restored_path}{Style.RESET_ALL}")


def command_list(_: argparse.Namespace) -> None:
    """
    Handle list command.
    """
    batches = list_batches()
    if not batches:
        print("No batches found. Upload something with `python bot.py upload <path>`.")
        return
    print(f"{Fore.CYAN}Stored batches:{Style.RESET_ALL}")
    print(f"{'Batch ID':<24}  {'Name':<32}  {'Size':>12}  {'Status':<10}")
    print("-" * 84)
    for batch in batches:
        name = batch["original_name"]
        if len(name) > 32:
            name = f"{name[:29]}..."
        print(
            f"{batch['batch_id']:<24}  {name:<32}  "
            f"{format_bytes(batch['total_size']):>12}  {batch['status']:<10}"
        )


def command_info(args: argparse.Namespace) -> None:
    """
    Handle info command.
    """
    batch = get_batch(args.batch_id)
    if not batch:
        print("Batch not found. Double-check the batch ID with `python bot.py list`.")
        return
    chunks = get_chunks(args.batch_id)
    print(f"{Fore.CYAN}Batch details{Style.RESET_ALL}")
    print(f"Batch ID: {batch['batch_id']}")
    print(f"Name: {batch['original_name']}")
    print(f"Files: {batch['file_count']}")
    print(f"Size: {format_bytes(batch['total_size'])}")
    print(f"Chunks: {len(chunks)}")
    print(f"Status: {batch['status']}")


def command_delete(args: argparse.Namespace) -> None:
    """
    Handle delete command.
    """
    confirm = input(
        "Delete local metadata for this batch? [y/N]: "
    ).strip().lower()
    if confirm != "y":
        print("Delete cancelled.")
        return
    delete_remote = (
        input("Also delete files from Discord? [y/N]: ").strip().lower() == "y"
    )
    if delete_remote:
        asyncio.run(_delete_from_discord(args.batch_id))
    delete_batch(args.batch_id)
    print(f"{Fore.YELLOW}Deleted batch metadata.{Style.RESET_ALL}")


def command_stats(_: argparse.Namespace) -> None:
    """
    Handle stats command.
    """
    stats = get_storage_stats()
    print(f"{Fore.CYAN}📊 Discord Storage Bot Stats{Style.RESET_ALL}")
    print("=" * 32)
    print(f"Total batches: {stats['batch_count']}")
    print(f"Total size: {format_bytes(stats['total_size'])}")
    print(f"Compressed size: {format_bytes(stats['compressed_size'])}")
    print(f"Total chunks: {stats['chunk_count']}")


def command_channels(_: argparse.Namespace) -> None:
    """
    Handle channels command - show storage channel usage.
    """
    from collections import defaultdict
    
    # Get configured channels
    config = Config.get_instance()
    configured_channels = config.get_storage_channels()
    
    print(f"{Fore.CYAN}📡 Storage Channels{Style.RESET_ALL}")
    print("=" * 60)
    print(f"\n{Fore.YELLOW}Configured Channels:{Style.RESET_ALL}")
    for i, channel in enumerate(configured_channels, 1):
        print(f"  {i}. #{channel}")
    
    # Get usage statistics from database
    batches = list_batches()
    channel_stats = defaultdict(lambda: {"count": 0, "size": 0})
    no_channel_count = 0
    
    for batch in batches:
        channel_name = batch.get("storage_channel_name") or "unknown"
        if channel_name == "unknown":
            no_channel_count += 1
        channel_stats[channel_name]["count"] += 1
        channel_stats[channel_name]["size"] += batch.get("total_size", 0)
    
    if channel_stats:
        print(f"\n{Fore.YELLOW}Channel Usage:{Style.RESET_ALL}")
        print(f"{'Channel':<30}  {'Batches':>10}  {'Total Size':>15}")
        print("-" * 60)
        
        for channel, stats in sorted(channel_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            color = Fore.GREEN if channel in configured_channels else Fore.RED
            print(f"{color}#{channel:<29}{Style.RESET_ALL}  {stats['count']:>10}  {format_bytes(stats['size']):>15}")
        
        if no_channel_count > 0:
            print(f"\n{Fore.YELLOW}Note: {no_channel_count} batch(es) don't have channel info (uploaded before multi-channel support).{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.YELLOW}No batches found.{Style.RESET_ALL}")
    
    print(f"\n{Fore.CYAN}Tip:{Style.RESET_ALL} To add more storage channels, edit STORAGE_CHANNEL_NAME in .env")
    print(f"      Use comma-separated values: STORAGE_CHANNEL_NAME=channel1,channel2,channel3")


async def _verify_batch(batch_id: str) -> None:
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")
    chunks = get_chunks(batch_id)
    if not chunks:
        raise StorageBotError("No chunks found for batch.")

    temp_dir = Path(__file__).resolve().parents[1] / f"temp_verify_{batch_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    def _progress(done: int, total: int) -> None:
        print(f"Downloaded {done}/{total} chunks", end="\r")

    await download_chunks_concurrent(
        chunks,
        temp_dir,
        max_concurrency=Config.get_instance().concurrent_downloads,
        progress_callback=_progress,
    )
    print("")

    for chunk in chunks:
        path = temp_dir / f"chunk_{chunk['chunk_index']}.bin"
        digest = await calculate_file_hash(path)
        if digest != chunk["file_hash"]:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise StorageBotError(f"Integrity check failed for chunk {chunk['chunk_index']}")

    shutil.rmtree(temp_dir, ignore_errors=True)


def command_verify(args: argparse.Namespace) -> None:
    """
    Handle verify command.
    """
    asyncio.run(_verify_batch(args.batch_id))
    print(f"{Fore.GREEN}✅ Integrity verified.{Style.RESET_ALL}")


def command_resume(args: argparse.Namespace) -> None:
    """
    Handle resume command.
    """
    batch_id = asyncio.run(resume_upload(args.batch_id))
    print(f"{Fore.GREEN}✅ Upload resumed. Batch ID: {batch_id}{Style.RESET_ALL}")


def command_backup(_: argparse.Namespace) -> None:
    """
    Handle backup command.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DEFAULT_DB_PATH.with_name(f"storage_backup_{timestamp}.db")
    shutil.copy2(DEFAULT_DB_PATH, backup_path)
    print(f"{Fore.GREEN}✅ Backup created: {backup_path}{Style.RESET_ALL}")
    upload_choice = input("Upload backup to Discord now? [y/N]: ").strip().lower()
    if upload_choice == "y":
        asyncio.run(_upload_backup_to_discord(backup_path))
        print(f"{Fore.GREEN}✅ Backup uploaded to Discord.{Style.RESET_ALL}")


def command_sync(args: argparse.Namespace) -> None:
    """
    Handle sync command.
    """
    if args.reset:
        confirm = input(
            "This will reset the local DB before syncing. Continue? [y/N]: "
        ).strip().lower()
        if confirm != "y":
            print("Sync cancelled.")
            return
    count = asyncio.run(sync_from_discord(reset_db=args.reset))
    print(f"{Fore.GREEN}✅ Synced {count} batches from Discord.{Style.RESET_ALL}")


def command_restore(args: argparse.Namespace) -> None:
    """
    Handle restore command.
    """
    print(f"{Fore.YELLOW}⚠️  This will replace your local database with a backup from Discord.{Style.RESET_ALL}")
    confirm = input("Continue? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Restore cancelled.")
        return
    
    restored_path = asyncio.run(_restore_database_from_discord(args.backup_file))
    
    # Reinitialize database connection after restore
    from .database import init_database
    init_database()
    
    # Show what was restored
    batches = list_batches()
    print(f"\n{Fore.GREEN}✅ Database restored successfully!{Style.RESET_ALL}")
    print(f"Database location: {restored_path}")
    print(f"Total batches: {len(batches)}")
    
    if batches:
        print(f"\n{Fore.CYAN}Restored batches:{Style.RESET_ALL}")
        for i, batch in enumerate(batches[:5], 1):
            print(f"  {i}. {batch['batch_id']} - {batch['original_name']}")
        if len(batches) > 5:
            print(f"  ... and {len(batches) - 5} more")
    print(f"\nRun {Fore.CYAN}python bot.py list{Style.RESET_ALL} to see all batches.")


async def _delete_from_discord(batch_id: str) -> None:
    batch = get_batch(batch_id)
    if not batch:
        raise StorageBotError("Batch not found.")
    config = Config.get_instance()
    client = setup_bot(config.discord_bot_token)
    done: asyncio.Future[None] = asyncio.Future()

    @client.event
    async def on_ready() -> None:
        try:
            if not client.guilds:
                raise StorageBotError("Bot is not connected to any guild.")
            guild = client.guilds[0]
            index_channel = discord.utils.get(
                guild.text_channels, name=config.batch_index_channel_name
            )
            thread_id = int(batch["thread_id"]) if batch.get("thread_id") else None
            message_id = int(batch["archive_message_id"]) if batch.get("archive_message_id") else None

            if thread_id:
                try:
                    thread = client.get_channel(thread_id) or await client.fetch_channel(thread_id)
                    if isinstance(thread, discord.Thread):
                        await thread.delete()
                except discord.NotFound:
                    pass
            if index_channel and message_id:
                try:
                    message = await index_channel.fetch_message(message_id)
                    await message.delete()
                except discord.NotFound:
                    pass

            done.set_result(None)
        except Exception as exc:
            done.set_exception(exc)
        finally:
            await client.close()

    await client.start(config.discord_bot_token)
    await done


async def _upload_backup_to_discord(backup_path: Path) -> None:
    config = Config.get_instance()
    client = setup_bot(config.discord_bot_token)
    done: asyncio.Future[None] = asyncio.Future()

    @client.event
    async def on_ready() -> None:
        try:
            await upload_backup_file(client, config.backup_channel_name, backup_path)
            done.set_result(None)
        except Exception as exc:
            done.set_exception(exc)
        finally:
            await client.close()

    await client.start(config.discord_bot_token)
    await done


async def _restore_database_from_discord(backup_filename: str = None) -> Path:
    """
    Restore database from Discord backup channel.
    
    Args:
        backup_filename: Specific backup filename to restore (None = latest)
    
    Returns:
        Path to restored database file.
    """
    config = Config.get_instance()
    client = setup_bot(config.discord_bot_token)
    done: asyncio.Future[Path] = asyncio.Future()

    @client.event
    async def on_ready() -> None:
        try:
            if not client.guilds:
                raise StorageBotError("Bot is not connected to any guild.")
            guild = client.guilds[0]
            print(f"✓ Connected to guild: {guild.name}")
            
            backup_channel = discord.utils.get(
                guild.text_channels, name=config.backup_channel_name
            )
            if backup_channel is None:
                raise StorageBotError(
                    f"Backup channel '{config.backup_channel_name}' not found."
                )
            print(f"✓ Found backup channel: #{backup_channel.name}")
            
            # Find the backup file
            target_message = None
            async for message in backup_channel.history(limit=100, oldest_first=False):
                if not message.attachments:
                    continue
                
                attachment = message.attachments[0]
                
                # Check if this is a database backup file
                if not attachment.filename.endswith('.db'):
                    continue
                
                # If specific filename requested, match it
                if backup_filename:
                    if attachment.filename == backup_filename:
                        target_message = message
                        break
                else:
                    # Use the first (most recent) backup found
                    target_message = message
                    break
            
            if not target_message:
                if backup_filename:
                    raise StorageBotError(
                        f"Backup file '{backup_filename}' not found in #{config.backup_channel_name}"
                    )
                else:
                    raise StorageBotError(
                        f"No database backups found in #{config.backup_channel_name}"
                    )
            
            attachment = target_message.attachments[0]
            print(f"✓ Found backup: {attachment.filename} ({format_bytes(attachment.size)})")
            print(f"  Uploaded: {target_message.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # Download the backup file
            print(f"✓ Downloading backup...")
            temp_backup = DEFAULT_DB_PATH.with_suffix('.db.downloading')
            
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status != 200:
                        raise StorageBotError(f"Failed to download backup: HTTP {resp.status}")
                    
                    async with aiofiles.open(temp_backup, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            await f.write(chunk)
            
            print(f"✓ Download complete")
            
            # Backup current database if it exists
            if DEFAULT_DB_PATH.exists():
                old_backup = DEFAULT_DB_PATH.with_name(
                    f"storage_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
                )
                shutil.copy2(DEFAULT_DB_PATH, old_backup)
                print(f"✓ Current database backed up to: {old_backup.name}")
            
            # Replace with downloaded backup
            temp_backup.replace(DEFAULT_DB_PATH)
            print(f"✓ Database restored successfully")
            
            done.set_result(DEFAULT_DB_PATH)
        except Exception as exc:
            done.set_exception(exc)
        finally:
            await client.close()

    await client.start(config.discord_bot_token)
    return await done


def main() -> None:
    """
    CLI entry point.
    """
    colorama_init()
    init_database()
    args = parse_arguments()

    try:
        if not args.command:
            _print_command_help("Choose a command to continue.")
            return
        if args.command == "help":
            _print_command_help("Discord Storage Bot CLI Help")
            return
        if args.command == "upload":
            command_upload(args)
        elif args.command == "download":
            command_download(args)
        elif args.command == "list":
            command_list(args)
        elif args.command == "info":
            command_info(args)
        elif args.command == "delete":
            command_delete(args)
        elif args.command == "stats":
            command_stats(args)
        elif args.command == "channels":
            command_channels(args)
        elif args.command == "verify":
            command_verify(args)
        elif args.command == "resume":
            command_resume(args)
        elif args.command == "backup":
            command_backup(args)
        elif args.command == "sync":
            command_sync(args)
        elif args.command == "restore":
            command_restore(args)
    except StorageBotError as exc:
        print(f"{Fore.RED}Error: {exc}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
