"""Logic for splitting and hashing files."""

import hashlib
from pathlib import Path


def get_file_hash(file_path: Path) -> str:
    """
    Generate a SHA256 hash for a file's path and name to use as a unique ID.
    
    Args:
        file_path: Path to the file
    
    Returns:
        12-character hash string
    """
    return hashlib.sha256(str(file_path.name).encode()).hexdigest()[:12]


def get_chunk_hash(data: bytes) -> str:
    """
    Generate a hash for the actual chunk content.
    
    Args:
        data: Chunk data
    
    Returns:
        16-character hash string
    """
    return hashlib.sha256(data).hexdigest()[:16]
