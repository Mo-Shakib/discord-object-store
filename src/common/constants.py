"""Constants used throughout the application."""

# Status colors for Discord embeds
STATUS_COLORS = {
    "success": 0x2ECC71,
    "partial": 0xF1C40F,
    "failed": 0xE74C3C,
    "deleted": 0x7F8C8D,
    "unknown": 0x95A5A6,
}

# Legacy manifest file name
LEGACY_MANIFEST = "manifest.json"

# Default chunk size for file slicing (in MB)
DEFAULT_CHUNK_SIZE_MB = 9.5

# Maximum number of concurrent uploads
MAX_CONCURRENT_UPLOADS = 5

# Retry attempts for failed operations
MAX_RETRY_ATTEMPTS = 3

# Rate limit for archive card updates (seconds)
ARCHIVE_CARD_UPDATE_RATE_LIMIT = 1.2
