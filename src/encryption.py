"""Encryption utilities for Discord storage bot."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from pathlib import Path
from typing import Callable, Optional

import aiofiles
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .utils import EncryptionError, get_io_buffer_size
ProgressCallback = Callable[[int, int, Optional[str]], None]


def generate_salt() -> str:
    """
    Generate a random salt.

    Returns:
        Base64-encoded salt string.
    """
    return base64.urlsafe_b64encode(secrets.token_bytes(16)).decode("utf-8")


def derive_key(master_key: str, salt: str) -> str:
    """
    Derive a Fernet key using PBKDF2.

    Args:
        master_key: Master key from configuration.
        salt: Base64-encoded salt.

    Returns:
        Derived Fernet key string.
    """
    try:
        master_bytes = base64.urlsafe_b64decode(master_key)
        salt_bytes = base64.urlsafe_b64decode(salt)
    except Exception as exc:
        raise EncryptionError("Invalid master key or salt format.") from exc

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt_bytes,
        iterations=200_000,
    )
    derived = kdf.derive(master_bytes)
    return base64.urlsafe_b64encode(derived).decode("utf-8")


def encrypt_chunk(data: bytes, key: str) -> bytes:
    """
    Encrypt bytes in memory.

    Args:
        data: Plaintext bytes.
        key: Fernet key.

    Returns:
        Encrypted bytes.
    """
    try:
        return Fernet(key).encrypt(data)
    except Exception as exc:
        raise EncryptionError("Failed to encrypt chunk.") from exc


def decrypt_chunk(data: bytes, key: str) -> bytes:
    """
    Decrypt bytes in memory.

    Args:
        data: Encrypted bytes.
        key: Fernet key.

    Returns:
        Decrypted bytes.
    """
    try:
        return Fernet(key).decrypt(data)
    except InvalidToken as exc:
        raise EncryptionError("Encrypted chunk integrity check failed.") from exc
    except Exception as exc:
        raise EncryptionError("Failed to decrypt chunk.") from exc


async def encrypt_file(
    input_path: Path,
    output_path: Path,
    key: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    Encrypt a file using chunked Fernet encryption (async).

    Args:
        input_path: Source file path.
        output_path: Encrypted file path.
        key: Fernet key.
        progress_callback: Optional progress callback.
    """
    total = input_path.stat().st_size
    processed = 0
    fernet = Fernet(key)
    buffer_size = get_io_buffer_size()

    try:
        async with aiofiles.open(input_path, "rb") as infile, \
                   aiofiles.open(output_path, "wb") as outfile:
            while True:
                chunk = await infile.read(buffer_size)
                if not chunk:
                    break
                # Encryption is CPU-bound, offload to thread pool
                encrypted = await asyncio.to_thread(fernet.encrypt, chunk)
                await outfile.write(len(encrypted).to_bytes(8, "big"))
                await outfile.write(encrypted)
                processed += len(chunk)
                if progress_callback:
                    progress_callback(processed, total, str(input_path))
    except Exception as exc:
        raise EncryptionError("Failed to encrypt file.") from exc


async def decrypt_file(
    input_path: Path,
    output_path: Path,
    key: str,
    progress_callback: Optional[ProgressCallback] = None,
) -> None:
    """
    Decrypt a file created by encrypt_file (async).

    Args:
        input_path: Encrypted file path.
        output_path: Output file path.
        key: Fernet key.
        progress_callback: Optional progress callback.
    """
    total = input_path.stat().st_size
    processed = 0
    fernet = Fernet(key)
    buffer_size = get_io_buffer_size()

    try:
        async with aiofiles.open(input_path, "rb") as infile, \
                   aiofiles.open(output_path, "wb") as outfile:
            while True:
                size_bytes = await infile.read(8)
                if not size_bytes:
                    break
                chunk_size = int.from_bytes(size_bytes, "big")
                encrypted = await infile.read(chunk_size)
                if len(encrypted) != chunk_size:
                    raise EncryptionError("Encrypted file is truncated or corrupt.")
                # Decryption is CPU-bound, offload to thread pool
                decrypted = await asyncio.to_thread(fernet.decrypt, encrypted)
                await outfile.write(decrypted)
                processed += len(decrypted)
                if progress_callback:
                    progress_callback(processed, total, str(input_path))
    except InvalidToken as exc:
        raise EncryptionError("Encrypted file integrity check failed.") from exc
    except Exception as exc:
        raise EncryptionError("Failed to decrypt file.") from exc


def calculate_hash(
    file_path: Path, progress_callback: Optional[ProgressCallback] = None
) -> str:
    """
    Calculate SHA-256 hash for a file.

    Args:
        file_path: File path to hash.
        progress_callback: Optional progress callback.

    Returns:
        SHA-256 hex digest.
    """
    total = file_path.stat().st_size
    processed = 0
    digest = hashlib.sha256()
    buffer_size = get_io_buffer_size()

    with open(file_path, "rb") as infile:
        while True:
            chunk = infile.read(buffer_size)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, total, str(file_path))

    return digest.hexdigest()
