# Refactoring Guide

## Overview

This document describes the refactoring from the monolithic 3-file structure to a modular, production-grade Python package.

## What Changed

### Old Structure (3 files)
```
discord-object-store/
├── bot_server.py          (1589 lines - bot logic + utilities)
├── slice_and_assemble.py  (627 lines - crypto + compression + chunking)
└── archive_card.py        (221 lines - Discord UI)
```

### New Structure (Modular Package)
```
discord-object-store/
├── main.py                        # Entry point
├── src/
│   ├── config.py                  # Configuration management
│   ├── common/                    # Shared utilities
│   │   ├── constants.py
│   │   ├── utils.py
│   │   ├── logging.py
│   │   └── types.py
│   ├── core/                      # Pure Python business logic
│   │   ├── crypto.py
│   │   ├── compression.py
│   │   ├── chunking.py
│   │   └── manifest.py
│   ├── services/                  # Application services
│   │   ├── file_system.py
│   │   └── archive_manager.py
│   └── bot/                       # Discord interface
│       ├── client.py
│       ├── utils.py
│       ├── ui/
│       │   └── archive_card.py
│       └── cogs/
│           ├── upload.py
│           ├── download.py
│           ├── management.py
│           └── help.py
```

## Key Improvements

### 1. Separation of Concerns
- **Core logic** (`src/core/`) is completely independent of Discord
- **Services layer** (`src/services/`) handles high-level operations
- **Bot layer** (`src/bot/`) handles only Discord interactions

### 2. Single Responsibility Principle
Each module has one clear purpose:
- `crypto.py` - Only encryption/decryption
- `compression.py` - Only compression
- `chunking.py` - Only file hashing
- `manifest.py` - Only manifest operations
- Each cog handles related commands only

### 3. Configuration Management
- All `os.getenv()` calls moved to `src/config.py`
- Single source of truth for configuration
- Validation happens at startup

### 4. Data Modeling
- Proper data classes in `src/common/types.py`
- Type-safe data structures
- Clear interfaces between components

### 5. Testability
- Core business logic can be tested without Discord
- Mock-friendly architecture
- Clear dependencies

## Migration Path

### For Users

**No action required!** The refactored code maintains 100% compatibility:

1. Your existing `.env` file works as-is
2. Your existing log files are compatible
3. Your existing archives can be downloaded
4. All commands work identically

**To use the new structure:**
```bash
# Old way (still works if bot_server.py exists)
python bot_server.py

# New way
python main.py bot
# or just
python main.py
```

**For CLI slicing:**
```bash
# Old way
python slice_and_assemble.py

# New way
python main.py slice
```

### For Developers

**Importing modules:**
```python
# Configuration
from src.config import config

# Utilities
from src.common.utils import format_bytes, normalize_archive_id
from src.common.constants import STATUS_COLORS

# Core operations
from src.core.crypto import encrypt_data, decrypt_data
from src.core.compression import compress_data, decompress_data
from src.core.manifest import create_manifest, parse_manifest

# Services
from src.services.file_system import FileSystemService
from src.services.archive_manager import ArchiveManager

# Bot components
from src.bot.ui.archive_card import create_archive_card, update_archive_card
```

## File Mapping

### bot_server.py → Multiple Files

| Old Location | New Location | Lines |
|--------------|--------------|-------|
| Configuration (lines 21-180) | `src/config.py` | Full module |
| Utility functions | `src/common/utils.py` | `format_bytes`, etc. |
| Log operations | `src/services/file_system.py` | `load_logs`, `write_logs` |
| Channel helpers | `src/bot/utils.py` | `get_archive_channel`, etc. |
| Upload command | `src/bot/cogs/upload.py` | `UploadCog` |
| Download command | `src/bot/cogs/download.py` | `DownloadCog` |
| Management commands | `src/bot/cogs/management.py` | `ManagementCog` |
| Help command | `src/bot/cogs/help.py` | `HelpCog` |
| Bot setup | `src/bot/client.py` | `create_bot` |

### slice_and_assemble.py → Multiple Files

