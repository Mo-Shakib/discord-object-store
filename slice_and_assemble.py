import os
import math
import json
import hashlib
import datetime
import re
import shutil
import gzip
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

LEGACY_MANIFEST = "manifest.json"

BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path):
    if not path.exists():
        return
    with path.open("r") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


ENV_FILE = BASE_DIR / ".env"
load_env_file(ENV_FILE)


def resolve_env_path(env_key, default_value):
    raw_value = os.getenv(env_key)
    value = raw_value if raw_value else default_value
    return Path(os.path.expanduser(value)).resolve()


UPLOAD_FOLDER = resolve_env_path(
    "DISCORD_DRIVE_UPLOAD_PATH",
    "/Volumes/Local Drive/DiscordDrive/Uploads",
)


def format_bytes(num_bytes):
    """Convert bytes to human readable format."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024.0 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{int(num_bytes)} B"


def derive_encryption_key(password: str, salt: bytes) -> bytes:
    """
    Derive a 256-bit encryption key from password using PBKDF2.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600000,
    )
    return kdf.derive(password.encode())


def compress_and_encrypt_data(data: bytes, password: str) -> bytes:
    """
    Compress data using gzip, then encrypt using AES-256-GCM.
    Returns: salt (16 bytes) + nonce (12 bytes) + ciphertext.
    """
    compressed = gzip.compress(data, compresslevel=9)
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_encryption_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, compressed, None)
    return salt + nonce + ciphertext


def decrypt_and_decompress_data(data: bytes, password: str) -> bytes:
    """
    Decrypt AES-256-GCM payload, then decompress gzip data.
    """
    if len(data) < 28:
        raise ValueError("Data too short to be encrypted.")
    salt = data[:16]
    nonce = data[16:28]
    ciphertext = data[28:]
    key = derive_encryption_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        compressed = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise ValueError(
            "Decryption failed. Wrong password or corrupted data."
        ) from exc
    try:
        return gzip.decompress(compressed)
    except Exception as exc:
        raise ValueError(
            "Decompression failed. Data may be corrupted.") from exc


def get_file_hash(file_path):
    """Generates a SHA256 hash for a file's path and name to use as a unique ID."""
    return hashlib.sha256(str(file_path.name).encode()).hexdigest()[:12]


def get_chunk_hash(data):
    """Generates a hash for the actual chunk content."""
    return hashlib.sha256(data).hexdigest()[:16]


def clean_path(path_str):
    """Cleans input paths from quotes and extra spaces."""
    cleaned = str(path_str).strip().strip("'").strip('"')
    cleaned = cleaned.replace("\\ ", " ")
    cleaned = os.path.expanduser(cleaned)
    return cleaned


def build_manifest_name(total_chunks, timestamp=None):
    """Builds a manifest name like 123-manifest_HHMMSS_DDMMYY.json."""
    now = timestamp or datetime.datetime.now()
    time_part = now.strftime("%H%M%S")
    date_part = now.strftime("%d%m%y")
    return f"{total_chunks}-manifest_{time_part}_{date_part}.json"


def list_manifest_files(folder):
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


def resolve_chunks_folder(path_str):
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
        candidate_names.extend(
            [
                f"[Archive] #{archive_id}",
                f"[Archive] {archive_id}",
                f"#{archive_id}",
                archive_id,
            ]
        )

    for candidate_name in candidate_names:
        candidate_path = parent / candidate_name
        if candidate_path.exists():
            return candidate_path

    if archive_id:
        for candidate in parent.glob(f"*{archive_id}*"):
            if candidate.is_dir():
                return candidate

    return folder


def find_manifest_file(folder):
    """Find the most recent manifest file in the folder."""
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


