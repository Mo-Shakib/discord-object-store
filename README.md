# Discord Object Store

Use a Discord channel as a lightweight, resumable object store. This repo contains:
- `bot_server.py`: a Discord bot that uploads/downloads chunked files, keeps history, and can resume failed transfers.
- `slice_and_assemble.py`: a helper to slice large files into Discord-sized chunks and reassemble them later using a manifest.

## How It Works
- Files are sliced into ~9.5 MB `.bin` chunks plus a manifest JSON. By default these land in `"/Volumes/Local Drive/DiscordDrive/Uploads"`.
- The bot watches the upload folder. `!upload` posts every chunk + manifest to the current Discord channel and writes a log (`/Users/shakib/discord-drive-history.json`) with a lot number and archive ID (`#DDMMYY-01`).
- `!download` re-fetches attachments by their logged message IDs into `"/Volumes/Local Drive/DiscordDrive/Downloads"`, skipping anything already present.
- If an upload fails, `!resume` retries only missing files and updates the log.
- `!history` and `!status` summarize recent archives and the current queue/drive state.

## Requirements
- Python 3.10+ (tested with discord.py).
- A Discord bot token with message content intent enabled.
- Access to a Discord channel where the bot can read/write messages and attachments.
- The default paths assume macOS with an external drive mounted at `/Volumes/Local Drive`. Adjust if your environment differs.

## Setup
1) Install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U discord.py
```
2) Create `.env` in the repo root:
```bash
DISCORD_BOT_TOKEN=your-bot-token
```
3) Adjust paths if needed:
- In `bot_server.py`, update `UPLOAD_FOLDER`, `DOWNLOAD_FOLDER`, and `LOG_FILE`.
- In `slice_and_assemble.py`, update `UPLOAD_FOLDER` (chunk output target).
Ensure the folders exist or are creatable.

## Usage
1) Prepare files (optional but recommended for large files):
- Run `python slice_and_assemble.py` and choose option 1 to slice a folder of large files.
- Chunks and a manifest like `123-manifest_HHMMSS_DDMMYY.json` will be placed in your upload folder.

2) Start the bot:
```bash
python bot_server.py
```
The bot will log startup info and check for the configured drive.

3) Bot commands (run in your Discord channel):
- `!upload` — Upload all `.bin` and manifest files currently in the upload folder as a new archive.
- `!download #DDMMYY-01 [#DDMMYY-02]` — Download one archive or a range; files already on disk are skipped.
- `!resume [archive_id]` — Retry failed files for the last failed archive or a specific archive ID.
- `!status` — Show drive presence, queued files, log counts, and last archive status.
- `!history` — List the 5 most recent archives.
- `!help` — In-channel help text.

4) Reassemble downloads:
- After downloading, run `python slice_and_assemble.py`, choose option 2, and point it to the archive folder (e.g., `[Archive] #120225-01` in your downloads directory). Files are restored next to that folder; the chunks folder is deleted if all pieces were present.

## What You Might Change
- Path configuration for uploads/downloads/logs to suit your storage.
- Chunk size or naming in `slice_and_assemble.py` if you target a different attachment limit.
- Log file location or retention strategy.
- Command prefix or intents if integrating with an existing bot setup.

## Tips & Troubleshooting
- Archive IDs are auto-built as `#DDMMYY-##` from the lot counter; keep the log file intact for reliable resume/download.
- If the external drive is not mounted, the bot will warn and still create the folders locally; confirm paths before uploading.
- For failed uploads, fix the underlying issue (missing chunk, network hiccup) and re-run `!resume`.
- Downloads are idempotent; rerun `!download` to fill gaps.

## Contributing
- Open issues or PRs with a clear description of the change or bug.
- Add concise comments only where the flow is non-obvious.
- Keep README and in-bot help text in sync when you add commands or change defaults.
