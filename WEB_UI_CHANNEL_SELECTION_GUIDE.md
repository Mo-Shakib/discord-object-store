# Web UI Channel Selection Guide

## Overview

The DisBucket Web UI now supports **manual channel selection** for uploads, giving you full control over where your files are stored on Discord.

---

## How to Choose a Channel When Uploading

### Step 1: Access the Web UI

Open your browser and navigate to:
```
http://127.0.0.1:8000/
```

### Step 2: Go to Upload Section

Click on **"Upload Artifact"** in the sidebar navigation.

### Step 3: Fill Out the Upload Form

You'll see the following fields:

1. **File Selection**
   - Click or drag files/folders to the drop zone
   - Toggle "Upload as folder" to preserve directory structure

2. **Artifact Metadata**
   - **Title**: Optional name for your upload
   - **Tags**: Comma-separated tags (e.g., `backup, important, v1.0`)

3. **Storage Channel** ⭐ NEW!
   - **Dropdown menu** with available channels
   - Options include:
     - `Auto (Round-Robin Distribution)` - Default option
     - Your configured channels (e.g., `file-storage-vault`, `backup-storage`)

4. **Description**
   - Optional text description

5. **Require CLI Confirmation**
   - Checkbox for additional confirmation

### Step 4: Select Your Channel

**Option A: Automatic Distribution (Default)**
- Leave the dropdown set to `Auto (Round-Robin Distribution)`
- DisBucket will automatically distribute your files across all configured channels
- Best for general uploads and load balancing

**Option B: Specific Channel**
- Click the dropdown and select a specific channel
- Example: Choose `backup-storage` for critical backups
- Your upload will be stored exclusively in that channel
- Best for organized storage and easy retrieval

### Step 5: Upload

Click **"Start Upload"** button and monitor progress in the Dashboard.

---

## Visual Guide

```
╔═══════════════════════════════════════════════════════╗
║                   Upload New Artifact                 ║
╠═══════════════════════════════════════════════════════╣
║                                                       ║
║  📁 [Drop files or click to browse]                  ║
║     ☐ Upload as folder                               ║
║                                                       ║
║  ┌─────────────────┬──────────────────────────────┐  ║
║  │ Title           │ Tags                         │  ║
║  │ [            ]  │ [                          ] │  ║
║  └─────────────────┴──────────────────────────────┘  ║
║                                                       ║
║  Storage Channel (Optional - Auto if not selected)   ║
║  ┌────────────────────────────────────────────────┐  ║
║  │ # [Auto (Round-Robin Distribution)        ▼]  │  ║
║  └────────────────────────────────────────────────┘  ║
║    ℹ Select a specific channel or leave as Auto     ║
║                                                       ║
║  Description                                          ║
║  ┌────────────────────────────────────────────────┐  ║
║  │                                                │  ║
║  └────────────────────────────────────────────────┘  ║
║                                                       ║
║  ☐ Require CLI Confirmation    [🚀 Start Upload]    ║
╚═══════════════════════════════════════════════════════╝
```

---

## Channel Dropdown Options

### Dynamic Loading

The channel dropdown is **dynamically populated** from your `.env` configuration:

```env
STORAGE_CHANNEL_NAME=file-storage-vault,backup-storage,archive-vault
```

**Web UI will display:**
```
┌─────────────────────────────────────────┐
│ Auto (Round-Robin Distribution)         │  ← Default
├─────────────────────────────────────────┤
│ file-storage-vault                      │
│ backup-storage                          │
│ archive-vault                           │
└─────────────────────────────────────────┘
```

### Adding More Channels

To add more channels to the dropdown:

1. Edit your `.env` file:
   ```env
   STORAGE_CHANNEL_NAME=channel1,channel2,channel3
   ```

2. Restart the API server (uvicorn will auto-reload)

3. Refresh the Web UI

4. New channels appear in the dropdown automatically

---

## Use Cases

### Use Case 1: General File Storage (Auto Mode)
**Scenario:** Uploading miscellaneous files  
**Selection:** `Auto (Round-Robin Distribution)`  
**Result:** Files are distributed evenly across all channels for load balancing

### Use Case 2: Critical Backups
**Scenario:** Database backup files  
**Selection:** `backup-storage`  
**Result:** All backups stored in a dedicated channel for easy management

### Use Case 3: Media Files
**Scenario:** Large video/audio files  
**Selection:** `media-vault`  
**Result:** Media files isolated in their own channel

### Use Case 4: Project-Specific Storage
**Scenario:** Project Alpha artifacts  
**Selection:** `project-alpha-storage`  
**Result:** All project files in one channel for organizational clarity

---

## Technical Details

### API Endpoint

The channel selection feature uses the following API:

**Get Available Channels:**
```bash
GET /api/channels
```

