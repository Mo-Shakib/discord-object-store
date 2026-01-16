import os
import math
import json
import hashlib
import datetime
import re
from pathlib import Path

LEGACY_MANIFEST = "manifest.json"

def get_file_hash(file_path):
    """Generates a SHA256 hash for a file's path and name to use as a unique ID."""
    return hashlib.sha256(str(file_path.name).encode()).hexdigest()[:12]

def get_chunk_hash(data):
    """Generates a hash for the actual chunk content."""
    return hashlib.sha256(data).hexdigest()[:16]

def clean_path(path_str):
    """Cleans input paths from quotes and extra spaces."""
    return str(path_str).strip().strip("'").strip('"')

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
    output_base_dir = folder.parent / f"{folder.name}_processed_chunks"
    output_base_dir.mkdir(exist_ok=True)

    # Manifest to store the 'key' for reassembly
    manifest = {
        "version": "2.0",
        "files": {}
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
    manifest_name = build_manifest_name(total_chunks)
    manifest_path = output_base_dir / manifest_name
    with open(manifest_path, 'w') as m_file:
        json.dump(manifest, m_file, indent=4)

    print(f"\n--- Slicing Complete ---")
    print(f"All chunks and the manifest key are in: {output_base_dir}")
    print(f"Keep '{manifest_name}' safe! It is required for reassembly.")

def assemble_from_manifest(chunks_folder_path):
    """
    Assembles files using a manifest file found in the chunks folder.
    """
    folder = resolve_chunks_folder(chunks_folder_path)
    if not folder.exists():
        print(
            f"Error: Folder not found: {folder}. "
            "Expected format: '[Archive] #DDMMYY-Number'."
        )
        return
    manifest_path, manifest_count = find_manifest_file(folder)

    if not manifest_path:
        json_candidates = [p.name for p in folder.iterdir() if p.is_file() and p.name.lower().endswith(".json")]
        if json_candidates:
            print(f"Debug: JSON files found: {', '.join(sorted(json_candidates))}")
        print(f"Error: No manifest file found in {folder}. Reassembly impossible.")
        return

    with open(manifest_path, 'r') as m_file:
        manifest = json.load(m_file)

    if manifest_count > 1:
        print(f"Multiple manifests found. Using most recent: {manifest_path.name}")

    output_dir = folder / "REASSEMBLED_FILES"
    output_dir.mkdir(exist_ok=True)

    print(f"Found instructions for {len(manifest['files'])} files.\n")

    for file_id, info in manifest["files"].items():
        original_name = info["original_name"]
        if original_name == ".DS_Store":
            print("Skipping .DS_Store entry in manifest.")
            continue
        chunk_list = info["chunks"]
        target_path = output_dir / original_name

        print(f"Reassembling: {original_name}...")
        
        try:
            with open(target_path, 'wb') as out_f:
                for chunk_name in chunk_list:
                    chunk_path = folder / chunk_name
                    if not chunk_path.exists():
                        print(f"  CRITICAL ERROR: Missing chunk {chunk_name}")
                        continue
                    with open(chunk_path, 'rb') as in_f:
                        out_f.write(in_f.read())
            print(f"  Successfully restored to {target_path.name}")
        except Exception as e:
            print(f"  Error reassembling {original_name}: {e}")

    print(f"\n--- Reassembly Complete ---")
    print(f"All files restored to: {output_dir}")

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
