"""AES-256-GCM encryption and PBKDF2 key derivation logic."""

import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def derive_encryption_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit encryption key from password using PBKDF2.
    
    Args:
        password: User password string
        salt: 16-byte salt
    
    Returns:
        32-byte encryption key
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,
    )
    return kdf.derive(password.encode())


def encrypt_data(data: bytes, password: str) -> bytes:
    """
    Encrypt data using AES-256-GCM.
    
    Args:
        data: Data to encrypt
        password: User password
    
    Returns:
        Encrypted data: salt (16 bytes) + nonce (12 bytes) + ciphertext
    """
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_encryption_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return salt + nonce + ciphertext


def decrypt_data(data: bytes, password: str) -> bytes:
    """
    Decrypt AES-256-GCM encrypted data.
    
    Args:
        data: Encrypted data (salt + nonce + ciphertext)
        password: User password
    
    Returns:
        Decrypted data
    
    Raises:
        ValueError: If data is too short, wrong password, or corrupted
    """
    if len(data) < 28:
        raise ValueError("Data too short to be encrypted.")
    
    salt = data[:16]
    nonce = data[16:28]
    ciphertext = data[28:]
    
    key = derive_encryption_key(password, salt)
    aesgcm = AESGCM(key)
    
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError(
            "Decryption failed. Wrong password or corrupted data."
        ) from exc
