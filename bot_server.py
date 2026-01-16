import discord
from discord.ext import commands
import os
import json
import datetime
import glob
import re

# --- CONFIGURATION ---
UPLOAD_FOLDER = '/Volumes/Local Drive/DiscordDrive/Uploads'
DOWNLOAD_FOLDER = '/Volumes/Local Drive/DiscordDrive/Downloads'
# Gets the directory where main.py actually lives

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = '/Users/shakib/discord-drive-history.json'
print(f"🧭 Log file path: {os.path.abspath(LOG_FILE)}")

MANIFEST_PATTERNS = []
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
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise SystemExit("❌ DISCORD_BOT_TOKEN not set. Add it to .env or your environment.")

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

def append_log(entry):
    logs = load_logs()
    logs.append(entry)
    write_logs(logs)

def find_log_index(logs, archive_id=None, lot=None):
    normalized_target = normalize_archive_id(archive_id) if archive_id else None
    for index, entry in enumerate(logs):
        if normalized_target:
            entry_id = normalize_archive_id(entry.get("archive_id")) or entry.get("archive_id")
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
        "- `!help`\n"
    )

def get_next_lot():
    logs = load_logs()
    if not logs:
        return 1
    return max(int(entry.get('lot', 0)) for entry in logs) + 1

@bot.event
async def on_ready():
    print(f"🟢 Bot online as {bot.user.name} (ID: {bot.user.id})")
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
    
    # 1. Send metadata
    header = await ctx.send(f"📦 **Archive: {archive_id}** | **Timestamp: {timestamp}**")
    
    # 2. Gather files (.bin and manifest .json files)
    files_to_upload = list_upload_files()
    
    if not files_to_upload:
        print("⚠️ No files found to upload.")
        await ctx.send("⚠️ No files found in the upload folder.")
        return

    total_size_bytes = calculate_total_size(files_to_upload)
    status_msg = await ctx.send(
        f"📤 Uploading {len(files_to_upload)} file(s) ({format_bytes(total_size_bytes)})..."
    )
    uploaded_message_ids = [header.id, status_msg.id]
    uploaded_files = []
    failed_files = []
    errors = {}
    
    # 3. Upload files
    print(f"📦 Uploading {len(files_to_upload)} file(s) from {UPLOAD_FOLDER}...")
    for file_path in files_to_upload:
        file_name = os.path.basename(file_path)
        print(f"⬆️ Uploading file: {file_name}")
        try:
            discord_file = discord.File(file_path)
            msg = await ctx.send(file=discord_file)
            uploaded_message_ids.append(msg.id)
            uploaded_files.append(file_name)
            try:
                os.remove(file_path)
                print(f"🗑️ Removed uploaded file: {file_name}")
            except OSError as e:
                print(f"⚠️ Could not delete {file_name} after upload: {e}")
        except Exception as e:
            failed_files.append(file_name)
            errors[file_name] = str(e)
            print(f"❌ Failed to upload {file_name}: {e}")

    status = "success" if not failed_files else "failed"
    entry = {
        "lot": lot_num,
        "archive_id": archive_id,
        "timestamp": timestamp,
        "message_ids": uploaded_message_ids,
        "status": status,
        "file_count": len(files_to_upload),
        "total_size_bytes": total_size_bytes,
        "uploaded_files": uploaded_files,
        "failed_files": failed_files,
    }
    if errors:
        entry["errors"] = errors
    append_log(entry)

    if status == "success":
        print(f"✅ Upload complete for Archive {archive_id}. Logged {len(uploaded_message_ids)} message(s).")
        await ctx.send(
            f"✅ Archive {archive_id} uploaded successfully.\n"
            f"📦 Files: {len(files_to_upload)} • Size: {format_bytes(total_size_bytes)}"
        )
    else:
        print(f"⚠️ Upload completed with errors for Archive {archive_id}.")
        await ctx.send(
            f"⚠️ Archive {archive_id} uploaded with errors.\n"
            f"✅ Uploaded: {len(uploaded_files)}/{len(files_to_upload)} • "
            f"Size: {format_bytes(total_size_bytes)}\n"
            "🔁 Use `!resume` to continue."
        )

