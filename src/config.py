"""Centralized configuration management for Discord Object Store."""

import os
from pathlib import Path
from typing import Optional


class Config:
    """Configuration class for Discord Object Store."""
    
    def __init__(self):
        """Initialize configuration by loading environment variables."""
        self.BASE_DIR = Path(__file__).resolve().parent.parent
        
        # Load .env file if it exists
        self._load_env_file()
        
        # Discord Configuration
        self.DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
        self.LOG_CHANNEL_ID = self._parse_optional_int("DISCORD_DRIVE_LOG_CHANNEL_ID")
        self.ARCHIVE_CHANNEL_ID = self._parse_required_int("DISCORD_DRIVE_ARCHIVE_CHANNEL_ID")
        self.STORAGE_CHANNEL_ID = self._parse_optional_int(
            "DISCORD_DRIVE_STORAGE_CHANNEL_ID",
            fallback_env_key="STORAGE_CHANNEL_ID"
        )
        self.DATABASE_CHANNEL_ID = self._parse_optional_int(
            "DISCORD_DRIVE_DATABASE",
            fallback_env_key="DISCORD_DRIVE_DATABASE_CHANNEL_ID"
        )
        
        # Encryption Configuration
        self.USER_KEY = os.getenv("USER_KEY")
        
        # Path Configuration
        self.DRIVE_PATH = self._resolve_env_path(
            "DISCORD_DRIVE_EXTERNAL_DRIVE_PATH",
            "/Volumes/Local Drive"
        )
        self.UPLOAD_FOLDER = self._resolve_env_path(
            "DISCORD_DRIVE_UPLOAD_PATH",
            os.path.join(self.DRIVE_PATH, "DiscordDrive", "Uploads")
        )
        self.DOWNLOAD_FOLDER = self._resolve_env_path(
            "DISCORD_DRIVE_DOWNLOAD_PATH",
            os.path.join(self.DRIVE_PATH, "DiscordDrive", "Downloads")
        )
        
        # Log File Configuration
        self.DEFAULT_LOG_DIR = os.path.join(self.BASE_DIR, "logs")
        self.DEFAULT_LOG_FILE = os.path.join(self.DEFAULT_LOG_DIR, "discord-drive-history.json")
        self.LEGACY_LOG_FILE = os.path.expanduser("~/discord-drive-history.json")
        self.LOG_FILE = self._resolve_log_file()
        
        # Manifest Configuration
        self.LEGACY_MANIFEST = "manifest.json"
        
        # Validate configuration
        self._validate()
    
    def _load_env_file(self):
        """Load environment variables from .env file."""
        env_file = self.BASE_DIR / ".env"
        if not env_file.exists():
            return
        
        with open(env_file, 'r') as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    
    def _resolve_env_path(self, env_key: str, default_value: str) -> str:
        """Resolve an environment variable path with expansion."""
        raw_value = os.getenv(env_key)
        value = raw_value if raw_value else default_value
        return os.path.abspath(os.path.expanduser(value))
    
    def _parse_optional_int(self, env_key: str, fallback_env_key: Optional[str] = None) -> Optional[int]:
        """Parse an optional integer from environment variable."""
        raw = os.getenv(env_key)
        if (raw is None or raw == "") and fallback_env_key:
            raw = os.getenv(fallback_env_key)
        if raw is None or raw == "":
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    
    def _parse_required_int(self, env_key: str) -> int:
        """Parse a required integer from environment variable."""
        value = self._parse_optional_int(env_key)
        if value is None:
            raise SystemExit(
                f"❌ {env_key} not set or invalid. Add it to .env or your environment."
            )
        return value
    
    def _resolve_log_file(self) -> str:
        """Resolve the log file path."""
        env_path = os.getenv("DISCORD_DRIVE_LOG_FILE")
        if env_path:
            return os.path.abspath(os.path.expanduser(env_path))
        if os.path.exists(self.LEGACY_LOG_FILE):
            return self.LEGACY_LOG_FILE
        return self.DEFAULT_LOG_FILE
    
    def _validate(self):
        """Validate required configuration."""
        if not self.DISCORD_BOT_TOKEN:
            raise SystemExit(
                "❌ DISCORD_BOT_TOKEN not set. Add it to .env or your environment."
            )
        
        if not self.USER_KEY:
            print("⚠️ WARNING: USER_KEY not set in .env - files will NOT be encrypted!")
            print("⚠️ Add USER_KEY=your_secure_password to .env file")
        
        # Create log directory if needed
        log_dir = os.path.dirname(self.LOG_FILE)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        print(f"🧭 Log file path: {os.path.abspath(self.LOG_FILE)}")
        
        # Check drive existence only if using default paths
        using_default_drive_paths = not (
            os.getenv("DISCORD_DRIVE_UPLOAD_PATH")
            or os.getenv("DISCORD_DRIVE_DOWNLOAD_PATH")
        )
        
        if using_default_drive_paths and not os.path.exists(self.DRIVE_PATH):
            print(
                f"❌ External drive not found at '{self.DRIVE_PATH}'. "
                "Please check the connection."
            )
        else:
            os.makedirs(self.UPLOAD_FOLDER, exist_ok=True)
            os.makedirs(self.DOWNLOAD_FOLDER, exist_ok=True)
            print("✅ Upload/Download folders ready.")


# Global configuration instance
config = Config()
