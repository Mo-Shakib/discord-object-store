"""Archive card creation and parsing for Discord embeds."""

import json
import re
from typing import Any, Dict, List, Optional

import discord

from ...common.constants import STATUS_COLORS
from ...common.utils import format_bytes, safe_str


def _build_files_field(metadata: Dict[str, Any]) -> str:
    """Build the files field for the embed."""
    files = metadata.get("files_display") or []
    if isinstance(files, str):
        return files
    if isinstance(files, list):
        if not files:
            count = metadata.get("file_count")
            return f"{count} files" if isinstance(count, int) else "Unknown"
        if len(files) > 10:
            return f"{len(files)} files (showing 10)\n" + "\n".join(files[:10])
        return "\n".join(files)
    count = metadata.get("file_count")
    return f"{count} files" if isinstance(count, int) else "Unknown"


def _status_label(status: Optional[str]) -> str:
    """Get status label."""
    if not status:
        return "unknown"
    return status


def build_archive_embed(metadata: Dict[str, Any]) -> discord.Embed:
    """
    Build a Discord embed for an archive.
    
    Args:
        metadata: Archive metadata dictionary
    
    Returns:
        Discord Embed object
    """
    archive_id = metadata.get("archive_id") or "unknown"
    status = (metadata.get("status") or "unknown").lower()
    color = STATUS_COLORS.get(status, STATUS_COLORS["unknown"])
    
    embed = discord.Embed(
        title=f"📦 Archive {archive_id}",
        color=color,
    )
    
    embed.add_field(
        name="📅 Timestamp",
        value=safe_str(metadata.get("timestamp")),
        inline=False
    )
    embed.add_field(
        name="📁 Files",
        value=_build_files_field(metadata),
        inline=False
    )
    embed.add_field(
        name="📊 Total Size",
        value=format_bytes(metadata.get("total_size_bytes")),
        inline=True
    )
    
    chunk_count = metadata.get("chunk_count")
    chunk_text = f"{chunk_count} chunks" if isinstance(chunk_count, int) else "Unknown"
    embed.add_field(name="🧩 Chunks", value=chunk_text, inline=True)
    embed.add_field(name="✅ Status", value=_status_label(status), inline=True)
    embed.add_field(
        name="💾 Download",
        value=f"`!download {archive_id}`",
        inline=False,
    )
    
    progress_text = metadata.get("progress_text")
    if progress_text:
        embed.add_field(name="⏳ Progress", value=progress_text, inline=False)
    
    footer_parts = []
    if metadata.get("lot") is not None:
        footer_parts.append(f"Lot {metadata.get('lot')}")
    uploader = metadata.get("uploader")
    if uploader:
        footer_parts.append(f"Uploader: {uploader}")
    if footer_parts:
        embed.set_footer(text=" • ".join(footer_parts))
    
    return embed


def _serialize_metadata(metadata: Dict[str, Any]) -> str:
    """Serialize metadata to JSON string."""
    payload = dict(metadata)
    
    # Truncate large lists
    for key in ("uploaded_files", "failed_files", "message_ids"):
        value = payload.get(key)
        if isinstance(value, list) and len(value) > 120:
            payload[key] = value[:120]
            payload[f"{key}_truncated"] = True
    
    try:
        serialized = json.dumps(
            payload, ensure_ascii=True, separators=(",", ":")
        )
        if len(serialized) > 1800:
            for key in ("uploaded_files", "failed_files", "message_ids"):
                payload.pop(key, None)
            payload["metadata_truncated"] = True
            serialized = json.dumps(
                payload, ensure_ascii=True, separators=(",", ":")
            )
        return serialized
    except TypeError:
        sanitized = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            elif isinstance(value, list):
                sanitized[key] = value
            else:
                sanitized[key] = safe_str(value)
        return json.dumps(sanitized, ensure_ascii=True, separators=(",", ":"))