@bot.command()
async def download(ctx, start: str, end: str = None):
    print(f"📥 Download command received from {ctx.author} in {ctx.channel}.")
    
    if not os.path.exists(LOG_FILE):
        print("❌ No log file found; cannot download.")
        await ctx.send("No log file found.")
        return

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

    print(f"📦 Preparing download for {len(target_lots)} lot(s) into {DOWNLOAD_FOLDER}...")
    total_lots = len(target_lots)
    for index, lot_data in enumerate(target_lots, start=1):
        archive_id = get_archive_id_from_entry(lot_data)
        print(f"⏳ Processing {index}/{total_lots} Lots (Archive {archive_id})...")
        archive_folder = f"[Archive] {archive_id}"
        lot_dir = os.path.join(DOWNLOAD_FOLDER, archive_folder)
        legacy_dir = os.path.join(DOWNLOAD_FOLDER, f"Lot_{lot_data['lot']}")
        if not os.path.exists(lot_dir) and os.path.exists(legacy_dir):
            try:
                os.rename(legacy_dir, lot_dir)
            except OSError as e:
                print(f"⚠️ Could not rename {legacy_dir} to {lot_dir}: {e}")
        os.makedirs(lot_dir, exist_ok=True)

        archive_size_bytes = lot_data.get("total_size_bytes")
        archive_size_text = format_bytes(archive_size_bytes) if archive_size_bytes is not None else "Unknown size"
        archive_file_count = lot_data.get("file_count")
        archive_file_text = (
            f"{archive_file_count} files" if isinstance(archive_file_count, int) else "Unknown file count"
        )
        await ctx.send(
            f"📦 **Downloading Archive: {archive_id}**\n"
            f"📄 {archive_file_text} • 📦 {archive_size_text}"
        )
        
        # Fetch the messages using the saved IDs
        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_files_known = 0
        expected_total_files = lot_data.get("file_count")
        for msg_id in lot_data['message_ids']:
            try:
                msg = await ctx.channel.fetch_message(msg_id)
                if expected_total_files is None:
                    total_files_known += len(msg.attachments)
                for attachment in msg.attachments:
                    file_path = os.path.join(lot_dir, attachment.filename)
                    if os.path.exists(file_path):
                        skipped_count += 1
                        total_files = expected_total_files if expected_total_files is not None else total_files_known
                        left = max(total_files - (success_count + failed_count + skipped_count), 0)
                        print(
                            f"📥 Downloaded {success_count}/{total_files} files "
                            f"(✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • ⏳ {left} left)"
                        )
                        continue
                    try:
                        await attachment.save(file_path)
                        success_count += 1
                    except Exception as e:
                        failed_count += 1
                        print(f"❌ Failed to save {attachment.filename}: {e}")
                    total_files = expected_total_files if expected_total_files is not None else total_files_known
                    left = max(total_files - (success_count + failed_count + skipped_count), 0)
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
        else:
            await ctx.send(
                f"⚠️ Archive {archive_id} downloaded with errors.\n"
                f"✅ {success_count} • ❌ {failed_count} • ⏭️ {skipped_count} • 📦 {final_total}\n"
                "🔁 Re-run `!download` to resume."
            )

    print(f"✅ Download complete for {start_label} to {end_label}.")
    await ctx.send(f"✅ Downloaded {start_label} to {end_label} to your local folder.")

@bot.command()
async def resume(ctx, archive_id: str = None):
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
        path = name if os.path.isabs(name) else os.path.join(UPLOAD_FOLDER, name)
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

    for file_path in file_paths:
        file_name = os.path.basename(file_path)
        print(f"⬆️ Resuming upload: {file_name}")
        try:
            discord_file = discord.File(file_path)
            msg = await ctx.send(file=discord_file)
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
    if errors:
        entry["errors"] = errors

    original_count = entry.get("file_count")
    if original_count is None:
        entry["file_count"] = len(set(uploaded_files + failed_files))

    if entry.get("total_size_bytes") is None:
        entry["total_size_bytes"] = total_size_bytes

    entry["status"] = "success" if not failed_files else "failed"
    logs[target_index] = entry
    write_logs(logs)

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
    last_archive = get_archive_id_from_entry(last_entry) if last_entry else "none"
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
            file_count = len(set(uploaded + failed)) if (uploaded or failed) else "?"
        total_size_bytes = entry.get("total_size_bytes")
        size_text = format_bytes(total_size_bytes) if total_size_bytes is not None else "Unknown size"
        timestamp = entry.get("timestamp", "unknown time")
        status_emoji = "✅" if status == "success" else ("⚠️" if status == "failed" else "❔")
        lines.append(
            f"{status_emoji} {archive_id} • {file_count} files • {size_text} • {timestamp}"
        )

    await ctx.send("\n".join(lines))

@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(build_help_text())

print("🚀 Starting bot...")
bot.run(TOKEN)
