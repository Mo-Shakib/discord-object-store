import asyncio
import discord
from discord.ext import commands
import os
import json
import datetime
import glob
import re
import time
from typing import Optional
from slice_and_assemble import assemble_from_manifest
from archive_card import (
    create_archive_card,
    update_archive_card,
    parse_archive_card,
    search_archives,
)

# --- CONFIGURATION ---
UPLOAD_FOLDER = '/Volumes/Local Drive/DiscordDrive/Uploads'
DOWNLOAD_FOLDER = '/Volumes/Local Drive/DiscordDrive/Downloads'
# Gets the directory where main.py actually lives

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOG_DIR = os.path.join(BASE_DIR, "logs")
DEFAULT_LOG_FILE = os.path.join(DEFAULT_LOG_DIR, "discord-drive-history.json")
LEGACY_LOG_FILE = os.path.expanduser("~/discord-drive-history.json")

MANIFEST_PATTERNS: list[str] = []
LEGACY_MANIFEST = "manifest.json"


def load_env_file(path):
    if not os.path.exists(path):
        return
    with open(path, 'r') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


ENV_FILE = os.path.join(BASE_DIR, '.env')
load_env_file(ENV_FILE)


def resolve_log_file():
    env_path = os.getenv("DISCORD_DRIVE_LOG_FILE")
    if env_path:
        return os.path.abspath(os.path.expanduser(env_path))
    if os.path.exists(LEGACY_LOG_FILE):
        return LEGACY_LOG_FILE
    return DEFAULT_LOG_FILE


LOG_FILE = resolve_log_file()
log_dir = os.path.dirname(LOG_FILE)
if log_dir:
    os.makedirs(log_dir, exist_ok=True)
print(f"🧭 Log file path: {os.path.abspath(LOG_FILE)}")

try:
    LOG_CHANNEL_ID = int(
        os.getenv("DISCORD_DRIVE_LOG_CHANNEL_ID", "1461594920568619038"))
except (TypeError, ValueError):
    LOG_CHANNEL_ID = 1461594920568619038

try:
    ARCHIVE_CHANNEL_ID = int(
        os.getenv("DISCORD_DRIVE_ARCHIVE_CHANNEL_ID", "1461732803375923251"))
except (TypeError, ValueError):
    ARCHIVE_CHANNEL_ID = 1461732803375923251

try:
    storage_env = os.getenv("DISCORD_DRIVE_STORAGE_CHANNEL_ID")
    STORAGE_CHANNEL_ID = int(storage_env) if storage_env else None
except (TypeError, ValueError):
    STORAGE_CHANNEL_ID = None

TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise SystemExit(
        "❌ DISCORD_BOT_TOKEN not set. Add it to .env or your environment.")

# This check prevents the bot from crashing if the drive isn't plugged in
if not os.path.exists('/Volumes/Local Drive'):
    print("❌ External drive 'Local Drive' not found. Please check the connection.")
else:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
    print("✅ External drive detected. Upload/Download folders ready.")

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
bot.remove_command("help")


def format_bytes(num_bytes):
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{int(num_bytes)} B"


def build_archive_id(lot_num, timestamp_str=None):
    if timestamp_str:
        try:
            dt = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            date_code = dt.strftime("%d%m%y")
        except ValueError:
            date_code = datetime.datetime.now().strftime("%d%m%y")
    else:
        date_code = datetime.datetime.now().strftime("%d%m%y")
    return f"#{date_code}-{int(lot_num):02d}"


def normalize_archive_id(archive_id):
    if not archive_id:
        return None
    candidate = str(archive_id).strip()
    if candidate.startswith("#"):
        candidate = candidate[1:]
    match = re.match(r"^(\d{6})-(\d+)$", candidate)
    if not match:
        return None
    date_code, number = match.groups()
    return f"#{date_code}-{int(number):02d}"


def load_logs():
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, 'r') as f:
            logs = json.load(f)
        if isinstance(logs, list):
            return logs
    except Exception:
        pass
    return []


def write_logs(logs):
    with open(LOG_FILE, 'w') as f:
        json.dump(logs, f, indent=4)


