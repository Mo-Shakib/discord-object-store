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
        ("verify <batch_id>", "Verify integrity", "Re-hash chunks and compare."),
        ("resume <batch_id>", "Resume upload", "Continue interrupted upload."),
        ("backup", "Backup database", "Create/upload DB backup."),
        ("sync [--reset]", "Sync from Discord", "Rebuild DB from Discord."),
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
    print("  python bot.py sync --reset")
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

    download_parser = subparsers.add_parser("download", help="Download batch")
    download_parser.add_argument("batch_id", help="Batch ID")
    download_parser.add_argument("path", help="Destination path")

    subparsers.add_parser("list", help="List all batches")

    info_parser = subparsers.add_parser("info", help="Batch details")
    info_parser.add_argument("batch_id", help="Batch ID")

    delete_parser = subparsers.add_parser("delete", help="Delete batch metadata")
    delete_parser.add_argument("batch_id", help="Batch ID")

    subparsers.add_parser("stats", help="Storage statistics")

    verify_parser = subparsers.add_parser("verify", help="Verify batch integrity")
    verify_parser.add_argument("batch_id", help="Batch ID")

    resume_parser = subparsers.add_parser("resume", help="Resume interrupted upload")
    resume_parser.add_argument("batch_id", help="Batch ID")

    subparsers.add_parser("backup", help="Backup database")

    sync_parser = subparsers.add_parser("sync", help="Sync database from Discord")
    sync_parser.add_argument(
        "--reset", action="store_true", help="Reset local database before syncing"
    )

    subparsers.add_parser("help", help="Show help and usage examples")

    return parser.parse_args()


def command_upload(args: argparse.Namespace) -> None:
    """
    Handle upload command.
    """
    batch_id = asyncio.run(upload(args.path, confirm=not args.yes))
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
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
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
        elif args.command == "verify":
            command_verify(args)
        elif args.command == "resume":
            command_resume(args)
        elif args.command == "backup":
            command_backup(args)
        elif args.command == "sync":
            command_sync(args)
    except StorageBotError as exc:
        print(f"{Fore.RED}Error: {exc}{Style.RESET_ALL}")


if __name__ == "__main__":
    main()
