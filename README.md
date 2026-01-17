# Discord Object Store

A production-grade, secure object storage system using Discord as a backend. Features AES-256-GCM encryption, Gzip compression, and a modular Python architecture.

## Features

- **🔒 Security**: AES-256-GCM encryption with PBKDF2 key derivation
- **🗜️ Compression**: Gzip-9 compression for optimal storage efficiency
- **📦 Chunking**: Intelligent file splitting for Discord's upload limits
- **🤖 Bot Interface**: Full Discord bot with resume capabilities
- **📊 Archive Management**: Track, verify, and manage all uploads
- **🔄 Resumable**: Failed uploads/downloads can be resumed
- **🏗️ Modular Architecture**: Clean separation of concerns for maintainability

## Architecture

```
discord_object_store/
├── main.py                    # Entry point (bot or CLI)
├── src/
│   ├── config.py             # Centralized configuration
│   ├── common/               # Shared utilities
│   │   ├── constants.py
│   │   ├── utils.py
│   │   ├── logging.py
│   │   └── types.py          # Data models
│   ├── core/                 # Core business logic (pure Python)
│   │   ├── crypto.py         # AES-GCM encryption
│   │   ├── compression.py    # Gzip compression
│   │   ├── chunking.py       # File chunking
│   │   └── manifest.py       # Manifest handling
│   ├── services/             # Application services
│   │   ├── file_system.py    # File I/O operations
│   │   └── archive_manager.py # Slicing/assembly orchestration
│   └── bot/                  # Discord interface
│       ├── client.py         # Bot setup
│       ├── utils.py          # Bot utilities
│       ├── ui/
│       │   └── archive_card.py # Discord embeds
│       └── cogs/             # Command modules
│           ├── upload.py
│           ├── download.py
│           ├── management.py
│           └── help.py
```

## Installation

### Prerequisites

- Python 3.9 or higher
- Discord bot token
- External drive (optional, paths are configurable)

### Setup

1. **Clone the repository**
   ```bash
   cd /path/to/discord-object-store
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Create .env file**
   ```bash
   cp .env.example .env
   ```

4. **Configure environment variables in `.env`**
   ```env
   # Required
   DISCORD_BOT_TOKEN=your_bot_token_here
   DISCORD_DRIVE_ARCHIVE_CHANNEL_ID=123456789
   USER_KEY=your_secure_encryption_key
   
   # Optional
   DISCORD_DRIVE_LOG_CHANNEL_ID=123456789
   DISCORD_DRIVE_STORAGE_CHANNEL_ID=123456789
   DISCORD_DRIVE_DATABASE_CHANNEL_ID=123456789
   DISCORD_DRIVE_UPLOAD_PATH=/custom/upload/path
   DISCORD_DRIVE_DOWNLOAD_PATH=/custom/download/path
   DISCORD_DRIVE_LOG_FILE=/custom/log/path/history.json
   ```

## Usage

### Discord Bot Mode

Start the bot:
```bash
python main.py bot
# or simply
python main.py
```

#### Bot Commands

- `!upload` — Upload files from the upload folder
- `!download #DDMMYY-01 [#DDMMYY-02]` — Download archive(s)
- `!resume [archive_id]` — Resume a failed upload
- `!status` — Show bot status and stats
- `!history` — Show recent archives
- `!archives [query]` — Search archives
- `!verify <archive_id>` — Verify archive integrity
- `!help` — Show help message

**Admin Commands:**
- `!rebuild-log` — Rebuild log from archive channel
- `!migrate-legacy` — Migrate old logs to new format
- `!cleanup <archive_id>` — Delete archive and thread

### CLI Slicer Mode

For standalone file slicing/assembly without the bot:
```bash
python main.py slice
```

This provides an interactive menu to:
1. Slice files into encrypted chunks
2. Reassemble files from chunks

## Workflow

### Uploading Files

1. Place files in the upload folder (default: `/Volumes/Local Drive/DiscordDrive/Uploads`)
2. Run the slicer to encrypt and chunk files:
   ```bash
   python main.py slice
   ```
3. Upload to Discord:
   ```
   !upload
   ```

### Downloading Files

```
!download #171226-01
```

Files are automatically reassembled and decrypted after download.

## Security

- **Encryption**: AES-256-GCM (Galois/Counter Mode)
- **Key Derivation**: PBKDF2-HMAC-SHA256 with 600,000 iterations
- **Per-Chunk Encryption**: Each chunk has unique salt and nonce
- **Compression**: Applied before encryption to reduce storage

### Important Security Notes

⚠️ **Keep your USER_KEY secure!** Without it, files cannot be decrypted.

⚠️ **Backup your manifests!** They contain the file structure information.

## Configuration

All configuration is centralized in `src/config.py`. Environment variables are loaded from `.env`:

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | Yes | Discord bot token |
| `DISCORD_DRIVE_ARCHIVE_CHANNEL_ID` | Yes | Channel for archive cards |
| `USER_KEY` | Recommended | Encryption key (files unencrypted if not set) |
| `DISCORD_DRIVE_LOG_CHANNEL_ID` | No | Channel for log backups |
| `DISCORD_DRIVE_STORAGE_CHANNEL_ID` | No | Legacy storage channel |
| `DISCORD_DRIVE_DATABASE_CHANNEL_ID` | No | Database notification channel |
| `DISCORD_DRIVE_UPLOAD_PATH` | No | Custom upload folder path |
| `DISCORD_DRIVE_DOWNLOAD_PATH` | No | Custom download folder path |

## Development

### Project Structure

The codebase follows these design principles:

1. **Separation of Concerns**: Core logic is independent of Discord
2. **Single Responsibility**: Each module has one clear purpose
3. **Dependency Injection**: Configuration is centralized
4. **Type Safety**: Data models defined in `common/types.py`

### Running Tests

```bash
# Add tests in future
pytest tests/
```

## Troubleshooting

### Bot won't start
- Check `DISCORD_BOT_TOKEN` in `.env`
- Verify bot has proper permissions in Discord
- Check `DISCORD_DRIVE_ARCHIVE_CHANNEL_ID` is valid

### Files aren't encrypted
- Set `USER_KEY` in `.env` file
- Restart the bot after adding the key

### Upload fails
- Check available disk space
- Verify upload folder exists and has files
- Use `!resume` to continue failed uploads

### Download fails
- Check archive exists with `!archives`
- Verify channel permissions
- Re-run `!download` to resume

## Migration from Old Version

If you have an existing installation:

1. Run `!migrate-legacy` to convert old logs to archive cards
2. Run `!rebuild-log confirm` to rebuild the log from archive channel
3. Old files will continue to work with the new system

## License

[Add your license here]

## Contributing

Contributions are welcome! Please follow the existing code structure and patterns.

## Support

For issues or questions, please open a GitHub issue.