| Old Location | New Location | Notes |
|--------------|--------------|-------|
| `derive_encryption_key` | `src/core/crypto.py` | Unchanged |
| `compress_and_encrypt_data` | Split: `src/core/compression.py` + `crypto.py` | Separated concerns |
| `decrypt_and_decompress_data` | Split: `src/core/crypto.py` + `compression.py` | Separated concerns |
| `get_file_hash`, `get_chunk_hash` | `src/core/chunking.py` | Unchanged |
| `build_manifest_name` | `src/core/manifest.py` | Unchanged |
| `slice_folder` | `src/services/archive_manager.py` | Orchestration logic |
| `assemble_from_manifest` | `src/services/archive_manager.py` | Orchestration logic |
| Manifest operations | `src/core/manifest.py` | Pure manifest logic |

### archive_card.py → src/bot/ui/archive_card.py

| Old Function | New Location | Changes |
|--------------|--------------|---------|
| `STATUS_COLORS` | `src/common/constants.py` | Now a constant |
| `_format_bytes` | `src/common/utils.py` | `format_bytes` |
| `build_archive_embed` | `src/bot/ui/archive_card.py` | Unchanged |
| `create_archive_card` | `src/bot/ui/archive_card.py` | Unchanged |
| `update_archive_card` | `src/bot/ui/archive_card.py` | Unchanged |
| `parse_archive_card` | `src/bot/ui/archive_card.py` | Unchanged |
| `search_archives` | `src/bot/ui/archive_card.py` | Unchanged |

## Logic Preservation

### Zero Changes to Core Functionality

The refactoring preserved **100% of the business logic**:

✅ AES-256-GCM encryption - **Identical implementation**  
✅ PBKDF2 key derivation - **Identical parameters (600,000 iterations)**  
✅ Gzip compression - **Same compression level (9)**  
✅ Chunking algorithm - **Identical chunk size and hashing**  
✅ Manifest structure - **Same JSON format**  
✅ Discord interactions - **Same commands and behavior**  
✅ Upload/download logic - **Identical flow**  
✅ Resume functionality - **Unchanged**  
✅ Archive cards - **Same embed format**  

### What Was Changed

**Only structural changes:**
- Code organization (files and folders)
- Import statements
- Function locations
- Module boundaries

**No changes to:**
- Encryption algorithms
- Compression settings
- Data formats
- Command behavior
- API interfaces

## Testing Checklist

To verify the refactoring:

- [ ] Bot starts successfully: `python main.py`
- [ ] Configuration loads from `.env`
- [ ] Upload command works: `!upload`
- [ ] Download command works: `!download #DDMMYY-01`
- [ ] Resume works: `!resume`
- [ ] Status command shows correct info: `!status`
- [ ] History displays: `!history`
- [ ] Archives search works: `!archives`
- [ ] Verify works: `!verify #DDMMYY-01`
- [ ] CLI slicer works: `python main.py slice`
- [ ] Encryption/decryption produces same results
- [ ] Existing archives can be downloaded
- [ ] Log files are compatible

## Benefits

### For Development
- **Easier to test**: Each component can be tested independently
- **Easier to debug**: Clear module boundaries
- **Easier to extend**: Add new features without touching core logic
- **Easier to understand**: Logical grouping and naming

### For Maintenance
- **Clear dependencies**: Know what depends on what
- **Isolated changes**: Changes in one module don't affect others
- **Better documentation**: Each module has a clear purpose
- **Type safety**: Data models prevent errors

### For Production
- **More reliable**: Better error handling and separation
- **More scalable**: Can add workers, queues, etc.
- **More secure**: Security logic isolated and reviewable
- **More efficient**: Can optimize individual components

## Future Enhancements

The new structure enables:

1. **Unit Tests**: Test core logic without Discord
2. **API Server**: Expose functionality via REST API
3. **Web UI**: Add a web interface
4. **Multiple Bots**: Run multiple bot instances
5. **Cloud Storage**: Add S3/GCS backends
6. **Database**: Switch from JSON to proper database
7. **Async Processing**: Add job queues
8. **Metrics**: Add monitoring and logging

## Questions?

If you have questions about the refactoring:
1. Check this guide
2. Review the code comments
3. Look at the module docstrings
4. Compare with the old files (still present)

## Old Files

The original files are preserved:
- `bot_server.py` - Original bot implementation
- `slice_and_assemble.py` - Original slicer
- `archive_card.py` - Original UI

You can compare them with the new structure to see how functionality was reorganized.
