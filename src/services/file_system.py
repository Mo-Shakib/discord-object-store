"""Local file I/O and directory management."""

import os
import glob
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..config import config
from ..common.utils import dedupe_paths
from ..core.manifest import list_manifest_files


class FileSystemService:
    """Service for file system operations."""
    
    @staticmethod
    def list_upload_files() -> List[str]:
        """
        List all files in the upload folder ready for upload.
        
        Returns:
            List of file paths
        """
        bin_files = glob.glob(os.path.join(config.UPLOAD_FOLDER, "*.bin"))
        manifest_files = [
            str(p) for p in list_manifest_files(Path(config.UPLOAD_FOLDER))
        ]
        return dedupe_paths(bin_files + manifest_files)
    
    @staticmethod
    def read_manifest_original_names(folder: str) -> List[str]:
        """
        Read original file names from manifest files in a folder.
        
        Args:
            folder: Folder path containing manifests
        
        Returns:
            List of original file names
        """
        names = []
        folder_path = Path(folder)
        
        for manifest_path in list_manifest_files(folder_path):
            try:
                with open(manifest_path, "r") as file:
                    manifest = json.load(file)
                files = manifest.get("files", {})
                for info in files.values():
                    original = info.get("original_name")
                    if original:
                        names.append(original)
            except Exception:
                continue
        
        return dedupe_paths(names)
    
    @staticmethod
    def calculate_total_size(file_paths: List[str]) -> int:
        """
        Calculate total size of files.
        
        Args:
            file_paths: List of file paths
        
        Returns:
            Total size in bytes
        """
        total = 0
        for path in file_paths:
            try:
                total += os.path.getsize(path)
            except OSError:
                continue
        return total
    
    @staticmethod
    def load_logs() -> List[Dict[str, Any]]:
        """
        Load logs from the log file.
        
        Returns:
            List of log entries
        """
        if not os.path.exists(config.LOG_FILE):
            return []
        
        try:
            with open(config.LOG_FILE, 'r') as f:
                logs = json.load(f)
            if isinstance(logs, list):
                return logs
        except Exception:
            pass
        
        return []
    
    @staticmethod
    def write_logs(logs: List[Dict[str, Any]]) -> None:
        """
        Write logs to the log file.
        
        Args:
            logs: List of log entries
        """
        with open(config.LOG_FILE, 'w') as f:
            json.dump(logs, f, indent=4)
    
    @staticmethod
    def get_next_lot() -> int:
        """
        Get the next available lot number.
        
        Returns:
            Next lot number
        """
        logs = FileSystemService.load_logs()
        if not logs:
            return 1
        return max(int(entry.get('lot', 0)) for entry in logs) + 1
    
    @staticmethod
    def find_log_index(
        logs: List[Dict[str, Any]],
        archive_id: Optional[str] = None,
        lot: Optional[int] = None
    ) -> Optional[int]:
        """
        Find the index of a log entry.
        
        Args:
            logs: List of log entries
            archive_id: Archive ID to search for
            lot: Lot number to search for
        
        Returns:
            Index of the log entry, or None if not found
        """
        from ..common.utils import normalize_archive_id
        
        normalized_target = normalize_archive_id(archive_id) if archive_id else None
        
        for index, entry in enumerate(logs):
            if normalized_target:
                entry_id = normalize_archive_id(
                    entry.get("archive_id")
                ) or entry.get("archive_id")
                if entry_id == normalized_target:
                    return index
            if lot is not None and entry.get("lot") == lot:
                return index
        
        return None
    
    @staticmethod
    def get_archive_id_from_entry(entry: Dict[str, Any]) -> str:
        """
        Get archive ID from a log entry.
        
        Args:
            entry: Log entry
        
        Returns:
            Archive ID
        """
        from ..common.utils import normalize_archive_id, build_archive_id
        
        archive_id = normalize_archive_id(entry.get("archive_id"))
        if archive_id:
            return archive_id
        
        lot = entry.get("lot")
        if lot is None:
            return "unknown"
        
        return build_archive_id(lot, entry.get("timestamp"))
    
    @staticmethod
    def get_archive_id_by_lot(logs: List[Dict[str, Any]], lot_num: int) -> str:
        """
        Get archive ID by lot number.
        
        Args:
            logs: List of log entries
            lot_num: Lot number
        
        Returns:
            Archive ID
        """
        for entry in logs:
            if entry.get("lot") == lot_num:
                return FileSystemService.get_archive_id_from_entry(entry)
        return f"Lot {lot_num}"
