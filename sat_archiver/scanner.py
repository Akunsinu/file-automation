"""Directory walker that discovers Instagram content items."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import (
    ARCHIVE_ROOT,
    COMMENT_FOLDER_RE,
    NAMED_STORY_FOLDER_RE,
    POST_FOLDER_RE,
    PROFILE_FOLDER_RE,
    SAT_CHECKS_SUBDIR,
    STORIES_TXT_FOLDER_RE,
    STORY_FILE_RE,
)
from .models import ContentItem
from .parsers import (
    format_date,
    generate_pseudo_shortcode,
    parse_metadata_json,
    parse_named_story_folder,
    parse_path_context,
    parse_post_folder,
    parse_profile_folder,
    parse_comment_folder,
    parse_story_filename,
    today_str,
)


def scan_folder(source_dir: Path) -> list[ContentItem]:
    """Scan a SAT Daily folder and return all discovered content items."""
    sat_checks = source_dir / SAT_CHECKS_SUBDIR
    if not sat_checks.is_dir():
        print(f"Error: {sat_checks} not found.")
        return []

    items: list[ContentItem] = []
    # Collect story files grouped by shortcode for Type A
    story_groups: dict[str, dict] = defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "path_context": {},
        "parent_dir": None,
    })

    _walk_tree(sat_checks, sat_checks, items, story_groups)

    # Convert story groups into ContentItems
    for shortcode, group in story_groups.items():
        dest = ARCHIVE_ROOT / group["username"] / f"{group['username']}_story_{shortcode}"
        item = ContentItem(
            shortcode=shortcode,
            username=group["username"],
            full_name=group["full_name"],
            content_type="Story",
            category=group["path_context"].get("category", ""),
            wpas_code=group["path_context"].get("wpas_code", ""),
            date_posted=format_date(group["date_str"]),
            media_type=group["media_type"],
            post_url="",
            batch=group["path_context"].get("batch", ""),
            section=group["path_context"].get("section", ""),
            archive_date=today_str(),
            destination_path=str(dest),
            source_path=group["parent_dir"],
            source_files=group["files"],
            is_folder_item=False,
        )
        items.append(item)

    return items


def _walk_tree(
    current: Path,
    sat_checks_root: Path,
    items: list[ContentItem],
    story_groups: dict[str, dict],
) -> None:
    """Recursively walk the directory tree, detecting content items."""
    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        return

    dirs: list[Path] = []
    files: list[Path] = []
    for entry in entries:
        if entry.name.startswith("."):
            continue
        if entry.is_dir():
            dirs.append(entry)
        elif entry.is_file():
            files.append(entry)

    # ── Check directories for content folder patterns ────────────────────
    for d in dirs:
        name = d.name
        rel_parts = d.relative_to(sat_checks_root).parts

        # Type B: Post folder
        if POST_FOLDER_RE.match(name):
            item = _handle_post_folder(d, rel_parts, sat_checks_root)
            if item:
                items.append(item)
            continue  # don't recurse

        # Type D: Profile folder
        if PROFILE_FOLDER_RE.match(name):
            item = _handle_profile_folder(d, rel_parts, sat_checks_root)
            if item:
                items.append(item)
            continue

        # Type D: Comment thread folder
        if COMMENT_FOLDER_RE.match(name):
            item = _handle_comment_thread_folder(d, rel_parts, sat_checks_root)
            if item:
                items.append(item)
            continue

        # Type E: Named story folder or IG Stories TXT
        if NAMED_STORY_FOLDER_RE.match(name) or STORIES_TXT_FOLDER_RE.match(name):
            # Edge case: check if contents are Type A story files
            if _folder_contains_story_files(d):
                # Process contained files as Type A stories
                _collect_story_files_from_dir(d, sat_checks_root, story_groups)
            else:
                item = _handle_named_story_folder(d, rel_parts, sat_checks_root)
                if item:
                    items.append(item)
            continue

        # Not a content folder -> recurse
        _walk_tree(d, sat_checks_root, items, story_groups)

    # ── Check files for Type A story pattern ─────────────────────────────
    for f in files:
        parsed = parse_story_filename(f.name)
        if parsed:
            _add_to_story_group(f, parsed, sat_checks_root, story_groups)


def _folder_contains_story_files(folder: Path) -> bool:
    """Check if a folder's direct children include Type A story files."""
    try:
        for entry in folder.iterdir():
            if entry.is_file() and STORY_FILE_RE.match(entry.name):
                return True
    except PermissionError:
        pass
    return False


def _collect_story_files_from_dir(
    folder: Path,
    sat_checks_root: Path,
    story_groups: dict[str, dict],
) -> None:
    """Collect Type A story files from a folder (e.g., an IG Stories TXT folder)."""
    try:
        for entry in sorted(folder.iterdir()):
            if entry.is_file():
                parsed = parse_story_filename(entry.name)
                if parsed:
                    _add_to_story_group(entry, parsed, sat_checks_root, story_groups)
    except PermissionError:
        pass


