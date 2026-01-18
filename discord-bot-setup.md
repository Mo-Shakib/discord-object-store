# Complete Step-by-Step Guide: Creating Your Discord Storage Bot

Choose name for your bot, for this guide, the example name is: **VaultKeeper**

---

## 📋 Prerequisites

Before starting, ensure you have:
- A Discord account
- A Discord server where you have Administrator permissions
- A web browser
- 10-15 minutes

---

## 🚀 Step-by-Step Bot Creation Process

### STEP 1: Access Discord Developer Portal

1. Open your web browser.
2. Go to: `https://discord.com/developers/applications`
3. Click the "Log In" button (top right).
4. Enter your Discord credentials.
5. Complete any 2FA if enabled.

Checkpoint: You should see the "Applications" page with a dark theme interface.

### STEP 2: Create New Application

1. Click the "New Application" button (top right, blue button).
2. A popup appears: "Create an Application".
3. In the "NAME" field, type: `VaultKeeper`.
4. Check the box: "I agree to the Discord Developer Terms of Service and Developer Policy".
5. Click "Create".

Checkpoint: You're now on the "General Information" page for VaultKeeper.

### STEP 3: Configure Application Settings (Optional but Recommended)

On the "General Information" page:

**Add an App Icon (optional):**
1. Click "Upload Image" under APP ICON.
2. Use a 512x512px image (vault/lock icon recommended).
3. Optional: free icons at `https://www.flaticon.com` (search "vault").

**Add Description:**
```
Secure file storage bot that encrypts and stores your files using Discord as a backend. Upload, manage, and retrieve your files with military-grade encryption.
```

**Add Tags (helps others find your bot if public):**
- utility
- storage
- security

Click "Save Changes" (bottom right).

Checkpoint: Your application information is saved.

### STEP 4: Create the Bot User

1. In the left sidebar, click "Bot" (under SETTINGS).
2. You'll see "Build-A-Bot".
3. Click the "Add Bot" button.
4. A confirmation popup appears: "Add a bot to this app?".
5. Click "Yes, do it!".

Checkpoint: You now see a BOT section with a token field (hidden by default).

### STEP 5: Configure Bot Settings

On the Bot page, configure these settings:

**A. Public Bot (Recommended: OFF)**
- Toggle OFF the "PUBLIC BOT" switch.
- Keep this OFF for security.

**B. Require OAuth2 Code Grant**
- Leave this OFF (default).

**C. Privileged Gateway Intents**
- PRESENCE INTENT: OFF
- SERVER MEMBERS INTENT: OFF
- MESSAGE CONTENT INTENT: ON (required for command functionality)

