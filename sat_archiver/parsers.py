"""Metadata extraction from filenames, folder names, and JSON files."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .config import (
    COLLAB_FOLDER_RE,
    COMMENT_FOLDER_RE,
    MO_PATH_TO_COLUMN,
    NAMED_STORY_FOLDER_RE,
    POST_FOLDER_RE,
    PROFILE_FOLDER_RE,
    RESHARE_FOLDER_RE,
    STORIES_TXT_FOLDER_RE,
    STORY_CATEGORY_TO_COLUMN,
    STORY_FILE_RE,
    VE_FILE_RE,
    PROFILE_FILE_RE,
    WPAS_RE,
)
from .models import ContentItem


# ── SAT Daily path context parsers ────────────────────────────────────────────

def parse_sat_daily_stories_context(rel_parts: tuple[str, ...]) -> dict:
    """Extract batch, dropdown column, dropdown value, WPAS code from Stories hierarchy.

    rel_parts is relative to SAT Checks - X - RTA/Stories/.
    Example: ("Batch 1", "Books", "WPAS B Plus", "file.mp4")
    Example: ("Batch 2", "Healing Tools", "WPAS CJ", "Advanced", "file.mp4")
    """
    ctx: dict = {
        "batch": "",
        "dropdown_column": "",
        "dropdown_value": "",
        "wpas_code": "",
    }
    if not rel_parts:
        return ctx

    ctx["batch"] = rel_parts[0]  # "Batch 1", "Batch 2"

    if len(rel_parts) > 1:
        category = rel_parts[1]  # "Books", "Food", "Healing Tools", etc.
        col = STORY_CATEGORY_TO_COLUMN.get(category, "")
        ctx["dropdown_column"] = col

    if len(rel_parts) > 2:
        wpas_match = WPAS_RE.match(rel_parts[2])
        if wpas_match:
            ctx["wpas_code"] = wpas_match.group(1)
            ctx["dropdown_value"] = wpas_match.group(1)
        else:
            # Non-WPAS subfolder (e.g. "Community", "Featured")
            ctx["dropdown_value"] = rel_parts[2]

    # Deeper subfolders can refine the value (e.g. "Advanced", "Exposures")
    # but skip content-type folders (IG Stories TXT, IG Stories, etc.)
    if len(rel_parts) > 3:
        sub = rel_parts[3]
        is_content_folder = (
            sub.startswith("IG Stories")
            or sub.startswith("IG Reshare")
            or sub.startswith("IG Profile")
            or sub.startswith("IG Regular Comment")
            or STORY_FILE_RE.match(sub)
        )
        if not is_content_folder:
            base = ctx["dropdown_value"]
            ctx["dropdown_value"] = f"{base} / {sub}"

    return ctx


def parse_sat_daily_mo_context(rel_parts: tuple[str, ...]) -> dict:
    """Extract MO column + value from Additional/MO/{type}/{category} hierarchy.

    rel_parts is relative to SAT Checks - X - RTA/Additional/MO/.
    Example: ("PW", "History - Lifestyle", "file.mp4")
    """
    ctx: dict = {"mo_column": "", "mo_value": ""}
    if not rel_parts:
        return ctx

    mo_type = rel_parts[0]  # "PW", "RPT", "SI", "TS", "WTS"
    ctx["mo_column"] = MO_PATH_TO_COLUMN.get(mo_type, "")

    if len(rel_parts) > 1:
        ctx["mo_value"] = rel_parts[1]  # "History - Lifestyle", etc.

    return ctx


def parse_daily_mo_context(section: str, rel_parts: tuple[str, ...]) -> dict:
    """Extract context from Daily MO folder hierarchy.

    section: "categories", "reshares", "manual", "profile", "ve"
    rel_parts: path components relative to the section folder.
    """
    ctx: dict = {
        "mo_column": "",
        "mo_value": "",
        "resharer_username": "",
        "resharer_name": "",
        "sheet_categories": "",
    }

    if section == "categories":
        # Categories/{category_name}/...
        # category_name becomes mo_pw value
        ctx["mo_column"] = "mo_pw"
        if rel_parts:
            ctx["mo_value"] = rel_parts[0]

    elif section == "reshares":
        # Reshares/{IG Reshare - date - Name - handle}/{category}/{username}/{post}/...
        ctx["sheet_categories"] = "Reshare"
        if rel_parts:
            reshare_info = parse_reshare_folder(rel_parts[0])
            if reshare_info:
                ctx["resharer_username"] = reshare_info["handle"]
                ctx["resharer_name"] = reshare_info["full_name"]
            # Category after resharer folder
            if len(rel_parts) > 1:
                ctx["mo_column"] = "mo_pw"
                ctx["mo_value"] = rel_parts[1]

    return ctx


# ── Reshare folder parser ─────────────────────────────────────────────────────

def parse_reshare_folder(folder_name: str) -> Optional[dict]:
    """Parse IG Reshare - YYYY-MM-DD - Name - handle folder."""
    m = RESHARE_FOLDER_RE.match(folder_name)
    if not m:
        return None
    date_str, full_name, handle = m.groups()
    return {"date_str": date_str, "full_name": full_name, "handle": handle}


# ── Collaborator extraction ───────────────────────────────────────────────────

def extract_collaborators(folder_name: str, metadata: dict | None = None) -> str:
    """Extract collaborator usernames from metadata.json or folder name _collab_ pattern.

    Returns comma-separated string.
    """
    # Prefer metadata.json collaborators field
    if metadata and metadata.get("collaborators"):
        collabs = metadata["collaborators"]
        if isinstance(collabs, list):
            return ", ".join(collabs)
        return str(collabs)

    # Fall back to folder name pattern
    m = COLLAB_FOLDER_RE.search(folder_name)
    if m:
        # e.g. _collab_mayuwater or _collab_user1_user2
        raw = m.group(1)
        # Split on underscores, but usernames can contain dots/underscores...
        # The collab part is everything after _collab_, separated by underscores
        return raw.replace("_", ", ")

    return ""


# ── VE file parser ────────────────────────────────────────────────────────────

def parse_ve_file(filename: str) -> Optional[dict]:
    """Parse an IG VE filename."""
    m = VE_FILE_RE.match(filename)
    if not m:
        return None
    date_part, full_name, handle = m.groups()
    return {"date_str": date_part, "full_name": full_name, "handle": handle}


# ── Profile screenshot file parser ────────────────────────────────────────────

def parse_profile_file(filename: str) -> Optional[dict]:
    """Parse a profile screenshot filename like {username}_profile_{YYYYMMDD}.png."""
    m = PROFILE_FILE_RE.match(filename)
    if not m:
        return None
    username, date_str, ext = m.groups()
    return {"username": username, "date_str": date_str}


# ── Existing parsers (preserved) ─────────────────────────────────────────────

def parse_path_context(rel_parts: tuple[str, ...]) -> dict:
    """Extract batch, section, category, WPAS code from relative path components.

    Legacy function for backward compatibility.
    rel_parts is relative to the SAT Checks - TO - RTA/ directory.
    """
    ctx: dict = {"batch": "", "section": "", "category": "", "wpas_code": ""}
    if not rel_parts:
        return ctx

    ctx["batch"] = rel_parts[0]

    if ctx["batch"].startswith("Batch"):
        if len(rel_parts) > 1:
            ctx["category"] = rel_parts[1]
        if len(rel_parts) > 2:
            wpas_match = WPAS_RE.match(rel_parts[2])
            if wpas_match:
                ctx["wpas_code"] = wpas_match.group(1)
                ctx["section"] = rel_parts[2]
            else:
                ctx["section"] = rel_parts[2]
    else:
        if len(rel_parts) > 1:
            ctx["section"] = rel_parts[1]

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
            "collaborators": data.get("collaborators", []),
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
    """Extract the Instagram username from a story filename prefix."""
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
    m = STORIES_TXT_FOLDER_RE.match(folder_name)
    if m:
        date_str, handle = m.groups()
        return {"date_str": date_str, "full_name": "", "handle": handle}
    return None


def generate_pseudo_shortcode(handle: str, date_str: str, folder_name: str) -> str:
    """Generate a deterministic pseudo-shortcode for items without an Instagram shortcode."""
    h = hashlib.sha256(folder_name.encode("utf-8")).hexdigest()[:8]
    return f"NOID_{handle}_{date_str}_{h}"


def format_date(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD, or pass through if already formatted."""
    if len(date_str) == 8 and date_str.isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str


def today_str() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")
