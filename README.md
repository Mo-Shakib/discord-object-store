# Discord Object Store

**Turn Discord into a secure, distributed file storage system.**

Discord Object Store creates an encrypted, chunked, and compressed archival system using Discord as the storage backend. Designed for both everyday users and developers, it utilizes a local SQLite database to manage metadata, ensuring reliable tracking, fast retrieval, and integrity verification without relying on Discord's native search.

## 🚀 Key Features

| Category         | Capabilities                                                 |
| ---------------- | ------------------------------------------------------------ |
| **Security**     | AES-256 (Fernet) encryption, PBKDF2 key derivation, and SHA-256 integrity checks. |
| **Storage**      | Automatic `.tar.gz` compression and 9.5MB chunking to comply with Discord API limits. |
| **Reliability**  | Resume interrupted uploads, local SQLite metadata indexing (WAL mode), and integrity verification. |
| **Interface**    | Robust CLI with progress indicators and a FastAPI-powered Web UI for live job tracking. |
| **Architecture** | Thread-based storage organization, human-readable batch index cards, and optional cloud backups. |

## 🛠️ Installation & Setup

### 1. Installation

Requires Python 3.8+.

```
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configuration

Create a Discord Application in the [Developer Portal](https://discord.com/developers/applications), invite the bot to your server, and run the interactive setup wizard.

For a complete, step-by-step walkthrough, see `discord-bot-setup.md`.

```
python setup.py
```

*Follow the prompts to configure your Bot Token, Channel IDs, and Encryption Keys.*

## 💻 Usage

### Command Line Interface (CLI)

The project provides a comprehensive CLI for managing archives.

```
# Core Operations
python bot.py upload <path>              # Upload a file or folder
python bot.py download <batch_id> <path> # Restore a batch to specific path
python bot.py list                       # List all indexed batches
python bot.py delete <batch_id>          # Delete batch (Local + Discord)

# Maintenance & Integrity
python bot.py info <batch_id>            # View detailed batch metadata
python bot.py verify <batch_id>          # Verify file integrity via SHA-256
python bot.py resume <batch_id>          # Resume an interrupted upload
python bot.py stats                      # View storage usage statistics

# Database Management
python bot.py backup                     # Backup local DB (optionally to Discord)
python bot.py sync --reset               # Rebuild local DB from Discord channels
```

### Web Dashboard

Launch the FastAPI-based UI for a visual interface to track jobs and browse archives.

```
uvicorn src.api:app --reload
```

Access the dashboard at `http://localhost:8000`.

**API Endpoints:**

- `GET /api/stats` — System metrics
- `GET /api/batches` — Browse archives
- `POST /api/jobs/upload` — Initiate upload

## 🧩 Architecture

The system decouples metadata from storage to ensure performance and reliability.

### Channel Topology

- **Storage Channel:** Contains threads where actual file chunks are uploaded as attachments.
- **Index Channel:** Stores human-readable "Batch Cards" containing metadata references.
- **Backup Channel:** (Optional) Stores encrypted snapshots of the local SQLite database.

### Workflow Overview

1. **Ingestion:** Files are scanned, packaged into a `.tar.gz` archive, and encrypted (Fernet).
2. **Chunking:** The archive is split into 9.5MB chunks to maximize Discord upload reliability.
3. **Indexing:** Metadata (Hash, Size, Order) is written to local SQLite; chunks are uploaded to a Discord thread.
4. **Restoration:** The system retrieves chunks via the local index, validates hashes, decrypts, and unpacks the archive.

## 🔐 Security & Privacy

- **Zero-Knowledge Architecture:** Discord only hosts encrypted binary chunks. It cannot read your filenames or content.
- **Key Management:** Your encryption key is generated locally. **Do not lose it.** Without the key, data in Discord is unrecoverable.
- **Integrity:** Every chunk is hashed (SHA-256). Corrupted chunks are detected immediately during download or verification.

## 🧰 Troubleshooting

| Issue                 | Resolution                                                   |
| --------------------- | ------------------------------------------------------------ |
| **Invalid Token**     | Ensure the bot token is correct in `.env` and hasn't been regenerated. |
| **Permission Errors** | Bot requires `Send Messages`, `Create Public Threads`, and `Attach Files`. |
| **Batch Not Found**   | Run `python bot.py sync --reset` to reconstruct the local index from Discord. |
| **Upload Fails**      | Check internet stability or lower `MAX_CHUNK_SIZE` in config. |

## 🤝 Contributing

Contributions are welcome. Please adhere to the following workflow:

1. Fork the repository and create a feature branch.
2. Ensure changes are well-documented and tested.
3. Submit a Pull Request linking relevant issues.