**Response:**
```json
{
  "channels": [
    "file-storage-vault",
    "backup-storage",
    "archive-vault"
  ],
  "default_distribution": "round-robin"
}
```

**Upload with Channel:**
```bash
POST /api/jobs/upload
Form Data:
  - files: (file data)
  - title: "My Upload"
  - tags: "tag1, tag2"
  - channel: "backup-storage"  ← Specify channel here
  - description: "Description"
  - confirm: false
```

### Form Data

The upload form sends the following data:

```javascript
FormData {
  files: FileList,
  title: "string",
  tags: "string",
  channel: "string",        // Empty for Auto, or channel name
  description: "string",
  confirm: boolean
}
```

---

## Verification

### Check Your Upload

After uploading with a specific channel:

1. Go to **"File Batches"** section
2. Click on your batch to expand details
3. Look for **"Storage Channel"** field
4. Verify it shows the channel you selected

**Example:**
```
┌──────────┬──────┬─────────────────────┬─────────────┐
│ Title    │ Tags │ Storage Channel     │ Description │
├──────────┼──────┼─────────────────────┼─────────────┤
│ Backup   │ DB   │ # backup-storage    │ Jan backup  │
└──────────┴──────┴─────────────────────┴─────────────┘
```

---

## Troubleshooting

### Issue 1: No Channels in Dropdown

**Problem:** Dropdown only shows "Auto (Round-Robin)"

**Solution:**
1. Check your `.env` file has `STORAGE_CHANNEL_NAME` configured
2. Ensure channels are comma-separated
3. Restart the API server
4. Refresh the browser

### Issue 2: Channel Not Created on Discord

**Problem:** Selected channel doesn't exist on Discord

**Solution:**
- DisBucket will automatically create the channel if it doesn't exist
- Ensure your bot has proper permissions in the Discord server
- Check bot has "Manage Channels" permission

### Issue 3: Upload Fails with Channel Selected

**Problem:** Upload fails when specific channel is chosen

**Solution:**
1. Verify the channel name matches exactly (case-sensitive)
2. Check Discord rate limits
3. View Dashboard logs for detailed error messages

---

## Keyboard Shortcuts

When in the Upload form:

- `Tab` - Navigate between fields
- `Space` - Toggle folder mode checkbox
- `Enter` - Submit form (when not in text area)
- `↑↓` - Navigate channel dropdown when focused

---

## Best Practices

### 1. Use Auto Mode for Regular Uploads
Let DisBucket handle distribution for optimal load balancing.

### 2. Reserve Specific Channels for Important Data
Create dedicated channels for:
- Daily/weekly backups
- Project-specific files
- Large media libraries
- Archive storage

### 3. Use Descriptive Channel Names
```env
# Good
STORAGE_CHANNEL_NAME=db-backups,media-vault,project-alpha

# Bad
STORAGE_CHANNEL_NAME=channel1,channel2,storage
```

### 4. Document Your Channel Strategy
Keep a mapping of what each channel is used for:

| Channel | Purpose | Example Content |
|---------|---------|----------------|
| file-storage-vault | General files | Mixed content |
| backup-storage | Critical backups | Database dumps |
| media-vault | Large media | Videos, audio |
| archive-vault | Long-term storage | Old projects |

---

## CLI vs Web UI Channel Selection

### CLI Method

```bash
# Manual channel selection
python bot.py upload /path/to/files --channel backup-storage

# Interactive selection
python bot.py upload /path/to/files
# CLI will prompt: "Select channel or press Enter for auto"
```

### Web UI Method

```
1. Open http://127.0.0.1:8000/
2. Click "Upload Artifact"
3. Select channel from dropdown
4. Click "Start Upload"
```

### Comparison

| Feature | CLI | Web UI |
|---------|-----|--------|
| Channel Selection | `--channel` flag or interactive | Dropdown menu |
| Visual Feedback | Terminal output | Real-time dashboard |
| Progress Tracking | Text-based | Visual progress bar |
| Multi-file Support | Native | Drag & drop |
| Convenience | Command-line power users | Visual preference |

Both methods use the **same backend** and produce **identical results**.

---

## Summary

✅ **Channel selection is now available in the Web UI**  
✅ **Dynamically loads channels from configuration**  
✅ **Default is Auto (Round-Robin) for easy use**  
✅ **Supports manual selection for organized storage**  
✅ **Works identically to CLI channel selection**

**Get Started:**
1. Open Web UI: http://127.0.0.1:8000/
2. Go to Upload section
3. Choose your channel
4. Upload!

---

**Need Help?**
- Check `user-guide.md` for full DisBucket documentation
- View `WEB_UI_TEST_REPORT.md` for compatibility details
- Run `python bot.py channels` to see configured channels

