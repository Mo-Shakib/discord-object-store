"""High-level logic coordinating slicing and assembling."""

import os
import re
import shutil
from pathlib import Path
from typing import Optional

from ..config import config
from ..core.crypto import encrypt_data, decrypt_data
from ..core.compression import compress_data, decompress_data
from ..core.chunking import get_file_hash, get_chunk_hash
from ..core.manifest import (
    create_manifest,
    parse_manifest,
    save_manifest,
    list_manifest_files,
)
from ..common.utils import format_bytes, clean_path
from ..common.constants import DEFAULT_CHUNK_SIZE_MB


class ArchiveManager:
    """Manager for slicing and assembling archives."""
    
    @staticmethod
    def slice_folder(folder_path: str, chunk_size_mb: float = DEFAULT_CHUNK_SIZE_MB) -> None:
        """
        Slice all files in a folder into compressed and encrypted chunks.
        
        Args:
            folder_path: Path to folder to slice
            chunk_size_mb: Chunk size in megabytes
        """
        folder = Path(clean_path(folder_path))
        if not folder.is_dir():
            print(f"Error: {folder} is not a valid directory.")
            return
        
        password = config.USER_KEY
        if not password:
            print("\n" + "=" * 50)
            print("❌ ENCRYPTION KEY REQUIRED")
            print("=" * 50)
            print("This operation requires USER_KEY to be set.")
            print("\nTo fix:")
            print("1. Open your .env file")
            print("2. Add: USER_KEY=your_secure_password")
            print("3. Restart the bot or script")
            print("=" * 50 + "\n")
            return
        
        chunk_size = int(chunk_size_mb * 1024 * 1024)
        output_base_dir = Path(config.UPLOAD_FOLDER)
        output_base_dir.mkdir(parents=True, exist_ok=True)
        
        files_to_process = [
            f for f in folder.iterdir() if f.is_file() and f.name != ".DS_Store"
        ]
        print(f"Found {len(files_to_process)} files to process.")
        print("🔒 Encryption: ENABLED (AES-256-GCM)")
        print("🗜️  Compression: ENABLED (gzip-9)\n")
        
        total_chunks = 0
        total_original_size = 0
        total_processed_size = 0
        manifest_files = {}
        
        for file_path in files_to_process:
            file_id = get_file_hash(file_path)
            file_size = file_path.stat().st_size
            total_original_size += file_size
            
            manifest_files[file_id] = {
                "original_name": file_path.name,
                "original_size": file_size,
                "chunks": [],
            }
            
            print(f"Processing: {file_path.name}")
            print(f"  Original size: {format_bytes(file_size)}")
            
            processed_size = 0
            num_chunks = 0
            
            def _process_chunk(raw_chunk: bytes, chunk_index: int) -> bool:
                nonlocal total_chunks, total_processed_size, processed_size, num_chunks
                
                try:
                    compressed = compress_data(raw_chunk)
                    processed_chunk = encrypt_data(compressed, password)
                except Exception as exc:
                    print(f"  ❌ Encryption failed: {exc}")
                    return False
                
                if not processed_chunk:
                    print("  ❌ Encryption failed: no data returned")
                    return False
                
                total_chunks += 1
                num_chunks += 1
                processed_size += len(processed_chunk)
                total_processed_size += len(processed_chunk)
                
                chunk_hash = get_chunk_hash(processed_chunk)
                chunk_name = f"{total_chunks:04d}-{file_id}-{chunk_hash}-{chunk_index:04d}.bin"
                chunk_path = output_base_dir / chunk_name
                
                with open(chunk_path, "wb") as chunk_file:
                    chunk_file.write(processed_chunk)
                
                manifest_files[file_id]["chunks"].append({
                    "name": chunk_name,
                    "size": len(processed_chunk),
                    "index": chunk_index,
                })
                return True
            
            with open(file_path, "rb") as file_handle:
                chunk_index = 0
                while True:
                    raw_chunk = file_handle.read(chunk_size)
                    if not raw_chunk:
                        break
                    if not _process_chunk(raw_chunk, chunk_index):
                        break
                    chunk_index += 1
            
            if file_size == 0:
                if not _process_chunk(b"", 0):
                    continue
            
            if file_size > 0:
                compression_ratio = (1 - processed_size / file_size) * 100
                print(f"  Generated {num_chunks} chunks")
                print(f"  Space saved: {compression_ratio:.1f}%\n")
            else:
                print(f"  Generated {num_chunks} chunks (empty file)\n")
        
        manifest = create_manifest(
            source_folder_name=folder.name,
            files=manifest_files,
            total_original_size=total_original_size,
            total_processed_size=total_processed_size,
            total_chunks=total_chunks,
            encrypted=True,
        )
        
        manifest_path = save_manifest(manifest, output_base_dir, total_chunks)
        
        print(f"\n{'=' * 50}")
        print("✅ SLICING COMPLETE")
        print(f"{'=' * 50}")
        print("🔒 Security: AES-256-GCM encryption + gzip-9 compression")
        print(f"📦 Original size: {format_bytes(total_original_size)}")
        print(f"🗜️  Final size: {format_bytes(total_processed_size)}")
        if total_original_size > 0:
            print(
                f"📉 Space saved: {(1 - total_processed_size / total_original_size) * 100:.1f}%"
            )
        else:
            print("📉 Space saved: 0.0%")
        print(f"🧩 Total chunks: {total_chunks}")
        print(f"📂 Location: {output_base_dir}")
        print("\n⚠️  IMPORTANT: Keep these safe:")
        print(f"   1. Manifest file: {manifest_path.name}")
        print("   2. USER_KEY from .env (required for decryption)")
        print(f"{'=' * 50}\n")
    
    @staticmethod
    def resolve_chunks_folder(path_str: str) -> Path:
        """
        Resolve the chunks folder path, handling various formats.
        
        Args:
            path_str: Path string
        
        Returns:
            Resolved Path object
        """
        folder = Path(clean_path(path_str))
        if folder.exists():
            return folder
        
        parent = folder.parent
        if not parent.exists():
            return folder
        
        name = folder.name.strip()
        match = re.search(r"(\d{6}-\d+)", name)
        archive_id = match.group(1) if match else None
        
        candidate_names = []
        if archive_id:
            candidate_names.extend([
                f"[Archive] #{archive_id}",
                f"[Archive] {archive_id}",
                f"#{archive_id}",
                archive_id,
            ])
        
        for candidate_name in candidate_names:
            candidate_path = parent / candidate_name
            if candidate_path.exists():
                return candidate_path
        
        if archive_id:
            for candidate in parent.glob(f"*{archive_id}*"):
                if candidate.is_dir():
                    return candidate
        
        return folder
    
    @staticmethod
    def assemble_from_manifest(chunks_folder_path: str) -> None:
        """
        Assemble files using manifest files found in the chunks folder.
        
        Args:
            chunks_folder_path: Path to folder containing chunks and manifest
        """
        folder = ArchiveManager.resolve_chunks_folder(chunks_folder_path)
        if not folder.exists():
            print(
                f"Error: Folder not found: {folder}. "
                "Expected format: '[Archive] #DDMMYY-Number'."
            )
            return
        
        manifest_paths = list_manifest_files(folder)
        if not manifest_paths:
            json_candidates = [
                p.name for p in folder.iterdir()
                if p.is_file() and p.name.lower().endswith(".json")
            ]
            if json_candidates:
                print(
                    f"Debug: JSON files found: {', '.join(sorted(json_candidates))}"
                )
            print(
                f"Error: No manifest file found in {folder}. Reassembly impossible."
            )
            return
        
        unique_paths = {path.resolve(): path for path in manifest_paths}
        manifest_files = sorted(
            unique_paths.values(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        manifest_count = len(manifest_files)
        
        output_base = folder.parent
        output_base.mkdir(exist_ok=True)
        
        if manifest_count > 1:
            print(
                f"Multiple manifests found. Reassembling {manifest_count} manifests."
            )
        
        had_errors = False
        
        for manifest_path in manifest_files:
            try:
                manifest = parse_manifest(manifest_path)
            except Exception as exc:
                print(f"⚠️ {exc}")
                had_errors = True
                continue
            
            is_encrypted = bool(manifest.get("encrypted"))
            encryption_scope = manifest.get("encryption_scope", "file")
            
            if is_encrypted:
                password = config.USER_KEY
                if not password:
                    print("\n" + "=" * 50)
                    print("❌ ENCRYPTION KEY REQUIRED")
                    print("=" * 50)
                    print("This archive is encrypted but USER_KEY is not set.")
                    print("\nTo fix:")
                    print("1. Open your .env file")
                    print("2. Add: USER_KEY=your_secure_password")
                    print("3. Restart the bot or script")
                    print("=" * 50 + "\n")
                    return
                print(
                    f"🔒 Archive is ENCRYPTED ({manifest.get('encryption_algorithm', 'unknown')})"
                )
            else:
                password = None
                print("⚠️  Archive is NOT encrypted (legacy format)")
            
            output_dir = ArchiveManager._resolve_output_dir(
                output_base, manifest, manifest_path, manifest_count
            )
            output_dir.mkdir(exist_ok=True)
            
            files = manifest.get("files", {})
            print(f"\n{'=' * 50}")
            print(
                f"Starting reassembly of {len(files)} file(s) from {manifest_path.name}"
            )
            print(f"{'=' * 50}\n")
            
            for file_id, info in files.items():
                original_name = info.get("original_name")
                if original_name == ".DS_Store":
                    print("⏭️  Skipping .DS_Store")
                    continue
                if not original_name:
                    print(f"  Skipping entry {file_id}: missing original_name")
                    had_errors = True
                    continue
                
                target_path = output_dir / original_name
                print(f"📄 Reassembling: {original_name}")
                
                chunk_entries = info.get("chunks") or []
                if chunk_entries and isinstance(chunk_entries[0], dict):
                    chunk_entries = sorted(
                        chunk_entries, key=lambda item: item.get("index", 0)
                    )
                
                if is_encrypted and encryption_scope == "chunk":
                    success = ArchiveManager._assemble_per_chunk_encryption(
                        chunk_entries, folder, target_path, password, info
                    )
                    if not success:
                        had_errors = True
                    continue
                
                success = ArchiveManager._assemble_file_encryption(
                    chunk_entries, folder, target_path, is_encrypted, password, info
                )
                if not success:
                    had_errors = True
        
        print(f"\n--- Reassembly Complete ---")
        print(f"All files restored to: {output_base}")
        if not had_errors:
            try:
                shutil.rmtree(folder)
                print(f"🗑️ Removed chunks folder: {folder}")
            except OSError as exc:
                print(f"⚠️ Could not remove chunks folder {folder}: {exc}")
    
    @staticmethod
    def _resolve_output_dir(
        base_dir: Path,
        manifest: dict,
        manifest_path: Path,
        manifest_count: int
    ) -> Path:
        """Resolve the output directory for reassembly."""
        source_folder = manifest.get("source_folder")
        if source_folder:
            return base_dir / source_folder
        if manifest_count > 1:
            return base_dir / f"restored_{manifest_path.stem}"
        return base_dir
    
    @staticmethod
    def _assemble_per_chunk_encryption(
        chunk_entries: list,
        folder: Path,
        target_path: Path,
        password: str,
        info: dict
    ) -> bool:
        """Assemble file with per-chunk encryption."""
        total_written = 0
        try:
            with open(target_path, "wb") as out_file:
                for chunk_info in chunk_entries:
                    chunk_name = (
                        chunk_info
                        if isinstance(chunk_info, str)
                        else chunk_info.get("name")
                    )
                    if not chunk_name:
                        raise ValueError("Missing chunk name in manifest entry.")
                    
                    chunk_path = folder / chunk_name
                    if not chunk_path.exists():
                        raise FileNotFoundError(f"Missing chunk: {chunk_name}")
                    
                    with open(chunk_path, "rb") as chunk_file:
                        encrypted_chunk = chunk_file.read()
                    
                    try:
                        decrypted = decrypt_data(encrypted_chunk, password)
                        original_chunk = decompress_data(decrypted)
                    except ValueError as exc:
                        raise ValueError(
                            f"Decryption failed for {chunk_name}: {exc}"
                        ) from exc
                    
                    out_file.write(original_chunk)
                    total_written += len(original_chunk)
        except Exception as exc:
            print(f"   ❌ Error reassembling chunks: {exc}\n")
            return False
        
        print(
            f"   ✓ Reassembled {len(chunk_entries)} chunks ({format_bytes(total_written)})"
        )
        print("   ✓ Decrypted and decompressed per chunk")
        
        expected_size = info.get("original_size")
        if expected_size is not None and total_written != expected_size:
            print(
                f"   ⚠️  Warning: Size mismatch (expected {format_bytes(expected_size)}, "
                f"got {format_bytes(total_written)})"
            )
        
        print(f"   ✅ Successfully restored to: {target_path.name}\n")
        return True
    
    @staticmethod
    def _assemble_file_encryption(
        chunk_entries: list,
        folder: Path,
        target_path: Path,
        is_encrypted: bool,
        password: Optional[str],
        info: dict
    ) -> bool:
        """Assemble file with file-level encryption (legacy)."""
        encrypted_data = bytearray()
        try:
            for chunk_info in chunk_entries:
                chunk_name = (
                    chunk_info
                    if isinstance(chunk_info, str)
                    else chunk_info.get("name")
                )
                if not chunk_name:
                    raise ValueError("Missing chunk name in manifest entry.")
                
                chunk_path = folder / chunk_name
                if not chunk_path.exists():
                    raise FileNotFoundError(f"Missing chunk: {chunk_name}")
                
                with open(chunk_path, "rb") as chunk_file:
                    encrypted_data.extend(chunk_file.read())
        except Exception as exc:
            print(f"   ❌ Error reading chunks: {exc}\n")
            return False
        
        print(
            f"   ✓ Reassembled {len(chunk_entries)} chunks ({format_bytes(len(encrypted_data))})"
        )
        
        try:
            if is_encrypted and password:
                decrypted = decrypt_data(bytes(encrypted_data), password)
                original_data = decompress_data(decrypted)
                print(
                    f"   ✓ Decrypted and decompressed → {format_bytes(len(original_data))}"
                )
            else:
                try:
                    original_data = decompress_data(bytes(encrypted_data))
                    print("   ✓ Decompressed (legacy format)")
                except Exception:
                    original_data = bytes(encrypted_data)
                    print("   ✓ No compression (legacy format)")
        except ValueError as exc:
            print(f"   ❌ Decryption failed: {exc}\n")
            return False
        except Exception as exc:
            print(f"   ❌ Unexpected error: {exc}\n")
            return False
        
        try:
            with open(target_path, "wb") as out_file:
                out_file.write(original_data)
        except Exception as exc:
            print(f"   ❌ Error writing file: {exc}\n")
            return False
        
        expected_size = info.get("original_size")
        if expected_size is not None and len(original_data) != expected_size:
            print(
                f"   ⚠️  Warning: Size mismatch (expected {format_bytes(expected_size)}, "
                f"got {format_bytes(len(original_data))})"
            )
        
        print(f"   ✅ Successfully restored to: {target_path.name}\n")
        return True
