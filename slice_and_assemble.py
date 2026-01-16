import os
import math
import json
import hashlib
import datetime
import re
import shutil
from pathlib import Path

LEGACY_MANIFEST = "manifest.json"
UPLOAD_FOLDER = Path("/Volumes/Local Drive/DiscordDrive/Uploads")

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
    Slices all files in a folder into hashed chunks and creates a manifest key.
    """
    folder = Path(clean_path(folder_path))
    if not folder.is_dir():
        print(f"Error: {folder} is not a valid directory.")
        return

    chunk_size = int(chunk_size_mb * 1024 * 1024)
    output_base_dir = UPLOAD_FOLDER
    output_base_dir.mkdir(parents=True, exist_ok=True)

    # Manifest to store the 'key' for reassembly
    manifest = {
        "version": "2.1",
        "source_folder": folder.name,
        "files": {},
    }

    files_to_process = [
        f for f in folder.iterdir() if f.is_file() and f.name != ".DS_Store"
    ]
    print(f"Found {len(files_to_process)} files to process.\n")

    total_chunks = 0
    for file_path in files_to_process:
        file_id = get_file_hash(file_path)
        file_size = file_path.stat().st_size
        num_chunks = math.ceil(file_size / chunk_size)
        
        manifest["files"][file_id] = {
            "original_name": file_path.name,
            "total_size": file_size,
            "chunks": []
        }

        print(f"Processing: {file_path.name} -> ID: {file_id}")

        with open(file_path, 'rb') as f:
            for i in range(num_chunks):
                chunk_data = f.read(chunk_size)
                total_chunks += 1
                # Generate an obfuscated chunk name
                chunk_name = f"{total_chunks}-data_{file_id}_{get_chunk_hash(chunk_data)}_{i:04d}.bin"
                chunk_path = output_base_dir / chunk_name
                
                with open(chunk_path, 'wb') as chunk_file:
                    chunk_file.write(chunk_data)
                
                manifest["files"][file_id]["chunks"].append(chunk_name)
        
        print(f"  Generated {num_chunks} hashed chunks.")

    # Save the manifest 'key'
    now = datetime.datetime.now()
    base_manifest_name = build_manifest_name(total_chunks, now)
    manifest_name = base_manifest_name
    manifest_path = output_base_dir / manifest_name
    counter = 1
    while manifest_path.exists():
        stem = base_manifest_name[:-5] if base_manifest_name.lower().endswith(".json") else base_manifest_name
        manifest_name = f"{stem}_{counter}.json"
        manifest_path = output_base_dir / manifest_name
        counter += 1
    with open(manifest_path, 'w') as m_file:
        json.dump(manifest, m_file, indent=4)

    print(f"\n--- Slicing Complete ---")
    print(f"All chunks and the manifest key are in: {output_base_dir}")
    print(f"Keep '{manifest_name}' safe! It is required for reassembly.")

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
            print(f"Debug: JSON files found: {', '.join(sorted(json_candidates))}")
        print(f"Error: No manifest file found in {folder}. Reassembly impossible.")
        return

    unique_paths = {path.resolve(): path for path in manifest_paths}
    manifest_files = sorted(
        unique_paths.values(),
        key=lambda path: path.stat().st_mtime,
    )
    manifest_count = len(manifest_files)

    output_base = folder.parent
    output_base.mkdir(exist_ok=True)

    if manifest_count > 1:
        print(f"Multiple manifests found. Reassembling {manifest_count} manifests.")

    had_errors = False
    for manifest_path in manifest_files:
        try:
            with open(manifest_path, 'r') as m_file:
                manifest = json.load(m_file)
        except Exception as e:
            print(f"⚠️ Failed to read manifest {manifest_path.name}: {e}")
            had_errors = True
            continue

        output_dir = _resolve_output_dir(output_base, manifest, manifest_path, manifest_count)
        output_dir.mkdir(exist_ok=True)

        files = manifest.get("files", {})
        print(f"Found instructions for {len(files)} files in {manifest_path.name}.\n")

        for file_id, info in files.items():
            original_name = info.get("original_name")
            if original_name == ".DS_Store":
                print("Skipping .DS_Store entry in manifest.")
                continue
            if not original_name:
                print(f"  Skipping entry {file_id}: missing original_name")
                had_errors = True
                continue
            chunk_list = info.get("chunks") or []
            target_path = output_dir / original_name

            print(f"Reassembling: {original_name}...")

            try:
                with open(target_path, 'wb') as out_f:
                    for chunk_name in chunk_list:
                        chunk_path = folder / chunk_name
                        if not chunk_path.exists():
                            print(f"  CRITICAL ERROR: Missing chunk {chunk_name}")
                            had_errors = True
                            continue
                        with open(chunk_path, 'rb') as in_f:
                            out_f.write(in_f.read())
                print(f"  Successfully restored to {target_path}")
            except Exception as e:
                print(f"  Error reassembling {original_name}: {e}")
                had_errors = True

    print(f"\n--- Reassembly Complete ---")
    print(f"All files restored to: {output_base}")
    if not had_errors:
        try:
            shutil.rmtree(folder)
            print(f"🗑️ Removed chunks folder: {folder}")
        except OSError as e:
            print(f"⚠️ Could not remove chunks folder {folder}: {e}")

def main():
    print("--- Discord Secure Bulk Slicer & Assembler ---")
    print("1. Slice all files in a FOLDER (Generates Key)")
    print("2. Reassemble files from a CHUNKS folder (Requires Key)")
    
    choice = input("\nSelect an option (1 or 2): ").strip()
    
    if choice == '1':
        path = input("Enter path to the folder containing LARGE files: ").strip()
        slice_folder(path)
    elif choice == '2':
        path = input("Enter path to the processed CHUNKS folder (manifest .json in name): ").strip()
        assemble_from_manifest(path)
    else:
        print("Invalid selection.")

if __name__ == "__main__":
    main()
