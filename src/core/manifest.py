"""JSON manifest creation and parsing logic."""

import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional

from ..common.constants import LEGACY_MANIFEST


def build_manifest_name(total_chunks: int, timestamp: Optional[datetime.datetime] = None) -> str:
    """
    Build a manifest name like 123-manifest_HHMMSS_DDMMYY.json.
    
    Args:
        total_chunks: Total number of chunks
        timestamp: Optional timestamp (defaults to now)
    
    Returns:
        Manifest filename
    """
    now = timestamp or datetime.datetime.now()
    time_part = now.strftime("%H%M%S")
    date_part = now.strftime("%d%m%y")
    return f"{total_chunks}-manifest_{time_part}_{date_part}.json"


def create_manifest(
    source_folder_name: str,
    files: Dict[str, Any],
    total_original_size: int,
    total_processed_size: int,
    total_chunks: int,
    encrypted: bool = True,
) -> Dict[str, Any]:
    """
    Create a manifest dictionary.
    
    Args:
        source_folder_name: Name of the source folder
        files: Dictionary of file information
        total_original_size: Total size of original files
        total_processed_size: Total size after processing
        total_chunks: Total number of chunks
        encrypted: Whether the archive is encrypted
    
    Returns:
        Manifest dictionary
    """
    manifest = {
        "version": "3.1",
        "encrypted": encrypted,
        "compression": "gzip-9",
        "encryption_algorithm": "AES-256-GCM" if encrypted else None,
        "kdf": "PBKDF2-SHA256-600000" if encrypted else None,
        "chunking": "per-chunk",
        "encryption_scope": "chunk" if encrypted else None,
        "source_folder": source_folder_name,
        "files": files,
        "total_original_size": total_original_size,
        "total_processed_size": total_processed_size,
        "total_chunks": total_chunks,
    }
    
    if total_original_size > 0:
        manifest["space_saved_percent"] = round(
            (1 - total_processed_size / total_original_size) * 100, 2
        )
    else:
        manifest["space_saved_percent"] = 0.0
    
    return manifest


def parse_manifest(manifest_path: Path) -> Dict[str, Any]:
    """
    Parse a manifest JSON file.
    
    Args:
        manifest_path: Path to manifest file
    
    Returns:
        Manifest dictionary
    
    Raises:
        ValueError: If manifest cannot be parsed
    """
    try:
        with open(manifest_path, "r") as f:
            return json.load(f)
    except Exception as exc:
        raise ValueError(f"Failed to parse manifest {manifest_path.name}: {exc}") from exc


def save_manifest(manifest: Dict[str, Any], output_dir: Path, total_chunks: int) -> Path:
    """
    Save manifest to a file.
    
    Args:
        manifest: Manifest dictionary
        output_dir: Output directory
        total_chunks: Total number of chunks
    
    Returns:
        Path to saved manifest file
    """
    now = datetime.datetime.now()
    base_manifest_name = build_manifest_name(total_chunks, now)
    manifest_name = base_manifest_name
    manifest_path = output_dir / manifest_name
    
    counter = 1
    while manifest_path.exists():
        stem = base_manifest_name[:-5] if base_manifest_name.lower().endswith(
            ".json") else base_manifest_name
        manifest_name = f"{stem}_{counter}.json"
        manifest_path = output_dir / manifest_name
        counter += 1
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=4)
    
    return manifest_path


def list_manifest_files(folder: Path) -> List[Path]:
    """
    Find all manifest files in a folder.
    
    Args:
        folder: Folder to search
    
    Returns:
        List of manifest file paths
    """
    candidates = []
    try:
        for path in folder.iterdir():
            if not path.is_file():
                continue
            name = path.name.lower()
            if not name.endswith(".json"):
                continue
            if "manifest" not in name:
                continue
            candidates.append(path)
    except OSError:
        return []
    
    legacy_path = folder / LEGACY_MANIFEST
    if legacy_path.exists() and legacy_path not in candidates:
        candidates.append(legacy_path)
    
    return candidates


def find_manifest_file(folder: Path) -> Tuple[Optional[Path], int]:
    """
    Find the most recent manifest file in the folder.
    
    Args:
        folder: Folder to search
    
    Returns:
        Tuple of (manifest path, total manifest count)
    """
    candidates = list_manifest_files(folder)
    if not candidates:
        return None, 0
    
    unique_candidates = {path.resolve(): path for path in candidates}
    manifest_files = sorted(
        unique_candidates.values(),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    
    return manifest_files[0], len(manifest_files)