def _add_to_story_group(
    file_path: Path,
    parsed: dict,
    sat_checks_root: Path,
    story_groups: dict[str, dict],
) -> None:
    """Add a story file to its shortcode group."""
    shortcode = parsed["shortcode"]
    group = story_groups[shortcode]
    group["files"].append(file_path)
    group["shortcode"] = shortcode
    group["username"] = parsed["username"]
    if parsed["full_name"]:
        group["full_name"] = parsed["full_name"]
    group["date_str"] = parsed["date_str"]
    group["parent_dir"] = file_path.parent

    # Determine media type from the raw file
    if parsed["suffix"] == "raw":
        if parsed["ext"] in ("mp4",):
            group["media_type"] = "Video"
        elif parsed["ext"] in ("jpg", "png"):
            group["media_type"] = "Image"

    # Path context (use the parent directory's position)
    if not group["path_context"]:
        try:
            rel = file_path.parent.relative_to(sat_checks_root)
            group["path_context"] = parse_path_context(rel.parts)
        except ValueError:
            group["path_context"] = {}


def _handle_post_folder(
    folder: Path, rel_parts: tuple[str, ...], sat_checks_root: Path
) -> Optional[ContentItem]:
    """Create a ContentItem from a Type B post folder."""
    parsed = parse_post_folder(folder.name)
    if not parsed:
        return None

    ctx = parse_path_context(rel_parts)

    # Look for metadata.json
    metadata = {}
    meta_files = list(folder.rglob("*_metadata.json"))
    has_meta = False
    if meta_files:
        metadata = parse_metadata_json(meta_files[0])
        has_meta = bool(metadata)

    username = metadata.get("username") or parsed["username"]
    shortcode = metadata.get("shortcode") or parsed["shortcode"]
    date_str = metadata.get("posted_at", "")
    if date_str:
        # Extract date part from ISO timestamp
        date_str = date_str[:10]
    else:
        date_str = format_date(parsed["date_str"])

    dest = ARCHIVE_ROOT / username / folder.name

    # Collect all files in the folder
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        shortcode=shortcode,
        username=username,
        full_name=metadata.get("full_name", ""),
        content_type="Post",
        category=ctx.get("category", ""),
        wpas_code=ctx.get("wpas_code", ""),
        date_posted=date_str,
        media_type=metadata.get("media_type", ""),
        like_count=metadata.get("like_count", 0),
        comment_count=metadata.get("comment_count", 0),
        caption=metadata.get("caption", ""),
        post_url=metadata.get("post_url", ""),
        batch=ctx.get("batch", ""),
        section=ctx.get("section", ""),
        archive_date=today_str(),
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        has_metadata_json=has_meta,
    )


def _handle_profile_folder(
    folder: Path, rel_parts: tuple[str, ...], sat_checks_root: Path
) -> Optional[ContentItem]:
    """Create a ContentItem from a Type D profile folder."""
    parsed = parse_profile_folder(folder.name)
    if not parsed:
        return None

    ctx = parse_path_context(rel_parts)
    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        shortcode=pseudo,
        username=handle,
        full_name=parsed["full_name"],
        content_type="Profile",
        category=ctx.get("category", ""),
        wpas_code=ctx.get("wpas_code", ""),
        date_posted=date_str,
        media_type="Mixed",
        batch=ctx.get("batch", ""),
        section=ctx.get("section", ""),
        archive_date=today_str(),
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
    )


def _handle_comment_thread_folder(
    folder: Path, rel_parts: tuple[str, ...], sat_checks_root: Path
) -> Optional[ContentItem]:
    """Create a ContentItem from a Type D comment thread folder."""
    parsed = parse_comment_folder(folder.name)
    if not parsed:
        return None

    ctx = parse_path_context(rel_parts)
    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        shortcode=pseudo,
        username=handle,
        full_name="",
        content_type="Comment Thread",
        category=ctx.get("category", ""),
        wpas_code=ctx.get("wpas_code", ""),
        date_posted=date_str,
        media_type="Mixed",
        batch=ctx.get("batch", ""),
        section=ctx.get("section", ""),
        archive_date=today_str(),
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
    )


def _handle_named_story_folder(
    folder: Path, rel_parts: tuple[str, ...], sat_checks_root: Path
) -> Optional[ContentItem]:
    """Create a ContentItem from a Type E named story folder."""
    parsed = parse_named_story_folder(folder.name)
    if not parsed:
        return None

    ctx = parse_path_context(rel_parts)
    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        shortcode=pseudo,
        username=handle,
        full_name=parsed.get("full_name", ""),
        content_type="Story Collection",
        category=ctx.get("category", ""),
        wpas_code=ctx.get("wpas_code", ""),
        date_posted=date_str,
        media_type="Mixed",
        batch=ctx.get("batch", ""),
        section=ctx.get("section", ""),
        archive_date=today_str(),
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
    )