def _extract_json_from_content(content: str) -> Optional[Dict[str, Any]]:
    """Extract JSON from message content."""
    if not content:
        return None
    
    code_block_match = re.search(
        r"```json\s*(\{.*?\})\s*```", content, re.DOTALL
    )
    if code_block_match:
        raw = code_block_match.group(1)
    else:
        raw_match = re.search(r"(\{.*\})", content, re.DOTALL)
        raw = raw_match.group(1) if raw_match else None
    
    if not raw:
        return None
    
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def create_archive_card(
    channel: discord.TextChannel,
    archive_id: str,
    metadata: Dict[str, Any]
) -> discord.Message:
    """
    Create an archive card in Discord.
    
    Args:
        channel: Discord channel to send to
        archive_id: Archive ID
        metadata: Archive metadata
    
    Returns:
        Discord Message object
    """
    payload = dict(metadata)
    payload["archive_id"] = archive_id
    
    embed = build_archive_embed(payload)
    content = f"```json\n{_serialize_metadata(payload)}\n```"
    
    message = await channel.send(content=content, embed=embed)
    
    for reaction in ("✅", "⚠️", "🗑️"):
        try:
            await message.add_reaction(reaction)
        except discord.HTTPException:
            pass
    
    return message


async def update_archive_card(
    message: discord.Message,
    metadata: Dict[str, Any]
) -> None:
    """
    Update an existing archive card.
    
    Args:
        message: Discord message to update
        metadata: Updated metadata
    """
    payload = dict(metadata)
    embed = build_archive_embed(payload)
    content = f"```json\n{_serialize_metadata(payload)}\n```"
    await message.edit(content=content, embed=embed)


def parse_archive_card(message: discord.Message) -> Optional[Dict[str, Any]]:
    """
    Parse metadata from an archive card message.
    
    Args:
        message: Discord message
    
    Returns:
        Metadata dictionary or None
    """
    metadata = _extract_json_from_content(message.content or "")
    
    if metadata is None and message.embeds:
        embed = message.embeds[0]
        metadata = {
            "archive_id": None,
            "timestamp": None,
            "status": None,
        }
        
        title = embed.title or ""
        match = re.search(r"#\d{6}-\d+", title)
        if match:
            metadata["archive_id"] = match.group(0)
        
        for field in embed.fields:
            name = field.name.lower()
            value = field.value
            if "timestamp" in name:
                metadata["timestamp"] = value
            elif "status" in name:
                metadata["status"] = value
            elif "files" in name:
                metadata["files_display"] = value.splitlines()
        
        footer = embed.footer.text if embed.footer else ""
        if footer:
            lot_match = re.search(r"lot\s+(\d+)", footer, re.IGNORECASE)
            if lot_match:
                metadata["lot"] = int(lot_match.group(1))
    
    if not metadata:
        return None
    
    metadata.setdefault("archive_message_id", message.id)
    return metadata


async def search_archives(
    channel: discord.TextChannel,
    query: Optional[str]
) -> List[discord.Message]:
    """
    Search for archives in a channel.
    
    Args:
        channel: Discord channel to search
        query: Search query string
    
    Returns:
        List of matching Discord messages
    """
    matches: List[discord.Message] = []
    query_norm = query.lower() if query else None
    
    async for message in channel.history(limit=200):
        if not message.embeds:
            continue
        
        embed = message.embeds[0]
        title = (embed.title or "").lower()
        if "archive" not in title:
            continue
        
        if not query_norm:
            matches.append(message)
            if len(matches) >= 10:
                break
            continue
        
        metadata = parse_archive_card(message) or {}
        archive_id = safe_str(metadata.get("archive_id")).lower()
        files = metadata.get("uploaded_files") or metadata.get("files_display") or []
        files_text = " ".join(files).lower() if isinstance(files, list) else safe_str(files).lower()
        timestamp = safe_str(metadata.get("timestamp")).lower()
        
        if query_norm in title or query_norm in archive_id or query_norm in files_text or query_norm in timestamp:
            matches.append(message)
    
    return matches
