"""Interactive setup wizard for Discord storage bot."""

from __future__ import annotations

import asyncio
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init as colorama_init
import discord

from src.config import Config, generate_encryption_key, save_config, validate_token
from src.utils import ConfigError, setup_logging


def _project_root() -> Path:
    return Path(__file__).resolve().parent


def _print_banner() -> None:
    print(f"{Fore.CYAN}Discord Storage Bot Setup{Style.RESET_ALL}")
    print(f"{Fore.CYAN}{'=' * 26}{Style.RESET_ALL}")
    print("This wizard will configure your bot token and database.")


def _check_python_version() -> None:
    if sys.version_info < (3, 10):
        raise ConfigError("Python 3.10 or higher is required.")


def prompt_bot_token() -> str:
    """
    Prompt the user for a Discord bot token.

    Returns:
        Validated bot token.
    """
    while True:
        token = input("Enter your Discord bot token: ").strip()
        if validate_token(token):
            return token
        print("Invalid token format. Please try again.")


async def test_connection(token: str) -> Optional[int]:
    """
    Verify the Discord bot token by connecting.

    Args:
        token: Discord bot token.

    Returns:
        Client ID if successful.
    """
    intents = discord.Intents(guilds=True)
    client = discord.Client(intents=intents)
    client_id: Optional[int] = None

    async def on_ready() -> None:
        nonlocal client_id
        if client.user:
            client_id = client.user.id
        await client.close()

    client.event(on_ready)
    try:
        await client.start(token)
    except discord.LoginFailure as exc:
        raise ConfigError("Unable to login with the provided token.") from exc
    return client_id


async def ensure_channels_setup(
    token: str, storage_name: str, archive_name: str, index_name: str, backup_name: str
) -> bool:
    """
    Ensure storage and archive channels exist. Returns True if any were missing.

    Args:
        token: Discord bot token.
        storage_name: Storage channel name.
        archive_name: Archive channel name.

    Returns:
        True if channels were missing and created.
    """
    intents = discord.Intents(guilds=True)
    client = discord.Client(intents=intents)
    created_missing = False

    async def on_ready() -> None:
        nonlocal created_missing
        if not client.guilds:
            await client.close()
            raise ConfigError("Bot is not connected to any guild.")
        guild = client.guilds[0]
        storage_channel = discord.utils.get(
            guild.text_channels, name=storage_name)
        archive_channel = discord.utils.get(
            guild.text_channels, name=archive_name)
        index_channel = discord.utils.get(guild.text_channels, name=index_name)
        backup_channel = discord.utils.get(
            guild.text_channels, name=backup_name)
        if storage_channel is None:
            await guild.create_text_channel(storage_name)
            created_missing = True
        if archive_channel is None:
            await guild.create_text_channel(archive_name)
            created_missing = True
        if index_channel is None:
            await guild.create_text_channel(index_name)
            created_missing = True
        if backup_channel is None:
            await guild.create_text_channel(backup_name)
            created_missing = True
        await client.close()

    client.event(on_ready)
    try:
        await client.start(token)
    except discord.LoginFailure as exc:
        raise ConfigError("Unable to login with the provided token.") from exc
    return created_missing


def generate_invite_link(client_id: int) -> str:
    """
    Create OAuth2 invite link for the bot.

    Args:
        client_id: Discord client ID.

    Returns:
        Invite URL.
    """
    permissions = 274877906944  # Manage Threads + Send Messages + Attach Files
    return (
        "https://discord.com/api/oauth2/authorize"
        f"?client_id={client_id}&permissions={permissions}&scope=bot"
    )


def run_setup() -> None:
    """
    Run the interactive setup wizard.
    """
    colorama_init()
    setup_logging()
    _print_banner()
    _check_python_version()

    token = prompt_bot_token()
    encryption_key = generate_encryption_key()

    config = Config(
        discord_bot_token=token,
        encryption_key=encryption_key,
        storage_channel_name="file-storage-vault",
        archive_channel_name="archive-cards",
        batch_index_channel_name="batch-index",
        backup_channel_name="db-backups",
        max_chunk_size=9_500_000,
        concurrent_uploads=5,
        concurrent_downloads=5,
    )
    save_config(config)
    print(f"{Fore.GREEN}✓ Configuration saved.{Style.RESET_ALL}")

    client_id = asyncio.run(test_connection(token))
    if client_id:
        invite = generate_invite_link(client_id)
        print(f"{Fore.CYAN}Invite link:{Style.RESET_ALL} {invite}")

    try:
        from src.database import DEFAULT_DB_PATH, init_database
    except ImportError:
        print("Database module not yet available. Run setup again after Phase 2.")
        return

    restore_path = prompt_restore_backup()
    if restore_path:
        if restore_backup(DEFAULT_DB_PATH, restore_path):
            print(f"{Fore.GREEN}✓ Database restored from backup.{Style.RESET_ALL}")
        else:
            print("Backup validation failed. Starting fresh database.")
            init_database()
            print(f"{Fore.GREEN}✓ Database initialized.{Style.RESET_ALL}")
    else:
        if DEFAULT_DB_PATH.exists():
            DEFAULT_DB_PATH.unlink()
        init_database()
        print(f"{Fore.GREEN}✓ Database initialized (fresh start).{Style.RESET_ALL}")

    channels_missing = asyncio.run(
        ensure_channels_setup(
            token,
            config.storage_channel_name,
            config.archive_channel_name,
            config.batch_index_channel_name,
            config.backup_channel_name,
        )
    )
    if channels_missing:
        if DEFAULT_DB_PATH.exists():
            DEFAULT_DB_PATH.unlink()
        init_database()
        print(
            "Channels were missing and have been created. "
            "Local database was reset to stay in sync."
        )

    sync_choice = input(
        "Sync local database from Discord now? [y/N]: "
    ).strip().lower()
    if sync_choice == "y":
        try:
            from src.syncer import sync_from_discord
        except ImportError:
            print("Sync module not available.")
        else:
            synced = asyncio.run(sync_from_discord(reset_db=True))
            print(
                f"{Fore.GREEN}✓ Synced {synced} batches from Discord.{Style.RESET_ALL}")
    print(f"{Fore.GREEN}Setup complete.{Style.RESET_ALL} Next step: run `python bot.py`")


def prompt_restore_backup() -> Optional[Path]:
    """
    Prompt for an optional database restore.

    Returns:
        Path to backup file if provided.
    """
    choice = input(
        "Do you want to restore a database backup? [y/N]: "
    ).strip().lower()
    if choice != "y":
        return None
    backup_path = input("Enter path to backup file: ").strip()
    if not backup_path:
        return None
    return Path(backup_path).expanduser().resolve()


def validate_backup(backup_path: Path) -> bool:
    """
    Validate backup file by checking schema.

    Args:
        backup_path: Path to backup db file.

    Returns:
        True if backup contains required tables.
    """
    if not backup_path.exists():
        print("Backup file not found.")
        return False
    try:
        with sqlite3.connect(backup_path) as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cur.fetchall()}
            required = {"batches", "chunks", "files"}
            return required.issubset(tables)
    except sqlite3.Error:
        return False


def restore_backup(db_path: Path, backup_path: Path) -> bool:
    """
    Restore database from a backup file if valid.

    Args:
        db_path: Destination database path.
        backup_path: Source backup path.

    Returns:
        True if restored successfully.
    """
    if not validate_backup(backup_path):
        return False
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, db_path)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    try:
        run_setup()
    except ConfigError as exc:
        print(f"Setup failed: {exc}")
