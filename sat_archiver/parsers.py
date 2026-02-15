"""Metadata extraction from filenames, folder names, and JSON files."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import (
    COMMENT_FOLDER_RE,
    NAMED_STORY_FOLDER_RE,
    POST_FOLDER_RE,
    PROFILE_FOLDER_RE,
    STORIES_TXT_FOLDER_RE,
    STORY_FILE_RE,
    WPAS_RE,
)
from .models import ContentItem


def parse_path_context(rel_parts: tuple[str, ...]) -> dict:
    """Extract batch, section, category, WPAS code from relative path components.

    rel_parts is relative to the SAT Checks - TO - RTA/ directory.
    Example: ("Batch 1", "Books", "WPAS B MULTI", "file.mp4")
    """
    ctx: dict = {"batch": "", "section": "", "category": "", "wpas_code": ""}
    if not rel_parts:
        return ctx

    ctx["batch"] = rel_parts[0]  # "Batch 1", "Batch 2", "MGT Check"

    if ctx["batch"].startswith("Batch"):
        # Batch folders: Batch / Category / [WPAS or sub-category] / ...
        if len(rel_parts) > 1:
            ctx["category"] = rel_parts[1]  # "Books", "Food", etc.
        if len(rel_parts) > 2:
            wpas_match = WPAS_RE.match(rel_parts[2])
            if wpas_match:
                ctx["wpas_code"] = wpas_match.group(1)
                ctx["section"] = rel_parts[2]
            else:
                ctx["section"] = rel_parts[2]  # "Community", "Featured", etc.
    else:
        # MGT Check: MGT Check / Section (SAT MO, SAT P&V) / ...
        if len(rel_parts) > 1:
            ctx["section"] = rel_parts[1]  # "SAT MO", "SAT P&V"

    return ctx


def parse_metadata_json(json_path: Path) -> dict:
    """Read and parse a post's metadata.json file."""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        return {
            "username": data.get("username", ""),
            "full_name": data.get("full_name", ""),
            "shortcode": data.get("shortcode", ""),
            "caption": data.get("caption", ""),
            "like_count": data.get("like_count", 0),
            "comment_count": data.get("comment_count", 0),
            "posted_at": data.get("posted_at", ""),
            "media_type": data.get("media_type", ""),
            "is_video": data.get("is_video", False),
            "post_url": data.get("post_url", ""),
            "post_type": data.get("post_type", ""),
        }
    except (json.JSONDecodeError, OSError) as exc:
        print(f"  Warning: could not read metadata: {json_path} ({exc})")
        return {}


def parse_story_filename(filename: str) -> Optional[dict]:
    """Parse a Type A story filename. Returns dict or None."""
    m = STORY_FILE_RE.match(filename)
    if not m:
        return None
    prefix, date_str, time_str, seq, shortcode, suffix, ext = m.groups()
    username = extract_username_from_story_prefix(prefix)
    full_name = ""
    if " " in prefix:
        # "Candice Richter loveinhealing" -> full_name = "Candice Richter"
        parts = prefix.rsplit(" ", 1)
        full_name = parts[0]

    raw_ext = ext if suffix == "raw" else ""

    return {
        "username": username,
        "full_name": full_name,
        "shortcode": shortcode,
        "date_str": date_str,
        "time_str": time_str,
        "seq": seq,
        "suffix": suffix,
        "ext": ext,
        "raw_ext": raw_ext,
    }


def extract_username_from_story_prefix(prefix: str) -> str:
    """Extract the Instagram username from a story filename prefix.

    Handles edge case: "Candice Richter loveinhealing" -> "loveinhealing"
    Normal case: "evinator" -> "evinator"
    """
    # Username is the last space-separated token
    return prefix.rsplit(" ", 1)[-1] if " " in prefix else prefix


def parse_post_folder(folder_name: str) -> Optional[dict]:
    """Parse a Type B post folder name."""
    m = POST_FOLDER_RE.match(folder_name)
    if not m:
        return None
    username, date_str, shortcode = m.groups()
    return {
        "username": username,
        "date_str": date_str,
        "shortcode": shortcode,
    }


def parse_profile_folder(folder_name: str) -> Optional[dict]:
    """Parse a Type D profile folder name."""
    m = PROFILE_FOLDER_RE.match(folder_name)
    if not m:
        return None
    date_str, full_name, handle = m.groups()
    return {
        "date_str": date_str,
        "full_name": full_name,
        "handle": handle,
    }


def parse_comment_folder(folder_name: str) -> Optional[dict]:
    """Parse a Type D comment thread folder name."""
    m = COMMENT_FOLDER_RE.match(folder_name)
    if not m:
        return None
    date_str, handle = m.groups()
    return {
        "date_str": date_str,
        "handle": handle,
    }


def parse_named_story_folder(folder_name: str) -> Optional[dict]:
    """Parse a Type E named story folder."""
    m = NAMED_STORY_FOLDER_RE.match(folder_name)
    if m:
        date_str, full_name, handle = m.groups()
        return {"date_str": date_str, "full_name": full_name, "handle": handle}
    # Try IG Stories TXT variant
    m = STORIES_TXT_FOLDER_RE.match(folder_name)
    if m:
        date_str, handle = m.groups()
        return {"date_str": date_str, "full_name": "", "handle": handle}
    return None


def generate_pseudo_shortcode(handle: str, date_str: str, folder_name: str) -> str:
    """Generate a deterministic pseudo-shortcode for items without an Instagram shortcode.

    Format: NOID_{handle}_{date}_{hash8}
    The hash is based on the full folder name for determinism.
    """
    h = hashlib.sha256(folder_name.encode("utf-8")).hexdigest()[:8]
    return f"NOID_{handle}_{date_str}_{h}"


def format_date(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, or pass through if already formatted."""
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str  # already YYYY-MM-DD or other format


def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")
