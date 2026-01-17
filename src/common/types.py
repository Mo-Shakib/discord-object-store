"""Type definitions and data models."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class ChunkInfo:
    """Information about a file chunk."""
    name: str
    size: int
    index: int


@dataclass
class FileInfo:
    """Information about a file in the archive."""
    original_name: str
    original_size: int
    chunks: List[ChunkInfo] = field(default_factory=list)


@dataclass
class ArchiveMetadata:
    """Metadata for an archive."""
    lot: int
    archive_id: str
    timestamp: str
    status: str = "unknown"
    file_count: Optional[int] = None
    total_size_bytes: Optional[int] = None
    uploaded_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    message_ids: List[int] = field(default_factory=list)
    chunk_count: Optional[int] = None
    files_display: List[str] = field(default_factory=list)
    uploader: Optional[str] = None
    archive_channel_id: Optional[int] = None
    storage_channel_id: Optional[int] = None
    thread_id: Optional[int] = None
    archive_message_id: Optional[int] = None
    errors: Dict[str, str] = field(default_factory=dict)
    progress_text: Optional[str] = None
    legacy: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "lot": self.lot,
            "archive_id": self.archive_id,
            "timestamp": self.timestamp,
            "status": self.status,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "uploaded_files": self.uploaded_files,
            "failed_files": self.failed_files,
            "message_ids": self.message_ids,
            "chunk_count": self.chunk_count,
            "files_display": self.files_display,
            "uploader": self.uploader,
            "archive_channel_id": self.archive_channel_id,
            "storage_channel_id": self.storage_channel_id,
            "thread_id": self.thread_id,
            "archive_message_id": self.archive_message_id,
            "errors": self.errors,
            "progress_text": self.progress_text,
            "legacy": self.legacy,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArchiveMetadata":
        """Create from dictionary."""
        return cls(
            lot=data.get("lot", 0),
            archive_id=data.get("archive_id", "unknown"),
            timestamp=data.get("timestamp", ""),
            status=data.get("status", "unknown"),
            file_count=data.get("file_count"),
            total_size_bytes=data.get("total_size_bytes"),
            uploaded_files=data.get("uploaded_files", []),
            failed_files=data.get("failed_files", []),
            message_ids=data.get("message_ids", []),
            chunk_count=data.get("chunk_count"),
            files_display=data.get("files_display", []),
            uploader=data.get("uploader"),
            archive_channel_id=data.get("archive_channel_id"),
            storage_channel_id=data.get("storage_channel_id"),
            thread_id=data.get("thread_id"),
            archive_message_id=data.get("archive_message_id"),
            errors=data.get("errors", {}),
            progress_text=data.get("progress_text"),
            legacy=data.get("legacy", False),
        )


@dataclass
class LogEntry:
    """Log entry for archive operations."""
    lot: int
    archive_id: str
    timestamp: str
    message_ids: List[int] = field(default_factory=list)
    status: str = "unknown"
    file_count: Optional[int] = None
    total_size_bytes: Optional[int] = None
    uploaded_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    thread_id: Optional[int] = None
    archive_message_id: Optional[int] = None
    archive_channel_id: Optional[int] = None
    storage_channel_id: Optional[int] = None
    chunk_count: Optional[int] = None
    errors: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "lot": self.lot,
            "archive_id": self.archive_id,
            "timestamp": self.timestamp,
            "message_ids": self.message_ids,
            "status": self.status,
            "file_count": self.file_count,
            "total_size_bytes": self.total_size_bytes,
            "uploaded_files": self.uploaded_files,
            "failed_files": self.failed_files,
            "thread_id": self.thread_id,
            "archive_message_id": self.archive_message_id,
            "archive_channel_id": self.archive_channel_id,
            "storage_channel_id": self.storage_channel_id,
            "chunk_count": self.chunk_count,
            "errors": self.errors,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LogEntry":
        """Create from dictionary."""
        return cls(
            lot=data.get("lot", 0),
            archive_id=data.get("archive_id", "unknown"),
            timestamp=data.get("timestamp", ""),
            message_ids=data.get("message_ids", []),
            status=data.get("status", "unknown"),
            file_count=data.get("file_count"),
            total_size_bytes=data.get("total_size_bytes"),
            uploaded_files=data.get("uploaded_files", []),
            failed_files=data.get("failed_files", []),
            thread_id=data.get("thread_id"),
            archive_message_id=data.get("archive_message_id"),
            archive_channel_id=data.get("archive_channel_id"),
            storage_channel_id=data.get("storage_channel_id"),
            chunk_count=data.get("chunk_count"),
            errors=data.get("errors", {}),
        )