def slice_folder(folder_path, chunk_size_mb=9.5):
    """
    Slices all files in a folder into compressed and encrypted chunks.
    """
    folder = Path(clean_path(folder_path))
    if not folder.is_dir():
        print(f"Error: {folder} is not a valid directory.")
        return

    password = os.getenv("USER_KEY")
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
    output_base_dir = UPLOAD_FOLDER
    output_base_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "version": "3.1",
        "encrypted": True,
        "compression": "gzip-9",
        "encryption_algorithm": "AES-256-GCM",
        "kdf": "PBKDF2-SHA256-600000",
        "chunking": "per-chunk",
        "encryption_scope": "chunk",
        "source_folder": folder.name,
        "files": {},
    }

    files_to_process = [
        f for f in folder.iterdir() if f.is_file() and f.name != ".DS_Store"
    ]
    print(f"Found {len(files_to_process)} files to process.")
    print("🔒 Encryption: ENABLED (AES-256-GCM)")
    print("🗜️  Compression: ENABLED (gzip-9)\n")

    total_chunks = 0
    total_original_size = 0
    total_processed_size = 0

    for file_path in files_to_process:
        file_id = get_file_hash(file_path)
        file_size = file_path.stat().st_size
        total_original_size += file_size

        manifest["files"][file_id] = {
            "original_name": file_path.name,
            "original_size": file_size,
            "chunks": [],
        }

        print(f"Processing: {file_path.name}")
        print(f"  Original size: {format_bytes(file_size)}")

        processed_size = 0
        num_chunks = 0

        def _process_chunk(raw_chunk, chunk_index):
            nonlocal total_chunks, total_processed_size, processed_size, num_chunks
            try:
                processed_chunk = compress_and_encrypt_data(
                    raw_chunk, password)
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

            manifest["files"][file_id]["chunks"].append(
                {"name": chunk_name, "size": len(
                    processed_chunk), "index": chunk_index}
            )
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

    manifest["total_original_size"] = total_original_size
    manifest["total_processed_size"] = total_processed_size
    manifest["total_chunks"] = total_chunks
    if total_original_size > 0:
        manifest["space_saved_percent"] = round(
            (1 - total_processed_size / total_original_size) * 100, 2
        )
    else:
        manifest["space_saved_percent"] = 0.0

    now = datetime.datetime.now()
    base_manifest_name = build_manifest_name(total_chunks, now)
    manifest_name = base_manifest_name
    manifest_path = output_base_dir / manifest_name
    counter = 1
    while manifest_path.exists():
        stem = base_manifest_name[:-5] if base_manifest_name.lower().endswith(
            ".json") else base_manifest_name
        manifest_name = f"{stem}_{counter}.json"
        manifest_path = output_base_dir / manifest_name
        counter += 1
    with open(manifest_path, "w") as m_file:
        json.dump(manifest, m_file, indent=4)

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
    print(f"   1. Manifest file: {manifest_name}")
    print("   2. USER_KEY from .env (required for decryption)")
    print(f"{'=' * 50}\n")


def _resolve_output_dir(base_dir, manifest, manifest_path, manifest_count):
    source_folder = manifest.get("source_folder")
    if source_folder:
        return base_dir / source_folder
    if manifest_count > 1:
        return base_dir / f"restored_{manifest_path.stem}"
    return base_dir