async def get_log_channel():
    if not LOG_CHANNEL_ID:
        return None
    channel = bot.get_channel(LOG_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(LOG_CHANNEL_ID)
        except Exception as e:
            print(f"⚠️ Could not fetch log channel {LOG_CHANNEL_ID}: {e}")
            return None
    return channel


async def get_archive_channel():
    if not ARCHIVE_CHANNEL_ID:
        return None
    channel = bot.get_channel(ARCHIVE_CHANNEL_ID)
    if channel is None:
        try:
            channel = await bot.fetch_channel(ARCHIVE_CHANNEL_ID)
        except Exception as e:
            print(
                f"⚠️ Could not fetch archive channel {ARCHIVE_CHANNEL_ID}: {e}")
            return None
    return channel


async def get_storage_channel(ctx):
    if STORAGE_CHANNEL_ID:
        channel = bot.get_channel(STORAGE_CHANNEL_ID)
        if channel is None:
            try:
                channel = await bot.fetch_channel(STORAGE_CHANNEL_ID)
            except Exception as e:
                print(
                    f"⚠️ Could not fetch storage channel {STORAGE_CHANNEL_ID}: {e}")
                return None
        return channel
    return ctx.channel


def read_manifest_original_names(folder):
    names = []
    for manifest_path in list_manifest_files(folder):
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


def build_progress_text(current, total, uploaded_bytes=None, total_bytes=None):
    if total is None or total == 0:
        return f"Uploading... {current} chunks"
    progress = f"Uploading... {current}/{total} chunks"
    if uploaded_bytes is not None and total_bytes is not None:
        progress += f" ({format_bytes(uploaded_bytes)} / {format_bytes(total_bytes)})"
    return progress


async def download_latest_log_from_channel():
    channel = await get_log_channel()
    if channel is None:
        return
    target_name = os.path.basename(LOG_FILE)
    try:
        async for msg in channel.history(limit=50):
            for attachment in msg.attachments:
                if attachment.filename == target_name:
                    await attachment.save(LOG_FILE)
                    print(
                        f"⬇️ Restored log from channel {LOG_CHANNEL_ID}: {target_name}")
                    return
        print(
            f"⚠️ No log backup found in channel {LOG_CHANNEL_ID}; using local copy.")
    except Exception as e:
        print(f"⚠️ Failed to download log backup: {e}")


async def upload_log_backup():
    if not os.path.exists(LOG_FILE):
        print(f"⚠️ Log file not found at {LOG_FILE}; skipping backup upload.")
        return
    channel = await get_log_channel()
    if channel is None:
        return
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        await channel.send(
            content=f"🗂️ discord-drive-history.json backup @ {timestamp}",
            file=discord.File(LOG_FILE, filename=os.path.basename(LOG_FILE)),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(f"⬆️ Uploaded log backup to channel {LOG_CHANNEL_ID}.")
    except Exception as e:
        print(f"⚠️ Failed to upload log backup: {e}")


async def persist_logs(logs):
    write_logs(logs)
    await upload_log_backup()


async def append_log(entry):
    logs = load_logs()
    logs.append(entry)
    await persist_logs(logs)


async def rebuild_log_from_archive_channel():
    rebuilt_logs, warning = await collect_logs_from_archive_channel()
    if warning:
        print(warning)
        return False
    if not rebuilt_logs:
        print("⚠️ No archive cards found; using local log.")
        return False
    write_logs(rebuilt_logs)
    print(f"🧾 Rebuilt log from archive channel ({len(rebuilt_logs)} entries).")
    return True


async def collect_logs_from_archive_channel():
    channel = await get_archive_channel()
    if channel is None:
        return [], "⚠️ Archive channel unavailable; using local log."
    rebuilt_logs = []
    seen_keys = {}
    async for message in channel.history(limit=None):
        metadata = parse_archive_card(message)
        if not metadata:
            continue
        archive_id = normalize_archive_id(metadata.get(
            "archive_id")) or metadata.get("archive_id")
        if not archive_id:
            continue
        lot = metadata.get("lot")
        entry = {
            "lot": lot,
            "archive_id": archive_id,
            "timestamp": metadata.get("timestamp"),
            "message_ids": metadata.get("message_ids", []),
            "status": metadata.get("status") or "unknown",
            "file_count": metadata.get("file_count"),
            "total_size_bytes": metadata.get("total_size_bytes"),
            "uploaded_files": metadata.get("uploaded_files", []),
            "failed_files": metadata.get("failed_files", []),
            "thread_id": metadata.get("thread_id"),
            "archive_message_id": metadata.get("archive_message_id", message.id),
            "archive_channel_id": ARCHIVE_CHANNEL_ID,
            "storage_channel_id": metadata.get("storage_channel_id"),
            "chunk_count": metadata.get("chunk_count"),
        }
        key = archive_id
        existing = seen_keys.get(key)
        if existing:
            existing["entry"].update(entry)
            continue
        rebuilt_logs.append(entry)
        seen_keys[key] = {"entry": entry}

    return rebuilt_logs, None


async def find_archive_card_by_id(archive_id):
    archive_channel = await get_archive_channel()
    if archive_channel is None:
        return None
    target = normalize_archive_id(archive_id) or archive_id
    async for message in archive_channel.history(limit=500):
        metadata = parse_archive_card(message)
        if not metadata:
            continue
        candidate = normalize_archive_id(metadata.get(
            "archive_id")) or metadata.get("archive_id")
        if candidate == target:
            return message
    return None


async def migrate_legacy_archives(ctx=None):
    archive_channel = await get_archive_channel()
    if archive_channel is None:
        print("⚠️ Archive channel unavailable; migration skipped.")
        return False
    logs = load_logs()
    if not logs:
        print("⚠️ No logs found for migration.")
        return False
    storage_channel = await get_storage_channel(ctx) if ctx else None
    updated = False
    for entry in logs:
        if entry.get("archive_message_id"):
            continue
        archive_id = get_archive_id_from_entry(entry)
        metadata = {
            "lot": entry.get("lot"),
            "archive_id": archive_id,
            "timestamp": entry.get("timestamp"),
            "status": entry.get("status") or "unknown",
            "file_count": entry.get("file_count"),
            "total_size_bytes": entry.get("total_size_bytes"),
            "uploaded_files": entry.get("uploaded_files", []),
            "failed_files": entry.get("failed_files", []),
            "message_ids": [],
            "chunk_count": entry.get("chunk_count") or entry.get("file_count"),
            "files_display": entry.get("uploaded_files", []),
            "uploader": "Legacy Import",
            "archive_channel_id": ARCHIVE_CHANNEL_ID,
            "storage_channel_id": STORAGE_CHANNEL_ID,
            "legacy": True,
        }
        archive_message = await create_archive_card(archive_channel, archive_id, metadata)
        try:
            thread = await archive_message.create_thread(
                name=f"{archive_id} legacy",
                auto_archive_duration=1440,
            )
        except Exception as e:
            print(f"⚠️ Failed to create legacy thread for {archive_id}: {e}")
            continue

        legacy_message_ids = entry.get("message_ids", [])
        migrated_ids = []
        if storage_channel and legacy_message_ids:
            for msg_id in legacy_message_ids:
                try:
                    msg = await storage_channel.fetch_message(msg_id)
                except Exception as e:
                    print(f"⚠️ Could not fetch legacy message {msg_id}: {e}")
                    continue
                for attachment in msg.attachments:
                    try:
                        file_obj = await attachment.to_file()
                        migrated = await thread.send(file=file_obj)
                        migrated_ids.append(migrated.id)
                    except Exception as e:
                        print(
                            f"⚠️ Failed to migrate attachment {attachment.filename}: {e}")

        metadata.update(
            {"thread_id": thread.id, "message_ids": migrated_ids[:150]})
        try:
            await update_archive_card(archive_message, metadata)
        except Exception as e:
            print(f"⚠️ Failed to update legacy archive card: {e}")

        entry["archive_message_id"] = archive_message.id
        entry["thread_id"] = thread.id
        if migrated_ids:
            entry["message_ids"] = migrated_ids
        updated = True

    if updated:
        write_logs(logs)
    return updated


async def reassemble_archive(lot_dir, archive_id, ctx=None):
    if not lot_dir or not os.path.isdir(lot_dir):
        return
    try:
        print(f"🛠️ Reassembling archive {archive_id} from {lot_dir}...")
        if ctx:
            await ctx.send(f"🛠️ Reassembling {archive_id} locally...")
        await asyncio.to_thread(assemble_from_manifest, lot_dir)
        if ctx:
            await ctx.send(f"✅ Reassembly complete for {archive_id}.")
        print(f"✅ Reassembly complete for {archive_id}.")
    except Exception as e:
        print(f"⚠️ Reassembly failed for {archive_id}: {e}")
        if ctx:
            await ctx.send(f"⚠️ Reassembly failed for {archive_id}: {e}")


async def download_from_thread(thread, lot_dir, expected_total_files):
    success_count = 0
    failed_count = 0
    skipped_count = 0
    total_files_known = 0

    async for msg in thread.history(limit=None, oldest_first=True):
        for attachment in msg.attachments:
            if expected_total_files is None:
                total_files_known += 1
            file_path = os.path.join(lot_dir, attachment.filename)
            if os.path.exists(file_path):
                skipped_count += 1
                total_files = expected_total_files if expected_total_files is not None else total_files_known
                left = max(total_files - (success_count +
                           failed_count + skipped_count), 0)
                print(
                    f"📥 Downloaded {success_count}/{total_files} files "
                    f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
                )
                continue
            saved = False
            for attempt in range(3):
                try:
                    await attachment.save(file_path)
                    saved = True
                    success_count += 1
                    break
                except Exception as e:
                    print(
                        f"❌ Failed to save {attachment.filename} (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(2 ** attempt)
            if not saved:
                failed_count += 1
            total_files = expected_total_files if expected_total_files is not None else total_files_known
            left = max(total_files - (success_count +
                       failed_count + skipped_count), 0)
            print(
                f"📥 Downloaded {success_count}/{total_files} files "
                f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
            )

    final_total = expected_total_files if expected_total_files is not None else total_files_known
    return success_count, failed_count, skipped_count, final_total


def find_log_index(logs, archive_id=None, lot=None):
    normalized_target = normalize_archive_id(
        archive_id) if archive_id else None
    for index, entry in enumerate(logs):
        if normalized_target:
            entry_id = normalize_archive_id(
                entry.get("archive_id")) or entry.get("archive_id")
            if entry_id == normalized_target:
                return index
        if lot is not None and entry.get("lot") == lot:
            return index
    return None


def get_archive_id_from_entry(entry):
    archive_id = normalize_archive_id(entry.get("archive_id"))
    if archive_id:
        return archive_id
    lot = entry.get("lot")
    if lot is None:
        return "unknown"
    return build_archive_id(lot, entry.get("timestamp"))


def calculate_total_size(file_paths):
    total = 0
    for path in file_paths:
        try:
            total += os.path.getsize(path)
        except OSError:
            continue
    return total


def dedupe_paths(paths):
    seen = set()
    unique_paths = []
    for path in paths:
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        unique_paths.append(path)
    return unique_paths


def list_manifest_files(folder):
    manifest_paths = []
    try:
        for name in os.listdir(folder):
            if not name.lower().endswith(".json"):
                continue
            if "manifest" not in name.lower():
                continue
            manifest_paths.append(os.path.join(folder, name))
    except OSError:
        pass
    legacy_path = os.path.join(folder, LEGACY_MANIFEST)
    if os.path.exists(legacy_path):
        manifest_paths.append(legacy_path)
    return dedupe_paths(manifest_paths)


def list_upload_files():
    bin_files = glob.glob(os.path.join(UPLOAD_FOLDER, "*.bin"))
    manifest_files = list_manifest_files(UPLOAD_FOLDER)
    return dedupe_paths(bin_files + manifest_files)


def get_archive_id_by_lot(logs, lot_num):
    for entry in logs:
        if entry.get("lot") == lot_num:
            return get_archive_id_from_entry(entry)
    return f"Lot {lot_num}"


def resolve_download_target(arg, logs):
    if arg is None:
        return None, None, None
    candidate = str(arg).strip()
    archive_id = normalize_archive_id(candidate)
    if archive_id:
        for entry in logs:
            entry_id = get_archive_id_from_entry(entry)
            if entry_id == archive_id:
                lot_value = entry.get("lot")
                if lot_value is None:
                    return None, None, f"Archive {archive_id} has no lot number in logs."
                return int(lot_value), archive_id, None
        return None, None, f"Archive {archive_id} not found in logs."
    if candidate.isdigit():
        return int(candidate), None, None
    return None, None, f"Invalid download target `{candidate}`. Use `#DDMMYY-01`."


def build_help_text():
    return (
        "## Discord Drive Bot Help\n"
        "\n"
        "**Overview**\n"
        "- Uploads files from your local upload folder to Discord as an archive.\n"
        "- Tracks every archive in `lot_history.json` for download and resume.\n"
        "\n"
        "**Folders**\n"
        f"- Uploads: `{UPLOAD_FOLDER}`\n"
        f"- Downloads: `{DOWNLOAD_FOLDER}`\n"
        "\n"
        "**Commands**\n"
        "- `!upload` — Create a new archive and upload all `.bin` files plus `*-manifest_*.json`.\n"
        "- `!download #DDMMYY-01 [#DDMMYY-02]` — Download a single archive or a range.\n"
        "- `!resume [archive_id]` — Resume the most recent failed archive, or a specific archive ID.\n"
        "- `!status` — Show bot status, queue size, and last archive info.\n"
        "- `!history` — Show the 5 most recent archives.\n"
        "- `!archives [query]` — List recent archives or search by ID/filename.\n"
        "- `!verify <archive_id>` — Verify archive thread chunks.\n"
        "- `!rebuild-log` — Rebuild local log from archive channel (admin).\n"
        "- `!migrate-legacy` — Migrate legacy logs to archive cards (admin).\n"
        "- `!cleanup <archive_id>` — Remove thread and mark archive deleted (admin).\n"
        "- `!help` — Show this help message.\n"
        "\n"
        "**Archive ID format**\n"
        "- `#DDMMYY-01` (example: `#120225-07`).\n"
        "\n"
        "**Tips**\n"
        "- If an upload fails, fix the issue and run `!resume`.\n"
        "- Downloads are resumable: re-run `!download` and existing files will be skipped.\n"
        "- Keep `DISCORD_BOT_TOKEN` in your `.env` file.\n"
    )


def build_commands_markdown():
    return (
        "### Available Commands\n"
        "- `!upload`\n"
        "- `!download #DDMMYY-01 [#DDMMYY-02]`\n"
        "- `!resume [archive_id]`\n"
        "- `!status`\n"
        "- `!history`\n"
        "- `!archives [query]`\n"
        "- `!verify <archive_id>`\n"
        "- `!rebuild-log`\n"
        "- `!migrate-legacy`\n"
        "- `!cleanup <archive_id>`\n"
        "- `!help`\n"
    )


def is_admin(ctx):
    perms = getattr(ctx.author, "guild_permissions", None)
    if not perms:
        return False
    return perms.administrator or perms.manage_guild


def get_next_lot():
    logs = load_logs()
    if not logs:
        return 1
    return max(int(entry.get('lot', 0)) for entry in logs) + 1


@bot.event
async def on_ready():
    print(f"🟢 Bot online as {bot.user.name} (ID: {bot.user.id})")
    rebuilt = await rebuild_log_from_archive_channel()
    if not rebuilt:
        await download_latest_log_from_channel()
    print("🤖 Ready and listening for commands.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        print(f"⚠️ Invalid command: {ctx.message.content}")
        await ctx.send(
            "⚠️ **Invalid command.**\n"
            "Use one of the commands below:\n\n"
            f"{build_commands_markdown()}"
        )
        return
    print(f"❌ Command error: {error}")
    raise error


@bot.command()
async def upload(ctx):
    print(f"📤 Upload command received from {ctx.author} in {ctx.channel}.")
    lot_num = get_next_lot()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    archive_id = build_archive_id(lot_num, timestamp)

    archive_channel = await get_archive_channel()
    if archive_channel is None:
        await ctx.send("⚠️ Archive channel unavailable. Upload aborted.")
        return

    files_to_upload = list_upload_files()
    if not files_to_upload:
        print("⚠️ No files found to upload.")
        await ctx.send("⚠️ No files found in the upload folder.")
        return

    original_names = read_manifest_original_names(UPLOAD_FOLDER)
    files_display = original_names if original_names else [
        os.path.basename(p) for p in files_to_upload]
    total_size_bytes = calculate_total_size(files_to_upload)
    chunk_count = len(files_to_upload)
    file_count = len(original_names) if original_names else None

    metadata = {
        "lot": lot_num,
        "archive_id": archive_id,
        "timestamp": timestamp,
        "status": "partial",
        "file_count": file_count,
        "total_size_bytes": total_size_bytes,
        "uploaded_files": [],
        "failed_files": [],
        "message_ids": [],
        "chunk_count": chunk_count,
        "files_display": files_display,
        "uploader": str(ctx.author),
        "archive_channel_id": ARCHIVE_CHANNEL_ID,
        "storage_channel_id": STORAGE_CHANNEL_ID,
    }

    archive_message = await create_archive_card(archive_channel, archive_id, metadata)
    try:
        thread = await archive_message.create_thread(
            name=f"{archive_id} chunks",
            auto_archive_duration=1440,
        )
    except Exception as e:
        await ctx.send(f"⚠️ Failed to create archive thread: {e}")
        return

    await ctx.send(
        f"📦 Archive card created: {archive_id}. Uploading {chunk_count} chunk(s) "
        f"({format_bytes(total_size_bytes)})..."
    )

    uploaded_message_ids = []
    uploaded_files = []
    failed_files = []
    errors = {}
    uploaded_bytes = 0
    last_edit = 0.0

    print(f"📦 Uploading {chunk_count} file(s) to thread {thread.id}...")
    for index, file_path in enumerate(files_to_upload, start=1):
        file_name = os.path.basename(file_path)
        print(f"⬆️ Uploading file: {file_name}")
        try:
            discord_file = discord.File(file_path)
            msg = await thread.send(file=discord_file)
            uploaded_message_ids.append(msg.id)
            uploaded_files.append(file_name)
            try:
                uploaded_bytes += os.path.getsize(file_path)
            except OSError:
                pass
            try:
                os.remove(file_path)
                print(f"🗑️ Removed uploaded file: {file_name}")
            except OSError as e:
                print(f"⚠️ Could not delete {file_name} after upload: {e}")
        except Exception as e:
            failed_files.append(file_name)
            errors[file_name] = str(e)
            print(f"❌ Failed to upload {file_name}: {e}")

        now = time.monotonic()
        if now - last_edit > 1.2 or index == chunk_count:
            metadata.update(
                {
                    "uploaded_files": uploaded_files,
                    "failed_files": failed_files,
                    "message_ids": uploaded_message_ids[:150],
                    "thread_id": thread.id,
                    "progress_text": build_progress_text(index, chunk_count, uploaded_bytes, total_size_bytes),
                }
            )
            try:
                await update_archive_card(archive_message, metadata)
                last_edit = now
            except Exception as e:
                print(f"⚠️ Failed to update archive card: {e}")

    if failed_files:
        status = "partial" if uploaded_files else "failed"
    else:
        status = "success"

    metadata.update(
        {
            "status": status,
            "uploaded_files": uploaded_files,
            "failed_files": failed_files,
            "message_ids": uploaded_message_ids[:150],
            "thread_id": thread.id,
        }
    )
    metadata.pop("progress_text", None)
    if errors:
        metadata["errors"] = errors

    try:
        await update_archive_card(archive_message, metadata)
    except Exception as e:
        print(f"⚠️ Failed to finalize archive card: {e}")

    entry = {
        "lot": lot_num,
        "archive_id": archive_id,
        "timestamp": timestamp,
        "message_ids": uploaded_message_ids,
        "status": status,
        "file_count": file_count,
        "total_size_bytes": total_size_bytes,
        "uploaded_files": uploaded_files,
        "failed_files": failed_files,
        "thread_id": thread.id,
        "archive_message_id": archive_message.id,
        "archive_channel_id": ARCHIVE_CHANNEL_ID,
        "storage_channel_id": STORAGE_CHANNEL_ID,
        "chunk_count": chunk_count,
    }
    if errors:
        entry["errors"] = errors
    await append_log(entry)

    if status == "success":
        print(f"✅ Upload complete for Archive {archive_id}.")
        try:
            await archive_message.pin()
        except Exception:
            pass
        await ctx.send(
            f"✅ Archive {archive_id} uploaded successfully.\n"
            f"📦 Chunks: {chunk_count} • Size: {format_bytes(total_size_bytes)}"
        )
    else:
        print(f"⚠️ Upload completed with errors for Archive {archive_id}.")
        await ctx.send(
            f"⚠️ Archive {archive_id} uploaded with errors.\n"
            f"✅ Uploaded: {len(uploaded_files)}/{chunk_count} • "
            f"Size: {format_bytes(total_size_bytes)}\n"
            "🔁 Use `!resume` to continue."
        )


@bot.command()
async def download(ctx, start: str, end: Optional[str] = None):
    print(f"📥 Download command received from {ctx.author} in {ctx.channel}.")

    if not os.path.exists(LOG_FILE):
        print("❌ No log file found; cannot download.")
        await ctx.send("No log file found.")
        return

    logs = load_logs()
    if not logs:
        rebuilt = await rebuild_log_from_archive_channel()
        if rebuilt:
            logs = load_logs()

    lot_start, start_id, error = resolve_download_target(start, logs)
    if error:
        await ctx.send(f"⚠️ {error}\n\n{build_commands_markdown()}")
        return
    lot_end = None
    end_id = None
    if end is not None:
        lot_end, end_id, error = resolve_download_target(end, logs)
        if error:
            await ctx.send(f"⚠️ {error}\n\n{build_commands_markdown()}")
            return
    if lot_end is None:
        lot_end = lot_start
    if lot_start > lot_end:
        lot_start, lot_end = lot_end, lot_start

    start_label = start_id or get_archive_id_by_lot(logs, lot_start)
    end_label = end_id or get_archive_id_by_lot(logs, lot_end)

    # Filter logs for the requested range
    target_lots = []
    for entry in logs:
        lot_value = entry.get("lot")
        if lot_value is None:
            continue
        try:
            lot_number = int(lot_value)
        except (TypeError, ValueError):
            continue
        if lot_start <= lot_number <= lot_end:
            target_lots.append(entry)

    if not target_lots:
        print(f"⚠️ No data found for download range {lot_start}-{lot_end}.")
        await ctx.send("⚠️ No data found for the requested range.")
        return

    total_expected_files = sum(
        entry.get("file_count", 0) for entry in target_lots if isinstance(entry.get("file_count"), int)
    )
    total_expected_text = (
        f"{total_expected_files} files"
        if total_expected_files > 0
        else "unknown file count"
    )
    await ctx.send(
        f"📥 Starting download {start_label} to {end_label} "
        f"({len(target_lots)} archive(s), {total_expected_text})."
    )

    print(
        f"📦 Preparing download for {len(target_lots)} lot(s) into {DOWNLOAD_FOLDER}...")
    total_lots = len(target_lots)
    for index, lot_data in enumerate(target_lots, start=1):
        archive_id = get_archive_id_from_entry(lot_data)
        print(
            f"⏳ Processing {index}/{total_lots} Lots (Archive {archive_id})...")
        archive_folder = f"[Archive] {archive_id}"
        lot_dir = os.path.join(DOWNLOAD_FOLDER, archive_folder)
        legacy_dir = os.path.join(DOWNLOAD_FOLDER, f"Lot_{lot_data['lot']}")
        if not os.path.exists(lot_dir) and os.path.exists(legacy_dir):
            try:
                os.rename(legacy_dir, lot_dir)
            except OSError as e:
                print(f"⚠️ Could not rename {legacy_dir} to {lot_dir}: {e}")
        os.makedirs(lot_dir, exist_ok=True)

        archive_message = await find_archive_card_by_id(archive_id)
        archive_metadata = parse_archive_card(
            archive_message) if archive_message else None

        archive_size_bytes = (
            (archive_metadata or {}).get("total_size_bytes")
            if archive_metadata
            else lot_data.get("total_size_bytes")
        )
        archive_size_text = format_bytes(
            archive_size_bytes) if archive_size_bytes is not None else "Unknown size"
        archive_file_count = (
            (archive_metadata or {}).get("file_count")
            if archive_metadata
            else lot_data.get("file_count")
        )
        archive_file_text = (
            f"{archive_file_count} files" if isinstance(
                archive_file_count, int) else "Unknown file count"
        )
        await ctx.send(
            f"📦 **Downloading Archive: {archive_id}**\n"
            f"📄 {archive_file_text} • 📦 {archive_size_text}"
        )

        expected_total_files = (
            (archive_metadata or {}).get("chunk_count")
            or lot_data.get("chunk_count")
            or lot_data.get("file_count")
        )

        thread_id = (
            (archive_metadata or {}).get("thread_id")
            if archive_metadata
            else lot_data.get("thread_id")
        )
        if thread_id:
            try:
                thread = await bot.fetch_channel(thread_id)
            except Exception as e:
                print(f"⚠️ Could not fetch archive thread {thread_id}: {e}")
                thread = None
        else:
            thread = None

        if thread is not None:
            success_count, failed_count, skipped_count, final_total = await download_from_thread(
                thread, lot_dir, expected_total_files
            )
        else:
            # Legacy fallback: fetch the messages using saved IDs
            success_count = 0
            failed_count = 0
            skipped_count = 0
            total_files_known = 0
            storage_channel = await get_storage_channel(ctx)
            if storage_channel is None:
                storage_channel = ctx.channel
            for msg_id in lot_data.get("message_ids", []):
                try:
                    msg = await storage_channel.fetch_message(msg_id)
                    if expected_total_files is None:
                        total_files_known += len(msg.attachments)
                    for attachment in msg.attachments:
                        file_path = os.path.join(lot_dir, attachment.filename)
                        if os.path.exists(file_path):
                            skipped_count += 1
                            total_files = expected_total_files if expected_total_files is not None else total_files_known
                            left = max(total_files - (success_count +
                                       failed_count + skipped_count), 0)
                            print(
                                f"📥 Downloaded {success_count}/{total_files} files "
                                f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
                            )
                            continue
                        saved = False
                        for attempt in range(3):
                            try:
                                await attachment.save(file_path)
                                saved = True
                                success_count += 1
                                break
                            except Exception as e:
                                print(
                                    f"❌ Failed to save {attachment.filename} (attempt {attempt + 1}): {e}")
                                await asyncio.sleep(2 ** attempt)
                        if not saved:
                            failed_count += 1
                        total_files = expected_total_files if expected_total_files is not None else total_files_known
                        left = max(total_files - (success_count +
                                   failed_count + skipped_count), 0)
                        print(
                            f"📥 Downloaded {success_count}/{total_files} files "
                            f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
                        )
                except Exception as e:
                    print(f"❌ Error downloading message {msg_id}: {e}")

            final_total = expected_total_files if expected_total_files is not None else total_files_known
        print(
            f"✅ Archive {archive_id} complete "
            f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • 📦 {final_total} total)"
        )
        if failed_count == 0:
            await ctx.send(
                f"✅ Archive {archive_id} downloaded successfully.\n"
                f"📥 Downloaded: {success_count} • ⏭️ Skipped: {skipped_count} • 📦 Total: {final_total}"
            )
            if archive_message:
                try:
                    await archive_message.add_reaction("📥")
                except Exception:
                    pass
            await reassemble_archive(lot_dir, archive_id, ctx)
        else:
            await ctx.send(
                f"⚠️ Archive {archive_id} downloaded with errors.\n"
                f"✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • 📦 {final_total}\n"
                "🔁 Re-run `!download` to resume."
            )

    print(f"✅ Download complete for {start_label} to {end_label}.")
    await ctx.send(f"✅ Downloaded {start_label} to {end_label} to your local folder.")


@bot.command()
async def resume(ctx, archive_id: Optional[str] = None):
    print(f"🔁 Resume command received from {ctx.author} in {ctx.channel}.")
    logs = load_logs()
    if not logs:
        await ctx.send("⚠️ No log file found.")
        return

    target_index = None
    if archive_id:
        target_index = find_log_index(logs, archive_id=archive_id)
        if target_index is None:
            await ctx.send(f"⚠️ Archive {archive_id} not found in logs.")
            return
    else:
        for i in range(len(logs) - 1, -1, -1):
            if logs[i].get("status") == "failed":
                target_index = i
                break
        if target_index is None:
            await ctx.send("✅ No failed uploads to resume.")
            return

    entry = logs[target_index]
    archive_id = get_archive_id_from_entry(entry)
    file_names = entry.get("failed_files") or []
    if not file_names:
        file_names = [os.path.basename(p) for p in list_upload_files()]
        print("⚠️ No failed_files list; falling back to current upload folder.")

    file_paths = []
    missing_files = []
    total_size_bytes = 0
    for name in file_names:
        path = name if os.path.isabs(
            name) else os.path.join(UPLOAD_FOLDER, name)
        if os.path.exists(path):
            file_paths.append(path)
            total_size_bytes += os.path.getsize(path)
        else:
            missing_files.append(name)

    if not file_paths:
        await ctx.send(f"⚠️ No files found to resume for Archive {archive_id}.")
        return

    await ctx.send(
        f"🔁 Resuming Archive {archive_id} with {len(file_paths)} file(s) "
        f"({format_bytes(total_size_bytes)})..."
    )

    uploaded_files = entry.get("uploaded_files", [])
    failed_files = []
    errors = entry.get("errors", {})
    message_ids = entry.get("message_ids", [])

    archive_message = await find_archive_card_by_id(archive_id)
    archive_metadata = parse_archive_card(
        archive_message) if archive_message else None
    thread_id = (archive_metadata or {}).get(
        "thread_id") or entry.get("thread_id")
    thread = None
    if thread_id:
        try:
            thread = await bot.fetch_channel(thread_id)
        except Exception as e:
            print(f"⚠️ Could not fetch thread {thread_id}: {e}")
    elif archive_message:
        try:
            thread = await archive_message.create_thread(
                name=f"{archive_id} chunks",
                auto_archive_duration=1440,
            )
        except Exception as e:
            print(f"⚠️ Failed to create thread for resume: {e}")

    target_channel = thread or ctx.channel

    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        print(f"⬆️ Resuming upload: {file_name}")
        try:
            discord_file = discord.File(file_path)
            msg = await target_channel.send(file=discord_file)
            message_ids.append(msg.id)
            if file_name not in uploaded_files:
                uploaded_files.append(file_name)
        except Exception as e:
            failed_files.append(file_name)
            errors[file_name] = str(e)
            print(f"❌ Failed to upload {file_name}: {e}")

    if missing_files:
        for name in missing_files:
            errors[name] = "file missing from upload folder"
        failed_files.extend(missing_files)

    entry["message_ids"] = message_ids
    entry["uploaded_files"] = uploaded_files
    entry["failed_files"] = failed_files
    if thread is not None:
        entry["thread_id"] = thread.id
    if errors:
        entry["errors"] = errors

    original_count = entry.get("file_count")
    if original_count is None:
        entry["file_count"] = len(set(uploaded_files + failed_files))

    if entry.get("total_size_bytes") is None:
        entry["total_size_bytes"] = total_size_bytes

    entry["status"] = "success" if not failed_files else "failed"
    logs[target_index] = entry
    await persist_logs(logs)

    if archive_message:
        archive_metadata = archive_metadata or {}
        archive_metadata.update(
            {
                "status": entry["status"],
                "uploaded_files": uploaded_files,
                "failed_files": failed_files,
                "message_ids": message_ids[:150],
                "thread_id": entry.get("thread_id"),
                "file_count": entry.get("file_count"),
                "total_size_bytes": entry.get("total_size_bytes"),
            }
        )
        try:
            await update_archive_card(archive_message, archive_metadata)
        except Exception as e:
            print(f"⚠️ Failed to update archive card on resume: {e}")

    if entry["status"] == "success":
        await ctx.send(
            f"✅ Archive {archive_id} successfully completed.\n"
            f"📦 Files: {entry['file_count']} • "
            f"Size: {format_bytes(entry['total_size_bytes'])}"
        )
    else:
        await ctx.send(
            f"⚠️ Archive {archive_id} still has failed uploads.\n"
            f"✅ Uploaded: {len(uploaded_files)}/{entry['file_count']} • "
            f"Size: {format_bytes(entry['total_size_bytes'])}\n"
            "🔁 Run `!resume` again after fixing issues."
        )


@bot.command()
async def status(ctx):
    drive_ok = os.path.exists('/Volumes/Local Drive')
    upload_files = list_upload_files()
    upload_total_size = calculate_total_size(upload_files)
    logs = load_logs()
    failed_count = len([l for l in logs if l.get("status") == "failed"])
    last_entry = logs[-1] if logs else None
    last_archive = get_archive_id_from_entry(
        last_entry) if last_entry else "none"
    last_status = last_entry.get("status") if last_entry else "n/a"

    await ctx.send(
        "📊 **Bot Status**\n"
        f"💾 Drive: {'✅ Ready' if drive_ok else '❌ Missing'}\n"
        f"📤 Upload queue: {len(upload_files)} file(s) • {format_bytes(upload_total_size)}\n"
        f"📚 Logs: {len(logs)} entries • ❗ Failed: {failed_count}\n"
        f"🗂️ Last Archive: {last_archive} • Status: {last_status}"
    )


@bot.command()
async def history(ctx):
    logs = load_logs()
    if not logs:
        await ctx.send("📭 No history found yet.")
        return

    recent = logs[-5:]
    lines = ["📜 **Recent Archives**"]
    for entry in recent:
        archive_id = get_archive_id_from_entry(entry)
        status = entry.get("status", "unknown")
        file_count = entry.get("file_count")
        if file_count is None:
            uploaded = entry.get("uploaded_files", [])
            failed = entry.get("failed_files", [])
            file_count = len(set(uploaded + failed)
                             ) if (uploaded or failed) else "?"
        total_size_bytes = entry.get("total_size_bytes")
        size_text = format_bytes(
            total_size_bytes) if total_size_bytes is not None else "Unknown size"
        timestamp = entry.get("timestamp", "unknown time")
        status_emoji = "✅" if status == "success" else (
            "⚠️" if status == "failed" else "❔")
        lines.append(
            f"{status_emoji} {archive_id} • {file_count} files • {size_text} • {timestamp}"
        )

    await ctx.send("\n".join(lines))


@bot.command()
async def archives(ctx, *, query: Optional[str] = None):
    archive_channel = await get_archive_channel()
    if archive_channel is None:
        await ctx.send("⚠️ Archive channel unavailable.")
        return
    messages = await search_archives(archive_channel, query)
    if not messages:
        await ctx.send("📭 No archives found.")
        return
    lines = ["📚 **Archives**"]
    for message in messages:
        metadata = parse_archive_card(message) or {}
        archive_id = metadata.get("archive_id") or "unknown"
        size_text = (
            format_bytes(metadata.get("total_size_bytes"))
            if metadata.get("total_size_bytes") is not None
            else "Unknown size"
        )
        status = metadata.get("status") or "unknown"
        lines.append(f"{archive_id} • {size_text} • {status}")
    await ctx.send("\n".join(lines))


@bot.command()
async def verify(ctx, archive_id: str):
    archive_message = await find_archive_card_by_id(archive_id)
    if archive_message is None:
        await ctx.send(f"⚠️ Archive {archive_id} not found.")
        return
    metadata = parse_archive_card(archive_message) or {}
    thread_id = metadata.get("thread_id")
    if not thread_id:
        await ctx.send(f"⚠️ Archive {archive_id} has no thread metadata.")
        return
    try:
        thread = await bot.fetch_channel(thread_id)
    except Exception as e:
        await ctx.send(f"⚠️ Could not fetch archive thread: {e}")
        return

    attachment_names = set()
    async for msg in thread.history(limit=None, oldest_first=True):
        for attachment in msg.attachments:
            attachment_names.add(attachment.filename)

    uploaded_files = metadata.get("uploaded_files")
    expected_files: list[str] = uploaded_files if isinstance(
        uploaded_files, list) else []
    missing_files = [
        name for name in expected_files if name not in attachment_names]
    chunk_count = metadata.get("chunk_count")
    if missing_files:
        await ctx.send(
            f"⚠️ Archive {archive_id} missing {len(missing_files)} chunk(s).\n"
            + "\n".join(missing_files[:20])
        )
        return
    if isinstance(chunk_count, int) and len(attachment_names) != chunk_count:
        await ctx.send(
            f"⚠️ Archive {archive_id} chunk count mismatch. "
            f"Expected {chunk_count}, found {len(attachment_names)}."
        )
        return
    await ctx.send(f"✅ Archive {archive_id} verified. {len(attachment_names)} chunks present.")


@bot.command(name="rebuild-log")
async def rebuild_log_command(ctx, confirm: Optional[str] = None):
    if not is_admin(ctx):
        await ctx.send("⛔ Admin permissions required.")
        return
    new_logs, warning = await collect_logs_from_archive_channel()
    if warning:
        await ctx.send(warning)
        return
    old_logs = load_logs()
    if confirm != "confirm":
        await ctx.send(
            f"🧾 Rebuild preview: local {len(old_logs)} entries, "
            f"archive channel {len(new_logs)} entries.\n"
            "Run `!rebuild-log confirm` to overwrite the local log."
        )
        return
    write_logs(new_logs)
    await ctx.send(f"✅ Rebuilt local log from archive channel ({len(new_logs)} entries).")


@bot.command(name="migrate-legacy")
async def migrate_legacy_command(ctx):
    if not is_admin(ctx):
        await ctx.send("⛔ Admin permissions required.")
        return
    migrated = await migrate_legacy_archives(ctx)
    if migrated:
        await ctx.send("✅ Legacy archives migrated to archive cards and threads.")
    else:
        await ctx.send("⚠️ No legacy archives migrated.")


@bot.command()
async def cleanup(ctx, archive_id: str):
    if not is_admin(ctx):
        await ctx.send("⛔ Admin permissions required.")
        return
    archive_message = await find_archive_card_by_id(archive_id)
    if archive_message is None:
        await ctx.send(f"⚠️ Archive {archive_id} not found.")
        return
    metadata = parse_archive_card(archive_message) or {}
    thread_id = metadata.get("thread_id")
    if thread_id:
        try:
            thread = await bot.fetch_channel(thread_id)
            await thread.delete()
        except Exception as e:
            await ctx.send(f"⚠️ Could not delete archive thread: {e}")
            return
    metadata["status"] = "deleted"
    try:
        await update_archive_card(archive_message, metadata)
    except Exception as e:
        print(f"⚠️ Failed to update archive card: {e}")
    logs = load_logs()
    logs = [entry for entry in logs if normalize_archive_id(
        entry.get("archive_id")) != normalize_archive_id(archive_id)]
    write_logs(logs)
    await ctx.send(f"🗑️ Archive {archive_id} cleaned up.")


@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(build_help_text())

print("🚀 Starting bot...")
bot.run(TOKEN)
