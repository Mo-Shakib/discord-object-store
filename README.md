# Discord Storage Bot

Turn Discord into secure, distributed file storage with compression, encryption, and chunked uploads.

## Features
- Compresses, encrypts, and splits files into <10MB chunks (capped at 9.5MB)
- Stores chunks in a dedicated storage channel using threads
- Posts searchable batch cards in a batch index channel
- Downloads and reconstructs files by batch ID
- SQLite metadata storage with WAL mode and indexes
- Syncs local database from Discord when needed
- Optional Discord-hosted database backups
- Progress indicators for long-running operations
- Simple, friendly CLI for non-technical users

## Architecture
- **Storage channel** (`STORAGE_CHANNEL_NAME`): contains threads with chunk files
- **Batch index channel** (`BATCH_INDEX_CHANNEL_NAME`): human-readable batch cards
- **Archive channel** (`ARCHIVE_CHANNEL_NAME`): reserved for future use
- **Backup channel** (`BACKUP_CHANNEL_NAME`): optional DB backups stored in Discord
- **SQLite**: local metadata store for batches, chunks, files
- **Fernet + PBKDF2**: encryption with per-batch salts

## Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Setup
1. Create a Discord bot in the Developer Portal and invite it to your server.
2. Run the setup wizard:
```bash
python setup.py
```
3. Follow prompts to save your token, generate keys, and optionally sync.

## Commands
```bash
python bot.py upload <path>              # Upload file/folder
python bot.py download <batch_id> <path> # Download batch
python bot.py list                       # List batches
python bot.py info <batch_id>            # Batch details
python bot.py delete <batch_id>          # Delete batch (local + optional Discord)
python bot.py stats                      # Storage statistics
python bot.py verify <batch_id>          # Verify integrity
python bot.py resume <batch_id>          # Resume upload
python bot.py backup                     # Backup DB (optional upload to Discord)
python bot.py sync --reset               # Rebuild DB from Discord
```

## Use Cases
- Archive project folders and assets safely in Discord
- Store large datasets without relying on local disk
- Share encrypted batches within a team Discord server

## Workflow
### Upload
1. Scan files/folders and calculate totals
2. Collect optional title, tags, description
3. Create `.tar.gz`, encrypt with Fernet, split into chunks
4. Post batch card to the batch index channel
5. Create a storage thread and upload chunk files
6. Save metadata to SQLite

### Download
1. Lookup batch metadata in SQLite
2. Download chunks concurrently
3. Verify SHA-256 hashes
4. Merge chunks, decrypt archive, extract files

### Sync
1. Read batch cards from the batch index channel
2. Use thread ID to fetch chunk attachments
3. Rebuild SQLite with batch/chunk metadata

## How It Works
- Each batch becomes a thread in the storage channel
- A batch card contains size, file count, tags, and timestamp
- The local DB stores chunk URLs, hashes, and metadata
- Encryption uses PBKDF2-derived keys with per-batch salts

## Security
- Never share your bot token or encryption key
- Encryption uses AES-256 (Fernet) with HMAC integrity
- SHA-256 used to verify chunk integrity
- `.env` and database files are ignored by Git

## Troubleshooting
- **Invalid token**: Ensure the bot token is correct and has not been regenerated.
- **No guilds found**: Invite the bot to a server and grant permissions.
- **Permission errors**: Ensure the bot can manage threads and send files.
- **Batch not found**: Run `python bot.py sync --reset` to rebuild DB.
- **Large files**: Ensure `MAX_CHUNK_SIZE` is below Discord upload limits.
