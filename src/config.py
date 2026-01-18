"""Configuration management for Discord storage bot."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Optional

from dotenv import load_dotenv

from .utils import ConfigError, atomic_write
ENV_TOKEN = "DISCORD_BOT_TOKEN"
ENV_KEY = "ENCRYPTION_KEY"
ENV_STORAGE_CHANNEL = "STORAGE_CHANNEL_NAME"
ENV_ARCHIVE_CHANNEL = "ARCHIVE_CHANNEL_NAME"
ENV_BATCH_INDEX_CHANNEL = "BATCH_INDEX_CHANNEL_NAME"
ENV_BACKUP_CHANNEL = "BACKUP_CHANNEL_NAME"
ENV_CHUNK_SIZE = "MAX_CHUNK_SIZE"
ENV_UPLOADS = "CONCURRENT_UPLOADS"
ENV_DOWNLOADS = "CONCURRENT_DOWNLOADS"
MAX_CHUNK_SIZE_CAP = 9_500_000


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _env_path() -> Path:
    return _base_dir() / ".env"


def validate_token(token: str) -> bool:
    """
    Validate Discord bot token format.

    Args:
        token: Bot token string.

    Returns:
        True if the token looks valid.
    """
    if not token or token.count(".") != 2:
        return False
    pattern = re.compile(
        r"^[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{20,}$")
    return bool(pattern.match(token))


def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded Fernet key.
    """
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise ConfigError(
            "cryptography is required to generate encryption key.") from exc
    return Fernet.generate_key().decode("utf-8")


def save_config(config: "Config") -> None:
    """
    Persist configuration to the .env file.

    Args:
        config: Config instance to save.
    """
    lines = [
        f"{ENV_TOKEN}={config.discord_bot_token}",
        f"{ENV_KEY}={config.encryption_key}",
        f"{ENV_STORAGE_CHANNEL}={config.storage_channel_name}",
        f"{ENV_ARCHIVE_CHANNEL}={config.archive_channel_name}",
        f"{ENV_BATCH_INDEX_CHANNEL}={config.batch_index_channel_name}",
        f"{ENV_BACKUP_CHANNEL}={config.backup_channel_name}",
        f"{ENV_CHUNK_SIZE}={config.max_chunk_size}",
        f"{ENV_UPLOADS}={config.concurrent_uploads}",
        f"{ENV_DOWNLOADS}={config.concurrent_downloads}",
    ]
    data = "\n".join(lines) + "\n"
    env_file = _env_path()
    atomic_write(env_file, data)
    os.chmod(env_file, 0o600)


@dataclass(frozen=True)
class Config:
    """Singleton configuration object."""

    discord_bot_token: str
    encryption_key: str
    storage_channel_name: str
    archive_channel_name: str
    batch_index_channel_name: str
    backup_channel_name: str
    max_chunk_size: int
    concurrent_uploads: int
    concurrent_downloads: int

    _instance: ClassVar[Optional["Config"]] = None

    @classmethod
    def get_instance(cls) -> "Config":
        """
        Retrieve a singleton instance of Config.

        Returns:
            Config singleton instance.
        """
        if cls._instance is None:
            cls._instance = load_config()
        return cls._instance


def _parse_int(value: str, name: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} must be greater than 0.")
    return parsed


def _parse_chunk_size(value: str) -> int:
    parsed = _parse_int(value, ENV_CHUNK_SIZE)
    if parsed > MAX_CHUNK_SIZE_CAP:
        import warnings

        warnings.warn(
            f"{ENV_CHUNK_SIZE} capped at {MAX_CHUNK_SIZE_CAP} bytes "
            f"(<10 MB).",
            RuntimeWarning,
        )
        return MAX_CHUNK_SIZE_CAP
    return parsed


def load_config() -> Config:
    """
    Load and validate configuration from the .env file.

    Returns:
        Config instance.
    """
    env_file = _env_path()
    if env_file.exists():
        load_dotenv(env_file)

    token = os.getenv(ENV_TOKEN, "").strip()
    encryption_key = os.getenv(ENV_KEY, "").strip()
    storage_channel = os.getenv(
        ENV_STORAGE_CHANNEL, "file-storage-vault").strip()
    archive_channel = os.getenv(ENV_ARCHIVE_CHANNEL, "archive-cards").strip()
    batch_index_channel = os.getenv(
        ENV_BATCH_INDEX_CHANNEL, "batch-index").strip()
    backup_channel = os.getenv(ENV_BACKUP_CHANNEL, "db-backups").strip()
    max_chunk = os.getenv(ENV_CHUNK_SIZE, str(MAX_CHUNK_SIZE_CAP)).strip()
    concurrent_uploads = os.getenv(ENV_UPLOADS, "5").strip()
    concurrent_downloads = os.getenv(ENV_DOWNLOADS, "5").strip()

    if not token:
        raise ConfigError(
            "DISCORD_BOT_TOKEN is required. Run setup.py to configure.")
    if not validate_token(token):
        raise ConfigError("DISCORD_BOT_TOKEN format is invalid.")
    generated_key = False
    if not encryption_key:
        encryption_key = generate_encryption_key()
        generated_key = True

    config = Config(
        discord_bot_token=token,
        encryption_key=encryption_key,
        storage_channel_name=storage_channel,
        archive_channel_name=archive_channel,
        batch_index_channel_name=batch_index_channel,
        backup_channel_name=backup_channel,
        max_chunk_size=_parse_chunk_size(max_chunk),
        concurrent_uploads=_parse_int(concurrent_uploads, ENV_UPLOADS),
        concurrent_downloads=_parse_int(concurrent_downloads, ENV_DOWNLOADS),
    )

    if generated_key or not env_file.exists():
        save_config(config)

    return config