**D. Bot Permissions**
- Scroll down to "Bot Permissions" section (we'll set these properly in OAuth2 later).
- Click "Save Changes" (bottom right).

Checkpoint: Bot settings configured correctly.

### STEP 6: Copy Your Bot Token (IMPORTANT)

Security warning: the bot token is like a password. Never share it publicly.

1. On the Bot page, find the "TOKEN" section.
2. Click "Reset Token".
3. Confirm "Yes, do it!".
4. Click "Copy" to copy the token.
5. Immediately paste it in a secure location:
   - Open Notepad/TextEdit.
   - Paste the token.
   - Save as `discord_token_backup.txt`.
   - Store in a secure folder (not public).

Checkpoint: Token safely copied and saved.

### STEP 7: Configure OAuth2 Settings

1. In the left sidebar, click "OAuth2" (under SETTINGS).
2. Click the "URL Generator" sub-menu.

**A. Select Scopes**
- bot
- applications.commands (future feature support)

**B. Select Bot Permissions**

Text Permissions:
- Send Messages
- Send Messages in Threads
- Attach Files
- Read Message History
- Add Reactions (optional)

General Permissions:
- Manage Channels
- Manage Threads
- View Channels

Advanced:
- Manage Messages (optional, for cleanup)

**C. Permission Integer**
- Record the permission integer displayed at the bottom.
- Example: `274878294016`

### STEP 8: Generate Invite URL

1. Scroll to the "GENERATED URL" section.
2. Click "Copy" next to the URL.
3. Save it in your secure notes file (same file as the token).

Checkpoint: Invite URL generated and copied.

### STEP 9: Invite Bot to Your Server

1. Open a new browser tab.
2. Paste the invite URL.
3. Select your target server from the dropdown.
4. Click "Authorize".
5. Complete CAPTCHA if prompted.

Checkpoint: Bot is now in your server.

### STEP 10: Verify Bot is in Server

1. Open Discord (desktop app or browser).
2. Navigate to your server.
3. Check the member list (right sidebar).
4. Under "OFFLINE", you should see VaultKeeper with a "BOT" tag.

Checkpoint: Bot appears in server member list.

### STEP 11: Create Bot Configuration Summary

Create a file called `BOT_INFO.txt`:

```
=== VAULTKEEPER BOT CONFIGURATION ===

Bot Name: VaultKeeper
Application ID: [Developer Portal > General Information]
Bot Token: [Your copied token - KEEP SECURE]
Invite URL: [Generated OAuth2 URL]
Permissions Integer: 274878294016

Enabled Intents:
- Message Content Intent: ON

Permissions:
- Manage Channels
- Manage Threads
- Send Messages
- Send Messages in Threads
- Attach Files
- Read Message History
- View Channels

Server: [Your server name]
Date Created: [Today's date]

=== NEXT STEPS ===
1. Install Python 3.10+
2. Clone bot repository
3. Create .env file with token
4. Run setup.py
```

Save this file securely.

---

## 🔐 Security Checklist

Before proceeding, verify:
- Bot token saved in a secure location (not public)
- Public Bot setting is OFF
- Token never shared in Discord/forums/screenshots
- `.env` file is ignored by Git
- Only you have access to the bot application in Developer Portal

---

## 🎯 Quick Reference

| Item | Status | Location |
| --- | --- | --- |
| Bot Token | Saved | `BOT_INFO.txt` (secure location) |
| Invite URL | Saved | `BOT_INFO.txt` |
| Bot in Server | Added | Your Discord server |
| Message Content Intent | Enabled | Developer Portal > Bot |
| Permissions | Configured | OAuth2 settings |

---

## 📝 Permission Explanations

- Manage Channels: create storage and archive channels on first run
- Manage Threads: create dedicated threads for each upload batch
- Send Messages: post archive cards with batch information
- Send Messages in Threads: upload chunk files to threads
- Attach Files: upload `.bin` chunk files (up to Discord size limits)
- Read Message History: retrieve attachment URLs when downloading
- View Channels: see channels it created

---

## 🐛 Troubleshooting

**Problem: "Missing Access" when generating invite URL**  
Solution: Make sure you own the application and are logged into the correct Discord account.

**Problem: Bot appears but is offline**  
Solution: This is normal. The bot is online only when you run the Python script.

**Problem: Can't see bot in member list**  
Solution:
- Check server settings > Roles
- Ensure "VaultKeeper" role exists
- Refresh Discord (Cmd/Ctrl + R)

**Problem: Forgot to copy token**  
Solution:
- Go to Developer Portal > Your Application > Bot
- Click "Reset Token"
- Copy the new token (old one is invalid)
- Update your `.env` file

**Problem: Bot invite link doesn't work**  
Solution:
- Regenerate URL in OAuth2 > URL Generator
- Ensure you have "Manage Server" permission
- Try in incognito/private browsing mode

---

## ✅ Final Verification Steps

Before moving to implementation:

1. Developer Portal: `https://discord.com/developers/applications`
2. Verify Bot Page:
   - "MESSAGE CONTENT INTENT" is ON
   - "PUBLIC BOT" is OFF
3. Verify OAuth2:
   - Scopes selected: bot, applications.commands
   - Permissions match checklist above
4. Verify In Discord:
   - Bot appears in member list (offline is normal)

---

## 🎉 Success! You're Ready for Next Steps

Your bot is now created and configured. Next steps:
- Set up development environment (Python 3.10+)
- Clone/create the bot code
- Create `.env` file with your bot token
- Run `setup.py` to initialize
- Start uploading files
