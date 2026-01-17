"""Gzip compression and decompression logic."""

import gzip


def compress_data(data: bytes, compresslevel: int = 9) -> bytes:
    """
    Compress data using gzip.
    
    Args:
        data: Data to compress
        compresslevel: Compression level (0-9, 9 is maximum compression)
    
    Returns:
        Compressed data
    """
    return gzip.compress(data, compresslevel=compresslevel)


def decompress_data(data: bytes) -> bytes:
    """
    Decompress gzip data.
    
    Args:
        data: Compressed data
    
    Returns:
        Decompressed data
    
    Raises:
        ValueError: If decompression fails
    """
    try:
        return gzip.decompress(data)
    except Exception as exc:
        raise ValueError(
            "Decompression failed. Data may be corrupted."
        ) from exc