def assemble_from_manifest(chunks_folder_path):
    """
    Assembles files using one or more manifest files found in the chunks folder.
    """
    folder = resolve_chunks_folder(chunks_folder_path)
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
                f"Debug: JSON files found: {', '.join(sorted(json_candidates))}")
        print(
            f"Error: No manifest file found in {folder}. Reassembly impossible.")
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
            f"Multiple manifests found. Reassembling {manifest_count} manifests.")

    had_errors = False
    for manifest_path in manifest_files:
        try:
            with open(manifest_path, "r") as m_file:
                manifest = json.load(m_file)
        except Exception as exc:
            print(f"⚠️ Failed to read manifest {manifest_path.name}: {exc}")
            had_errors = True
            continue

        is_encrypted = bool(manifest.get("encrypted"))
        encryption_scope = manifest.get("encryption_scope", "file")
        if is_encrypted:
            password = os.getenv("USER_KEY")
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

        output_dir = _resolve_output_dir(
            output_base, manifest, manifest_path, manifest_count)
        output_dir.mkdir(exist_ok=True)

        files = manifest.get("files", {})
        print(
            f"\n{'=' * 50}")
        print(
            f"Starting reassembly of {len(files)} file(s) from {manifest_path.name}")
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
                                raise ValueError(
                                    "Missing chunk name in manifest entry.")
                            chunk_path = folder / chunk_name
                            if not chunk_path.exists():
                                raise FileNotFoundError(
                                    f"Missing chunk: {chunk_name}")
                            with open(chunk_path, "rb") as chunk_file:
                                encrypted_chunk = chunk_file.read()
                            try:
                                original_chunk = decrypt_and_decompress_data(
                                    encrypted_chunk, password
                                )
                            except ValueError as exc:
                                raise ValueError(
                                    f"Decryption failed for {chunk_name}: {exc}"
                                ) from exc
                            out_file.write(original_chunk)
                            total_written += len(original_chunk)
                except Exception as exc:
                    print(f"   ❌ Error reassembling chunks: {exc}\n")
                    had_errors = True
                    continue

                print(
                    f"   ✓ Reassembled {len(chunk_entries)} chunks ({format_bytes(total_written)})"
                )
                print(
                    f"   ✓ Decrypted and decompressed per chunk"
                )
                expected_size = info.get("original_size")
                if expected_size is not None and total_written != expected_size:
                    print(
                        f"   ⚠️  Warning: Size mismatch (expected {format_bytes(expected_size)}, "
                        f"got {format_bytes(total_written)})"
                    )

                print(f"   ✅ Successfully restored to: {target_path.name}\n")
                continue

            encrypted_data = bytearray()
            try:
                for chunk_info in chunk_entries:
                    chunk_name = (
                        chunk_info
                        if isinstance(chunk_info, str)
                        else chunk_info.get("name")
                    )
                    if not chunk_name:
                        raise ValueError(
                            "Missing chunk name in manifest entry.")
                    chunk_path = folder / chunk_name
                    if not chunk_path.exists():
                        raise FileNotFoundError(f"Missing chunk: {chunk_name}")
                    with open(chunk_path, "rb") as chunk_file:
                        encrypted_data.extend(chunk_file.read())
            except Exception as exc:
                print(f"   ❌ Error reading chunks: {exc}\n")
                had_errors = True
                continue

            print(
                f"   ✓ Reassembled {len(chunk_entries)} chunks ({format_bytes(len(encrypted_data))})"
            )

            try:
                if is_encrypted and password:
                    original_data = decrypt_and_decompress_data(
                        bytes(encrypted_data), password
                    )
                    print(
                        f"   ✓ Decrypted and decompressed → {format_bytes(len(original_data))}"
                    )
                else:
                    try:
                        original_data = gzip.decompress(bytes(encrypted_data))
                        print("   ✓ Decompressed (legacy format)")
                    except Exception:
                        original_data = bytes(encrypted_data)
                        print("   ✓ No compression (legacy format)")
            except ValueError as exc:
                print(f"   ❌ Decryption failed: {exc}\n")
                had_errors = True
                continue
            except Exception as exc:
                print(f"   ❌ Unexpected error: {exc}\n")
                had_errors = True
                continue

            try:
                with open(target_path, "wb") as out_file:
                    out_file.write(original_data)
            except Exception as exc:
                print(f"   ❌ Error writing file: {exc}\n")
                had_errors = True
                continue

            expected_size = info.get("original_size")
            if expected_size is not None and len(original_data) != expected_size:
                print(
                    f"   ⚠️  Warning: Size mismatch (expected {format_bytes(expected_size)}, "
                    f"got {format_bytes(len(original_data))})"
                )

            print(f"   ✅ Successfully restored to: {target_path.name}\n")

    print(f"\n--- Reassembly Complete ---")
    print(f"All files restored to: {output_base}")
    if not had_errors:
        try:
            shutil.rmtree(folder)
            print(f"🗑️ Removed chunks folder: {folder}")
        except OSError as exc:
            print(f"⚠️ Could not remove chunks folder {folder}: {exc}")


def main():
    print("--- Discord Secure Bulk Slicer & Assembler ---")
    print("1. Slice all files in a FOLDER (Generates Key)")
    print("2. Reassemble files from a CHUNKS folder (Requires Key)")

    choice = input("\nSelect an option (1 or 2): ").strip()

    if choice == '1':
        path = input(
            "Enter path to the folder containing LARGE files: ").strip()
        slice_folder(path)
    elif choice == '2':
        path = input(
            "Enter path to the processed CHUNKS folder (manifest .json in name): ").strip()
        assemble_from_manifest(path)
    else:
        print("Invalid selection.")


if __name__ == "__main__":
    main()
