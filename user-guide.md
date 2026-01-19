# DisBucket User Guide

**Version:** 1.0  
**Last Updated:** January 2026

---

## Table of Contents

1. [Introduction](#introduction)
2. [Installation & Setup](#installation--setup)
3. [Quick Start](#quick-start)
4. [Command Reference](#command-reference)
5. [Multi-Channel Storage](#multi-channel-storage)
6. [Backup & Restore](#backup--restore)
7. [Use Cases & Examples](#use-cases--examples)
8. [Configuration](#configuration)
9. [Advanced Features](#advanced-features)
10. [Troubleshooting](#troubleshooting)
11. [Best Practices](#best-practices)

---

## Introduction

**DisBucket** is a Discord-based file storage system that allows you to securely store and retrieve files using Discord as a backend. Features include:

- 🔐 **End-to-end encryption** (Fernet/AES-256)
- 📦 **Automatic compression** (tar.gz)
- 🔄 **Chunked uploads** (9.5MB chunks for Discord compatibility)
- 🌐 **Multi-channel support** (distribute files across channels)
- 💾 **Database backup/restore** (sync across devices)
- ⚡ **Async/parallel operations** (fast uploads/downloads)
- 🔍 **Metadata & tagging** (organize your files)

---

## Installation & Setup

### Prerequisites

- Python 3.10 or higher
- Discord bot account
- Discord server with bot invited

### Step 1: Install Dependencies

```bash
cd DisBucket
pip install -r requirements.txt
```

### Step 2: Run Setup Wizard

```bash
python setup.py
```

The wizard will guide you through:

1. **Bot Token**: Enter your Discord bot token
2. **Encryption Key**: 
   - Enter existing key (for multi-device setup)
   - OR generate new key (for fresh installation)
3. **Save Key**: Confirm you've saved the encryption key
4. **Database**: Initialize or restore from backup
5. **Channels**: Auto-create Discord channels
6. **Sync**: Optionally sync from Discord

**⚠️ CRITICAL:** Save your encryption key in a password manager! Without it, you cannot decrypt your files.

### Step 3: Verify Installation

```bash
python bot.py help
```

---

## Quick Start

### Upload Your First File

```bash
# Interactive upload (with prompts)
python bot.py upload /path/to/myfile.zip

# Quick upload (skip prompts)
python bot.py upload /path/to/myfile.zip --yes
```

### List Your Files

```bash
python bot.py list
```

**Output:**
```
Batch ID                  Name                          Size      Status
------------------------------------------------------------------------
BATCH_20260119_5EC2       myfile.zip               420.68 MB    complete
```

### Download a File

```bash
python bot.py download BATCH_20260119_5EC2 ./downloads
```

**Output:**
```
📥 Download preview
Name: myfile.zip
Size: 420.68 MB (45 chunks)
Downloading: 100%|██████████████████| 45/45 [00:18<00:00]
✓ Verifying integrity...
✓ Merging chunks...
✓ Decrypting archive...
✓ Extracting files...
✅ Restored to: ./downloads/myfile.zip
```

---

## Command Reference

### Upload Commands

#### Basic Upload
```bash
python bot.py upload <path>
```
Upload a file or folder with interactive prompts.

**Options:**
- `--yes` - Skip confirmation prompt
- `--channel <name>` - Upload to specific channel

**Examples:**
```bash
# Upload with metadata prompts
python bot.py upload ~/Documents/project.zip

# Quick upload without prompts
python bot.py upload ~/Videos/movie.mp4 --yes

# Upload to specific channel
python bot.py upload ~/Photos/album.tar.gz --channel photos-storage --yes
```

**Interactive Prompts:**
```
Title (optional, shown on Discord card): My Project Files
Tags (comma separated, optional): work, important, 2024
Description (optional, short summary): Project backup from Q1 2024
```

---

### Download Commands

#### Download Batch
```bash
python bot.py download <batch_id> <destination>
```
Download and restore a previously uploaded batch.

**Examples:**
```bash
# Download to current directory
python bot.py download BATCH_20260119_5EC2 .

# Download to specific folder
python bot.py download BATCH_20260119_5EC2 ~/Downloads/restored

# Download multiple batches
for id in BATCH_20260119_5EC2 BATCH_20260119_ABCD; do
    python bot.py download $id ./backup
done
```

---

### List & Info Commands

#### List All Batches
```bash
python bot.py list
```
Shows all stored batches with summary information.

**Output:**
```
Stored batches:
Batch ID                  Name                          Size      Status
------------------------------------------------------------------------
BATCH_20260119_5EC2       project.zip              420.68 MB    complete
BATCH_20260118_ABC1       documents.tar.gz          52.31 MB    complete
BATCH_20260117_XYZ9       photos.zip               1.23 GB      complete
```

#### Batch Details
```bash
python bot.py info <batch_id>
```
Shows detailed information about a specific batch.

**Example:**
```bash
python bot.py info BATCH_20260119_5EC2
```

**Output:**
```
Batch details
Batch ID: BATCH_20260119_5EC2
Name: project.zip
Files: 15
Size: 420.68 MB
Chunks: 45
Status: complete
Storage Channel: #file-storage-vault
Title: My Project Files
Tags: work, important, 2024
Description: Project backup from Q1 2024
```

---

### Delete Commands

#### Delete Batch
```bash
python bot.py delete <batch_id>
```
Delete batch metadata (and optionally from Discord).

**Interactive Flow:**
```bash
python bot.py delete BATCH_20260119_5EC2
```

**Prompts:**
```
Delete local metadata for this batch? [y/N]: y
Also delete files from Discord? [y/N]: y
Deleted batch metadata.
```

**⚠️ Warning:** Deleting from Discord is permanent and cannot be undone!

---

### Statistics Commands

#### Storage Statistics
```bash
python bot.py stats
```
Shows overall storage statistics.

**Output:**
```
📊 Discord Storage Bot Stats
================================
Total batches: 15
Total size: 12.45 GB
Compressed size: 9.87 GB
Total chunks: 1,245
```

#### Channel Distribution
```bash
python bot.py channels
```
Shows how batches are distributed across storage channels.

**Output:**
```
📡 Storage Channels
============================================================

Configured Channels:
  1. #file-storage-vault
  2. #file-storage-2
  3. #videos-storage

Channel Usage:
Channel                            Batches       Total Size
------------------------------------------------------------
#file-storage-vault                      8         5.23 GB
#file-storage-2                          5         3.45 GB
#videos-storage                          2         3.77 GB

Tip: To add more storage channels, edit STORAGE_CHANNEL_NAME in .env
```

---

### Verification Commands

#### Verify Batch Integrity
```bash
python bot.py verify <batch_id>
```
Re-downloads chunks and verifies SHA-256 hashes.

**Example:**
```bash
python bot.py verify BATCH_20260119_5EC2
```

**Output:**
```
Downloaded 45/45 chunks
✅ Integrity verified.
```

---

### Resume Commands

#### Resume Interrupted Upload
```bash
python bot.py resume <batch_id>
```
Continue an upload that was interrupted.

**Example:**
```bash
python bot.py resume BATCH_20260119_5EC2
```

**Output:**
```
Resuming upload
Uploading: 100%|██████████████████| 15/45 [00:08<00:00]
✅ Upload resumed. Batch ID: BATCH_20260119_5EC2
```

**When to use:** After network failure, bot crash, or manual interruption during upload.

---

### Backup & Restore Commands

#### Create Database Backup
```bash
python bot.py backup
```
Creates local backup and optionally uploads to Discord.

**Interactive Flow:**
```
✅ Backup created: storage_backup_20260119_120000.db
Upload backup to Discord now? [y/N]: y
✅ Backup uploaded to Discord.
```

#### Restore Database from Discord
```bash
python bot.py restore
```
Downloads latest database backup from Discord `#db-backups` channel.

**Options:**
- `--backup-file <filename>` - Restore specific backup

**Examples:**
```bash
# Restore latest backup
python bot.py restore

# Restore specific backup
python bot.py restore --backup-file storage_backup_20260119_120000.db
```

**Output:**
```
⚠️  This will replace your local database with a backup from Discord.
Continue? [y/N]: y
✓ Connected to guild: YourServer
✓ Found backup channel: #db-backups
✓ Found backup: storage_backup_20260119_120000.db (64.00 KB)
✓ Downloading backup...
✓ Download complete
✓ Current database backed up to: storage_pre_restore_20260119_120530.db
✓ Database restored successfully

✅ Database restored successfully!
Total batches: 15
```

---

### Sync Commands

#### Sync from Discord
```bash
python bot.py sync
```
Rebuilds local database by scanning Discord messages.

**Options:**
- `--reset` - Delete local database before syncing

**Examples:**
```bash
# Add new batches from Discord
python bot.py sync

# Full reset and rebuild
python bot.py sync --reset
```

**When to use:**
- New device setup
- Database corruption
- Missing batches in local database

**⚠️ Note:** `restore` is faster and preferred. Use `sync` only if restore doesn't work.

---

## Multi-Channel Storage

### Overview

Distribute your files across multiple Discord channels for:
- Better organization
- Bypass rate limits
- Parallel operations
- Channel-specific purposes

### Configuration

Edit `.env` file:
```ini
# Single channel (default)
STORAGE_CHANNEL_NAME=file-storage-vault

# Multiple channels (comma-separated)
STORAGE_CHANNEL_NAME=file-storage-vault,file-storage-2,file-storage-3

# Organized by type
STORAGE_CHANNEL_NAME=videos-storage,photos-storage,documents-storage
```

### Channel Selection Methods

#### Method 1: Auto Round-Robin (Default)
```bash
python bot.py upload myfile.zip --yes
```
Bot automatically selects channel for balanced distribution.

#### Method 2: Interactive Menu
```bash
python bot.py upload myfile.zip
```

**Menu:**
```
Available Storage Channels:
  0.   Auto (Round-robin)                 [Default]
  1.   #file-storage-vault
  2.   #videos-storage
  3.   #photos-storage

Select channel (0-3, Enter for auto): 2
✓ Selected: #videos-storage
```

#### Method 3: Command-Line Flag
```bash
python bot.py upload movie.mp4 --channel videos-storage --yes
```

### Channel Management

```bash
# View channel distribution
python bot.py channels

# Upload to specific channel
python bot.py upload file.zip --channel special-storage

# Create new channel on-the-fly
python bot.py upload important.tar.gz --channel priority-storage --yes
```

---

## Backup & Restore

### Why Backup?

- **Multi-device sync** - Access files from multiple computers
- **Disaster recovery** - Recover from database corruption
- **Version history** - Keep snapshots of your file catalog

### Backup Workflow

```bash
# Weekly backup routine
python bot.py backup
# Type 'y' to upload to Discord

# Or automated
echo "y" | python bot.py backup
```

### Restore Workflow

#### On New Computer:
```bash
# Step 1: Install and setup (use SAME encryption key!)
python setup.py

# Step 2: Restore database
python bot.py restore

# Step 3: Verify
python bot.py list
```

#### After Corruption:
```bash
# Restore latest backup
python bot.py restore

# Check data
python bot.py stats
```

### Backup Best Practices

1. **Weekly backups** - Create regular backups
2. **Before major operations** - Backup before bulk deletes
3. **After significant uploads** - Backup after adding important files
4. **Multiple locations** - Keep local and Discord backups

---

## Use Cases & Examples

### Use Case 1: Personal File Backup

**Scenario:** Backup important documents weekly.

**Setup:**
```ini
# .env
STORAGE_CHANNEL_NAME=documents-backup
```

**Workflow:**
```bash
#!/bin/bash
# backup-documents.sh

DATE=$(date +%Y%m%d)
BACKUP_DIR=~/Documents
TEMP_ARCHIVE="/tmp/documents-$DATE.tar.gz"

# Create archive
tar -czf "$TEMP_ARCHIVE" "$BACKUP_DIR"

# Upload to Discord
python bot.py upload "$TEMP_ARCHIVE" \
    --channel documents-backup \
    --yes

# Cleanup
rm "$TEMP_ARCHIVE"

# Backup database
echo "y" | python bot.py backup
```

**Cron Job:**
```bash
# Run every Sunday at 2 AM
0 2 * * 0 /path/to/backup-documents.sh
```

---

### Use Case 2: Project Version Control

**Scenario:** Keep versioned backups of project releases.

**Setup:**
```ini
# .env
STORAGE_CHANNEL_NAME=project-releases,project-dev
```

**Workflow:**
```bash
#!/bin/bash
# release.sh

VERSION=$1
PROJECT_DIR=~/Projects/MyApp

if [ -z "$VERSION" ]; then
    echo "Usage: ./release.sh <version>"
    exit 1
fi

# Create release archive
tar -czf "MyApp-v$VERSION.tar.gz" "$PROJECT_DIR"

# Upload with metadata
python bot.py upload "MyApp-v$VERSION.tar.gz" \
    --channel project-releases \
    --yes

# Tag in database
python bot.py info $(python bot.py list | tail -1 | awk '{print $1}')

echo "Release v$VERSION backed up to Discord!"
```

**Usage:**
```bash
./release.sh 1.0.0
./release.sh 1.1.0
./release.sh 2.0.0
```

---

### Use Case 3: Media Library Organization

**Scenario:** Organize videos, photos, and music separately.

**Setup:**
```ini
# .env
STORAGE_CHANNEL_NAME=videos-library,photos-library,music-library
```

**Upload Script:**
```bash
#!/bin/bash
# smart-upload.sh

FILE=$1

# Detect file type
case "${FILE##*.}" in
    mp4|mkv|avi|mov)
        CHANNEL="videos-library"
        ;;
    jpg|jpeg|png|gif|webp)
        CHANNEL="photos-library"
        ;;
    mp3|flac|wav|m4a)
        CHANNEL="music-library"
        ;;
    *)
        CHANNEL="auto"
        ;;
esac

if [ "$CHANNEL" = "auto" ]; then
    python bot.py upload "$FILE" --yes
else
    echo "Uploading to $CHANNEL..."
    python bot.py upload "$FILE" --channel "$CHANNEL" --yes
fi
```

**Usage:**
```bash
./smart-upload.sh vacation-2024.mp4  # → videos-library
./smart-upload.sh family-photo.jpg   # → photos-library
./smart-upload.sh album.mp3          # → music-library
```

---

### Use Case 4: Multi-Device Sync

**Scenario:** Access your files from work laptop and home desktop.

**Device 1 (Initial Setup):**
```bash
# Setup on first device
python setup.py
# Save encryption key: abc123xyz...

# Upload files
python bot.py upload ~/Documents --yes
python bot.py upload ~/Projects --yes

# Backup database
python bot.py backup
# Type 'y' to upload
```

**Device 2 (Setup):**
```bash
# Setup on second device
python setup.py
# Use SAME encryption key: abc123xyz...

# Restore database
python bot.py restore

# Verify files are available
python bot.py list

# Download needed files
python bot.py download BATCH_20260119_5EC2 ~/Documents
```

**Sync Workflow:**
```bash
# On Device 1 after changes:
python bot.py backup

# On Device 2 to get updates:
python bot.py restore
python bot.py list
```

---

### Use Case 5: Automated Server Backups

**Scenario:** Daily backup of server data with rotation.

**Backup Script:**
```bash
#!/bin/bash
# server-backup.sh

DATE=$(date +%Y%m%d)
BACKUP_NAME="server-backup-$DATE"

# Dump database
mysqldump -u root myapp > /tmp/myapp.sql

# Backup application
tar -czf "/tmp/$BACKUP_NAME.tar.gz" \
    /var/www/myapp \
    /etc/nginx/sites-available/myapp \
    /tmp/myapp.sql

# Upload to Discord
cd /opt/disbucket
python bot.py upload "/tmp/$BACKUP_NAME.tar.gz" \
    --channel server-backups \
    --yes

# Keep last 7 days locally
find /tmp -name "server-backup-*.tar.gz" -mtime +7 -delete

# Cleanup
rm /tmp/myapp.sql

# Log
echo "[$(date)] Backup completed: $BACKUP_NAME" >> /var/log/disbucket-backup.log
```

**Cron:**
```bash
# Daily at 3 AM
0 3 * * * /opt/scripts/server-backup.sh
```

---

### Use Case 6: Photo Album Archival

**Scenario:** Archive family photos by year.

**Organization:**
```ini
# .env
STORAGE_CHANNEL_NAME=photos-2020,photos-2021,photos-2022,photos-2023,photos-2024
```

**Upload by Year:**
```bash
#!/bin/bash
# archive-photos.sh

YEAR=$1
PHOTOS_DIR=~/Photos/$YEAR

if [ ! -d "$PHOTOS_DIR" ]; then
    echo "Directory not found: $PHOTOS_DIR"
    exit 1
fi

# Create archive
cd ~/Photos
tar -czf "$YEAR-photos.tar.gz" "$YEAR"

# Upload
python bot.py upload "$YEAR-photos.tar.gz" \
    --channel "photos-$YEAR" \
    --yes

echo "Archived $YEAR photos!"
```

**Usage:**
```bash
./archive-photos.sh 2024
```

---

### Use Case 7: Large File Distribution

**Scenario:** Share large files with team using Discord.

**Workflow:**
```bash
# 1. Upload file
python bot.py upload presentation.zip \
    --channel team-shared \
    --yes

# 2. Get batch ID
BATCH_ID=$(python bot.py list | grep presentation | awk '{print $1}')

# 3. Share batch ID with team
echo "Download with: python bot.py download $BATCH_ID ./downloads"

# Team members can download:
python bot.py download $BATCH_ID ~/Downloads
```

---

## Configuration

### Environment Variables (.env)

```ini
# Required
DISCORD_BOT_TOKEN=your_bot_token_here
ENCRYPTION_KEY=your_44_character_base64_key_here

# Storage Channels (comma-separated for multiple)
STORAGE_CHANNEL_NAME=file-storage-vault

# System Channels
BATCH_INDEX_CHANNEL_NAME=batch-index
BACKUP_CHANNEL_NAME=db-backups

# Performance
MAX_CHUNK_SIZE=9500000
CONCURRENT_UPLOADS=5
CONCURRENT_DOWNLOADS=5
IO_BUFFER_SIZE=8388608
```

### Configuration Options

#### Storage Channels
```ini
# Single channel
STORAGE_CHANNEL_NAME=file-storage-vault

# Multiple channels (round-robin)
STORAGE_CHANNEL_NAME=storage-1,storage-2,storage-3

# Organized channels
STORAGE_CHANNEL_NAME=videos,photos,documents,backups
```

#### Performance Tuning
```ini
# Conservative (slow connection, avoid rate limits)
CONCURRENT_UPLOADS=3
CONCURRENT_DOWNLOADS=3
MAX_CHUNK_SIZE=8388608

# Aggressive (fast connection, maximize speed)
CONCURRENT_UPLOADS=10
CONCURRENT_DOWNLOADS=10
MAX_CHUNK_SIZE=9500000

# Custom buffer size (default: 8MB)
IO_BUFFER_SIZE=16777216  # 16MB
```

#### Channel Names
```ini
# Batch index (archive cards displayed here)
BATCH_INDEX_CHANNEL_NAME=batch-index

# Database backups stored here
BACKUP_CHANNEL_NAME=db-backups
```

---

## Advanced Features

### Custom Metadata

Add searchable metadata to uploads:

```bash
python bot.py upload myfile.zip
```

**Prompts:**
```
Title (optional, shown on Discord card): Q1 2024 Report
Tags (comma separated, optional): work, reports, 2024, quarterly
Description (optional, short summary): Financial report for Q1 2024
```

**Benefits:**
- Searchable in Discord
- Easier to identify files
- Better organization

### Parallel Operations

DisBucket uses async I/O for maximum performance:

```python
# Upload multiple files simultaneously (in script)
import asyncio
from src.uploader import upload

async def bulk_upload(files):
    tasks = [upload(file, confirm=False) for file in files]
    results = await asyncio.gather(*tasks)
    return results

# Run
files = ["file1.zip", "file2.zip", "file3.zip"]
asyncio.run(bulk_upload(files))
```

### Database Operations

Direct database access (advanced):

```python
from src.database import list_batches, get_batch, get_chunks

# List all batches
batches = list_batches()
for batch in batches:
    print(f"{batch['batch_id']}: {batch['original_name']}")

# Get specific batch
batch = get_batch("BATCH_20260119_5EC2")
print(f"Size: {batch['total_size']} bytes")

# Get chunks
chunks = get_chunks("BATCH_20260119_5EC2")
print(f"Chunks: {len(chunks)}")
```

### Web API

Start the web server:

```bash
python -m src.api
```

**Endpoints:**
```bash
# Upload via API
curl -X POST "http://localhost:8000/api/jobs/upload" \
  -F "files=@myfile.zip" \
  -F "title=My File" \
  -F "channel=special-storage"

# List batches
curl "http://localhost:8000/api/batches"

# Get batch info
curl "http://localhost:8000/api/batches/BATCH_20260119_5EC2"

# Delete batch
curl -X DELETE "http://localhost:8000/api/batches/BATCH_20260119_5EC2"
```

---

## Troubleshooting

### Common Issues

#### Issue: "Batch not found"
**Cause:** Database out of sync with Discord.

**Solution:**
```bash
# Try restore first
python bot.py restore

# If that fails, sync from Discord
python bot.py sync --reset
```

#### Issue: "Invalid encryption key"
**Cause:** Wrong key or corrupted file.

**Solution:**
- Verify you're using correct encryption key
- Check `.env` file for typos
- Restore from backup if key was changed

#### Issue: "Rate limited"
**Cause:** Too many requests to Discord API.

**Solution:**
```ini
# Reduce concurrency in .env
CONCURRENT_UPLOADS=3
CONCURRENT_DOWNLOADS=3
```

Or use multiple storage channels:
```ini
STORAGE_CHANNEL_NAME=storage-1,storage-2,storage-3
```

#### Issue: "Failed to upload chunk"
**Cause:** Network timeout or Discord downtime.

**Solution:**
```bash
# Resume the upload
python bot.py resume BATCH_ID
```

#### Issue: "Database locked"
**Cause:** Another DisBucket process is running.

**Solution:**
- Close other DisBucket processes
- Wait for ongoing operations to finish
- Restart if hung

#### Issue: "Channel not found"
**Cause:** Bot doesn't have access to channel.

**Solution:**
- Check bot permissions in Discord
- Ensure bot has "View Channel" and "Send Messages" permissions
- Verify channel name in `.env` matches Discord

---

## Best Practices

### Security

1. **Encryption Key**
   - Store in password manager
   - Never commit to git
   - Create backup copies
   - Use same key across devices

2. **Bot Token**
   - Keep secret
   - Regenerate if compromised
   - Don't share publicly

3. **Permissions**
   - Grant minimum required permissions
   - Use private Discord server
   - Restrict channel access

### Organization

1. **Naming Conventions**
   ```bash
   # Good
   project-name-v1.0.0.tar.gz
   backup-2024-01-19.zip
   photos-summer-2024.tar.gz
   
   # Avoid
   stuff.zip
   backup.tar.gz
   untitled.zip
   ```

2. **Metadata Usage**
   - Always add titles for important files
   - Use consistent tagging scheme
   - Add descriptive summaries

3. **Channel Organization**
   ```ini
   # By type
   STORAGE_CHANNEL_NAME=videos,photos,documents,code
   
   # By project
   STORAGE_CHANNEL_NAME=project-alpha,project-beta,project-gamma
   
   # By time
   STORAGE_CHANNEL_NAME=current,archive-2024,archive-2023
   ```

### Performance

1. **Upload Optimization**
   ```bash
   # Compress before upload
   tar -czf archive.tar.gz large-folder/
   python bot.py upload archive.tar.gz --yes
   
   # Use appropriate concurrency
   # Fast connection: 5-10
   # Slow connection: 3-5
   ```

2. **Download Optimization**
   ```bash
   # Download during off-peak hours
   # Use multiple channels for parallel downloads
   ```

3. **Maintenance**
   ```bash
   # Weekly backup
   python bot.py backup
   
   # Monthly verification
   python bot.py verify BATCH_ID
   
   # Quarterly cleanup
   python bot.py list  # Review old files
   python bot.py delete OLD_BATCH_ID  # Remove if needed
   ```

### Backup Strategy

**3-2-1 Backup Rule:**
- **3** copies of data
- **2** different storage types
- **1** copy off-site

**Example:**
1. Original files (local)
2. DisBucket/Discord (cloud)
3. External hard drive (off-site)

**Database Backups:**
```bash
# Weekly automated backup
echo "y" | python bot.py backup  # Discord

# Monthly local backup
cp storage.db ~/Backups/storage-$(date +%Y%m%d).db
```

---

## Command Cheat Sheet

```bash
# Upload
python bot.py upload <path> [--yes] [--channel <name>]

# Download
python bot.py download <batch_id> <destination>

# List & Info
python bot.py list
python bot.py info <batch_id>
python bot.py stats
python bot.py channels

# Manage
python bot.py delete <batch_id>
python bot.py verify <batch_id>
python bot.py resume <batch_id>

# Backup & Restore
python bot.py backup
python bot.py restore [--backup-file <name>]
python bot.py sync [--reset]

# Help
python bot.py help
python bot.py <command> --help
```

---

## Support & Resources

- **GitHub Issues:** Report bugs and request features
- **Configuration:** Check `.env` file
- **Logs:** Review terminal output for errors
- **Database:** Located at `storage.db`
- **Backups:** Stored in Discord `#db-backups` channel

---

## License & Credits

**DisBucket** - Discord-based file storage system  
**Developer:** Shakib  
**GitHub:** https://github.com/Mo-Shakib/

---

*End of User Guide*
