"""Directory walker that discovers Instagram content items."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import (
    ARCHIVE_ROOT,
    COMMENT_FOLDER_RE,
    FolderType,
    MO_PATH_TO_COLUMN,
    NAMED_STORY_FOLDER_RE,
    POST_FOLDER_RE,
    PROFILE_FOLDER_RE,
    RESHARE_FOLDER_RE,
    SAT_CHECKS_RE,
    STORIES_TXT_FOLDER_RE,
    STORY_CATEGORY_TO_COLUMN,
    STORY_FILE_RE,
)
from .models import ContentItem
from .parsers import (
    extract_collaborators,
    format_date,
    generate_pseudo_shortcode,
    parse_daily_mo_context,
    parse_metadata_json,
    parse_named_story_folder,
    parse_post_folder,
    parse_profile_file,
    parse_profile_folder,
    parse_comment_folder,
    parse_reshare_folder,
    parse_sat_daily_mo_context,
    parse_sat_daily_stories_context,
    parse_story_filename,
    parse_ve_file,
    today_str,
)


# ── Public API ────────────────────────────────────────────────────────────────

def detect_folder_type(source_dir: Path) -> tuple[FolderType, str]:
    """Detect whether source_dir is SAT Daily or Daily MO.

    Returns (folder_type, downloader_initials).
    For SAT Daily, initials come from "SAT Checks - {initials} - RTA" subdir.
    For Daily MO, initials are empty (set later by GUI/CLI).
    """
    name = source_dir.name
    if name.startswith("SAT Daily on "):
        # Find SAT Checks subdir
        try:
            for entry in source_dir.iterdir():
                if entry.is_dir():
                    m = SAT_CHECKS_RE.match(entry.name)
                    if m:
                        return FolderType.SAT_DAILY, m.group(1)
        except PermissionError:
            pass
        return FolderType.SAT_DAILY, ""

    if name.startswith("Daily MO on "):
        return FolderType.DAILY_MO, ""

    return FolderType.UNKNOWN, ""


def scan_folder(source_dir: Path) -> list[ContentItem]:
    """Scan a source folder and return all discovered content items.

    Dispatches to SAT Daily or Daily MO scanner based on folder type.
    """
    folder_type, initials = detect_folder_type(source_dir)

    if folder_type == FolderType.SAT_DAILY:
        return _scan_sat_daily(source_dir, initials)
    elif folder_type == FolderType.DAILY_MO:
        return _scan_daily_mo(source_dir)
    else:
        print(f"Error: Unrecognized folder type for {source_dir}")
        return []


# ── SAT Daily Scanner ─────────────────────────────────────────────────────────

def _scan_sat_daily(source_dir: Path, downloader: str) -> list[ContentItem]:
    """Scan a SAT Daily folder (Stories, P&V, Additional/MO sections)."""
    # Find SAT Checks subdir
    sat_checks = None
    try:
        for entry in source_dir.iterdir():
            if entry.is_dir() and SAT_CHECKS_RE.match(entry.name):
                sat_checks = entry
                break
    except PermissionError:
        pass

    if not sat_checks:
        print(f"Error: No 'SAT Checks - * - RTA' directory found in {source_dir}")
        return []

    items: list[ContentItem] = []
    archive_date = today_str()

    # ── Stories section ───────────────────────────────────────────────────
    stories_dir = sat_checks / "Stories"
    if stories_dir.is_dir():
        items.extend(_scan_sat_daily_stories(stories_dir, downloader, archive_date))

    # ── P&V section ───────────────────────────────────────────────────────
    pv_dir = sat_checks / "P&V"
    if pv_dir.is_dir():
        items.extend(_scan_sat_daily_pv(pv_dir, downloader, archive_date))

    # ── Additional/MO section ─────────────────────────────────────────────
    mo_dir = sat_checks / "Additional" / "MO"
    if mo_dir.is_dir():
        items.extend(_scan_sat_daily_mo(mo_dir, downloader, archive_date))

    return items


def _scan_sat_daily_stories(stories_dir: Path, downloader: str, archive_date: str) -> list[ContentItem]:
    """Scan Stories/ section: Batch/Category/WPAS hierarchy."""
    items: list[ContentItem] = []
    story_groups: dict[str, dict] = defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "ctx": {},
        "parent_dir": None,
    })

    _walk_stories_tree(stories_dir, stories_dir, items, story_groups, downloader, archive_date)

    # Convert story groups into ContentItems
    for shortcode, group in story_groups.items():
        dest = ARCHIVE_ROOT / group["username"] / f"{group['username']}_story_{shortcode}"
        ctx = group["ctx"]
        item = ContentItem(
            timestamp=archive_date,
            shortcode=shortcode,
            real_name=group["full_name"],
            username=group["username"],
            post_type="Story",
            downloader=downloader,
            post_date=format_date(group["date_str"]),
            db_link=str(group["files"][0]) if group["files"] else "",
            batch=ctx.get("batch", ""),
            wpas_code=ctx.get("wpas_code", ""),
            destination_path=str(dest),
            source_path=group["parent_dir"],
            source_files=group["files"],
            is_folder_item=False,
            folder_type="sat_daily",
            content_section="stories",
        )
        # Set dropdown column value from context
        col = ctx.get("dropdown_column", "")
        val = ctx.get("dropdown_value", "")
        if col and val:
            if hasattr(item, col):
                setattr(item, col, val)
        items.append(item)

    return items


def _walk_stories_tree(
    current: Path,
    stories_root: Path,
    items: list[ContentItem],
    story_groups: dict[str, dict],
    downloader: str,
    archive_date: str,
) -> None:
    """Walk Stories/ tree, detecting content items at each level."""
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

    # Check directories for content folder patterns
    for d in dirs:
        name = d.name

        # Type B: Post folder
        if POST_FOLDER_RE.match(name):
            item = _build_post_item(d, downloader, archive_date, "sat_daily", "stories")
            if item:
                # Set batch and dropdown from stories context
                try:
                    rel = d.parent.relative_to(stories_root)
                    ctx = parse_sat_daily_stories_context(rel.parts)
                    item.batch = ctx.get("batch", "")
                    col = ctx.get("dropdown_column", "")
                    val = ctx.get("dropdown_value", "")
                    if col and val and hasattr(item, col):
                        setattr(item, col, val)
                except ValueError:
                    pass
                items.append(item)
            continue

        # Type D: Profile folder
        if PROFILE_FOLDER_RE.match(name):
            item = _build_profile_item(d, downloader, archive_date, "sat_daily", "stories")
            if item:
                items.append(item)
            continue

        # Type D: Comment thread folder
        if COMMENT_FOLDER_RE.match(name):
            item = _build_comment_thread_item(d, downloader, archive_date, "sat_daily", "stories")
            if item:
                items.append(item)
            continue

        # Type E: Named story folder or IG Stories TXT
        if NAMED_STORY_FOLDER_RE.match(name) or STORIES_TXT_FOLDER_RE.match(name):
            if _folder_contains_story_files(d):
                _collect_story_files_from_dir(d, stories_root, story_groups)
            else:
                item = _build_named_story_item(d, downloader, archive_date, "sat_daily", "stories")
                if item:
                    # Set context from path
                    try:
                        rel = d.parent.relative_to(stories_root)
                        ctx = parse_sat_daily_stories_context(rel.parts)
                        item.batch = ctx.get("batch", "")
                        col = ctx.get("dropdown_column", "")
                        val = ctx.get("dropdown_value", "")
                        if col and val and hasattr(item, col):
                            setattr(item, col, val)
                    except ValueError:
                        pass
                    items.append(item)
            continue

        # Not a content folder -> recurse
        _walk_stories_tree(d, stories_root, items, story_groups, downloader, archive_date)

    # Check files for Type A story pattern
    for f in files:
        parsed = parse_story_filename(f.name)
        if parsed:
            _add_to_story_group(f, parsed, stories_root, story_groups)


def _scan_sat_daily_pv(pv_dir: Path, downloader: str, archive_date: str) -> list[ContentItem]:
    """Scan P&V/ section: {username}/{post_folder}/..."""
    items: list[ContentItem] = []

    try:
        for username_dir in sorted(pv_dir.iterdir()):
            if not username_dir.is_dir() or username_dir.name.startswith("."):
                continue
            for post_dir in sorted(username_dir.iterdir()):
                if not post_dir.is_dir() or post_dir.name.startswith("."):
                    continue
                if POST_FOLDER_RE.match(post_dir.name):
                    item = _build_post_item(post_dir, downloader, archive_date, "sat_daily", "pv")
                    if item:
                        items.append(item)
    except PermissionError:
        pass

    return items


def _scan_sat_daily_mo(mo_dir: Path, downloader: str, archive_date: str) -> list[ContentItem]:
    """Scan Additional/MO/ section: {type}/{category}/..."""
    items: list[ContentItem] = []
    story_groups: dict[str, dict] = defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "ctx": {},
        "parent_dir": None,
    })

    try:
        for type_dir in sorted(mo_dir.iterdir()):
            if not type_dir.is_dir() or type_dir.name.startswith("."):
                continue
            mo_type = type_dir.name  # PW, RPT, SI, TS, WTS
            mo_column = MO_PATH_TO_COLUMN.get(mo_type, "")

            for category_dir in sorted(type_dir.iterdir()):
                if not category_dir.is_dir() or category_dir.name.startswith("."):
                    continue
                mo_value = category_dir.name  # "History - Lifestyle", etc.

                # Scan for story files and post folders in this category
                _scan_mo_category(
                    category_dir, mo_column, mo_value,
                    items, story_groups, mo_dir,
                    downloader, archive_date, "sat_daily", "mo",
                )
    except PermissionError:
        pass

    # Convert story groups
    for shortcode, group in story_groups.items():
        dest = ARCHIVE_ROOT / group["username"] / f"{group['username']}_story_{shortcode}"
        ctx = group["ctx"]
        item = ContentItem(
            timestamp=archive_date,
            shortcode=shortcode,
            real_name=group["full_name"],
            username=group["username"],
            post_type="Story",
            downloader=downloader,
            post_date=format_date(group["date_str"]),
            db_link=str(group["files"][0]) if group["files"] else "",
            destination_path=str(dest),
            source_path=group["parent_dir"],
            source_files=group["files"],
            is_folder_item=False,
            folder_type="sat_daily",
            content_section="mo",
        )
        mo_col = ctx.get("mo_column", "")
        mo_val = ctx.get("mo_value", "")
        if mo_col and mo_val and hasattr(item, mo_col):
            setattr(item, mo_col, mo_val)
        items.append(item)

    return items


def _scan_mo_category(
    category_dir: Path,
    mo_column: str,
    mo_value: str,
    items: list[ContentItem],
    story_groups: dict[str, dict],
    root_dir: Path,
    downloader: str,
    archive_date: str,
    folder_type: str,
    content_section: str,
) -> None:
    """Scan a single MO category directory for stories and posts."""
    try:
        entries = sorted(category_dir.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            if POST_FOLDER_RE.match(entry.name):
                item = _build_post_item(entry, downloader, archive_date, folder_type, content_section)
                if item and mo_column and hasattr(item, mo_column):
                    setattr(item, mo_column, mo_value)
                if item:
                    items.append(item)
            elif NAMED_STORY_FOLDER_RE.match(entry.name) or STORIES_TXT_FOLDER_RE.match(entry.name):
                if _folder_contains_story_files(entry):
                    _collect_story_files_from_dir(entry, root_dir, story_groups, mo_column=mo_column, mo_value=mo_value)
                else:
                    item = _build_named_story_item(entry, downloader, archive_date, folder_type, content_section)
                    if item and mo_column and hasattr(item, mo_column):
                        setattr(item, mo_column, mo_value)
                    if item:
                        items.append(item)
            elif PROFILE_FOLDER_RE.match(entry.name):
                item = _build_profile_item(entry, downloader, archive_date, folder_type, content_section)
                if item and mo_column and hasattr(item, mo_column):
                    setattr(item, mo_column, mo_value)
                if item:
                    items.append(item)
        elif entry.is_file():
            parsed = parse_story_filename(entry.name)
            if parsed:
                _add_to_story_group(entry, parsed, root_dir, story_groups, mo_column=mo_column, mo_value=mo_value)


# ── Daily MO Scanner ──────────────────────────────────────────────────────────

def _scan_daily_mo(source_dir: Path) -> list[ContentItem]:
    """Scan a Daily MO folder (Categories, Reshares, Manual, Profile, VE)."""
    items: list[ContentItem] = []
    archive_date = today_str()

    # ── Categories ────────────────────────────────────────────────────────
    categories_dir = source_dir / "Categories"
    if categories_dir.is_dir():
        items.extend(_scan_daily_mo_categories(categories_dir, archive_date))

    # ── Reshares ──────────────────────────────────────────────────────────
    reshares_dir = source_dir / "Reshares"
    if reshares_dir.is_dir():
        items.extend(_scan_daily_mo_reshares(reshares_dir, archive_date))

    # ── Manual ────────────────────────────────────────────────────────────
    manual_dir = source_dir / "Manual"
    if manual_dir.is_dir():
        items.extend(_scan_daily_mo_manual(manual_dir, archive_date))

    # ── Profile ───────────────────────────────────────────────────────────
    profile_dir = source_dir / "Profile"
    if profile_dir.is_dir():
        items.extend(_scan_daily_mo_profile(profile_dir, archive_date))

    # ── VE ────────────────────────────────────────────────────────────────
    ve_dir = source_dir / "VE"
    if ve_dir.is_dir():
        items.extend(_scan_daily_mo_ve(ve_dir, archive_date))

    return items


def _scan_daily_mo_categories(categories_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Categories/ — each subfolder name becomes mo_pw value."""
    items: list[ContentItem] = []
    story_groups: dict[str, dict] = defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "ctx": {},
        "parent_dir": None,
    })

    try:
        for cat_dir in sorted(categories_dir.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.startswith("."):
                continue
            category_name = cat_dir.name  # "History - Character", etc.

            _scan_mo_category(
                cat_dir, "mo_pw", category_name,
                items, story_groups, categories_dir,
                "", archive_date, "daily_mo", "categories",
            )
    except PermissionError:
        pass

    # Convert story groups
    for shortcode, group in story_groups.items():
        dest = ARCHIVE_ROOT / group["username"] / f"{group['username']}_story_{shortcode}"
        ctx = group["ctx"]
        item = ContentItem(
            timestamp=archive_date,
            shortcode=shortcode,
            real_name=group["full_name"],
            username=group["username"],
            post_type="Story",
            post_date=format_date(group["date_str"]),
            db_link=str(group["files"][0]) if group["files"] else "",
            destination_path=str(dest),
            source_path=group["parent_dir"],
            source_files=group["files"],
            is_folder_item=False,
            folder_type="daily_mo",
            content_section="categories",
        )
        mo_col = ctx.get("mo_column", "")
        mo_val = ctx.get("mo_value", "")
        if mo_col and mo_val and hasattr(item, mo_col):
            setattr(item, mo_col, mo_val)
        items.append(item)

    return items


def _scan_daily_mo_reshares(reshares_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Reshares/ — IG Reshare folders with category/username/post structure."""
    items: list[ContentItem] = []
    story_groups: dict[str, dict] = defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "ctx": {},
        "parent_dir": None,
    })

    try:
        for reshare_dir in sorted(reshares_dir.iterdir()):
            if not reshare_dir.is_dir() or reshare_dir.name.startswith("."):
                continue

            reshare_info = parse_reshare_folder(reshare_dir.name)
            resharer_username = reshare_info["handle"] if reshare_info else ""
            resharer_name = reshare_info["full_name"] if reshare_info else ""

            # Walk category dirs inside reshare folder
            for cat_dir in sorted(reshare_dir.iterdir()):
                if not cat_dir.is_dir() or cat_dir.name.startswith("."):
                    continue
                category_name = cat_dir.name

                # Category might contain username dirs with posts, or direct posts
                _scan_reshare_category(
                    cat_dir, category_name,
                    resharer_username, resharer_name,
                    items, story_groups, reshares_dir,
                    archive_date,
                )
    except PermissionError:
        pass

    # Convert story groups
    for shortcode, group in story_groups.items():
        dest = ARCHIVE_ROOT / group["username"] / f"{group['username']}_story_{shortcode}"
        ctx = group["ctx"]
        item = ContentItem(
            timestamp=archive_date,
            shortcode=shortcode,
            real_name=group["full_name"],
            username=group["username"],
            post_type="Story",
            post_date=format_date(group["date_str"]),
            db_link=str(group["files"][0]) if group["files"] else "",
            sheet_categories="Reshare",
            resharer_username=ctx.get("resharer_username", ""),
            resharer_name=ctx.get("resharer_name", ""),
            destination_path=str(dest),
            source_path=group["parent_dir"],
            source_files=group["files"],
            is_folder_item=False,
            folder_type="daily_mo",
            content_section="reshares",
        )
        mo_col = ctx.get("mo_column", "")
        mo_val = ctx.get("mo_value", "")
        if mo_col and mo_val and hasattr(item, mo_col):
            setattr(item, mo_col, mo_val)
        items.append(item)

    return items


def _scan_reshare_category(
    cat_dir: Path,
    category_name: str,
    resharer_username: str,
    resharer_name: str,
    items: list[ContentItem],
    story_groups: dict[str, dict],
    root_dir: Path,
    archive_date: str,
) -> None:
    """Scan a category inside a reshare folder: may contain username dirs or direct posts."""
    try:
        entries = sorted(cat_dir.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.name.startswith("."):
            continue

        if entry.is_dir():
            if POST_FOLDER_RE.match(entry.name):
                # Direct post in category
                item = _build_post_item(entry, "", archive_date, "daily_mo", "reshares")
                if item:
                    item.sheet_categories = "Reshare"
                    item.mo_pw = category_name
                    item.resharer_username = resharer_username
                    item.resharer_name = resharer_name
                    items.append(item)
            else:
                # Username directory containing posts
                _scan_reshare_username_dir(
                    entry, category_name,
                    resharer_username, resharer_name,
                    items, story_groups, root_dir,
                    archive_date,
                )
        elif entry.is_file():
            parsed = parse_story_filename(entry.name)
            if parsed:
                _add_to_story_group(
                    entry, parsed, root_dir, story_groups,
                    mo_column="mo_pw", mo_value=category_name,
                    resharer_username=resharer_username,
                    resharer_name=resharer_name,
                )


def _scan_reshare_username_dir(
    username_dir: Path,
    category_name: str,
    resharer_username: str,
    resharer_name: str,
    items: list[ContentItem],
    story_groups: dict[str, dict],
    root_dir: Path,
    archive_date: str,
) -> None:
    """Scan a username directory inside a reshare category."""
    try:
        for entry in sorted(username_dir.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir() and POST_FOLDER_RE.match(entry.name):
                item = _build_post_item(entry, "", archive_date, "daily_mo", "reshares")
                if item:
                    item.sheet_categories = "Reshare"
                    item.mo_pw = category_name
                    item.resharer_username = resharer_username
                    item.resharer_name = resharer_name
                    items.append(item)
            elif entry.is_file():
                parsed = parse_story_filename(entry.name)
                if parsed:
                    _add_to_story_group(
                        entry, parsed, root_dir, story_groups,
                        mo_column="mo_pw", mo_value=category_name,
                        resharer_username=resharer_username,
                        resharer_name=resharer_name,
                    )
    except PermissionError:
        pass


def _scan_daily_mo_manual(manual_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Manual/ — IG Stories and IG Reshare folder patterns."""
    items: list[ContentItem] = []

    try:
        for entry in sorted(manual_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            # IG Stories folder
            if NAMED_STORY_FOLDER_RE.match(entry.name) or STORIES_TXT_FOLDER_RE.match(entry.name):
                item = _build_named_story_item(entry, "", archive_date, "daily_mo", "manual")
                if item:
                    items.append(item)
                continue

            # IG Reshare folder
            if RESHARE_FOLDER_RE.match(entry.name):
                reshare_info = parse_reshare_folder(entry.name)
                if reshare_info:
                    item = _build_named_story_item(entry, "", archive_date, "daily_mo", "manual")
                    if item:
                        item.resharer_username = reshare_info["handle"]
                        item.resharer_name = reshare_info["full_name"]
                        item.sheet_categories = "Reshare"
                        items.append(item)
                continue

    except PermissionError:
        pass

    return items


def _scan_daily_mo_profile(profile_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Profile/ — individual profile screenshot files."""
    items: list[ContentItem] = []

    try:
        for entry in sorted(profile_dir.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            parsed = parse_profile_file(entry.name)
            if parsed:
                username = parsed["username"]
                date_str = format_date(parsed["date_str"])
                pseudo = generate_pseudo_shortcode(username, date_str, entry.name)
                dest = ARCHIVE_ROOT / username / entry.name

                items.append(ContentItem(
                    timestamp=archive_date,
                    shortcode=pseudo,
                    username=username,
                    post_type="Profile",
                    post_date=date_str,
                    db_link=str(entry),
                    destination_path=str(dest),
                    source_path=entry,
                    source_files=[entry],
                    is_folder_item=False,
                    folder_type="daily_mo",
                    content_section="profile",
                ))
    except PermissionError:
        pass

    return items


def _scan_daily_mo_ve(ve_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan VE/ — video evidence files."""
    items: list[ContentItem] = []

    try:
        for entry in sorted(ve_dir.iterdir()):
            if not entry.is_file() or entry.name.startswith("."):
                continue
            parsed = parse_ve_file(entry.name)
            if parsed:
                handle = parsed["handle"]
                full_name = parsed["full_name"]
                date_str = parsed["date_str"]
                pseudo = generate_pseudo_shortcode(handle, date_str, entry.name)
                dest = ARCHIVE_ROOT / handle / entry.name

                items.append(ContentItem(
                    timestamp=archive_date,
                    shortcode=pseudo,
                    real_name=full_name,
                    username=handle,
                    post_type="VE",
                    post_date=date_str,
                    db_link=str(entry),
                    destination_path=str(dest),
                    source_path=entry,
                    source_files=[entry],
                    is_folder_item=False,
                    folder_type="daily_mo",
                    content_section="ve",
                ))
    except PermissionError:
        pass

    return items


# ── Shared item builders ──────────────────────────────────────────────────────

def _build_post_item(
    folder: Path,
    downloader: str,
    archive_date: str,
    folder_type: str,
    content_section: str,
) -> Optional[ContentItem]:
    """Create a ContentItem from a post folder (Type B)."""
    parsed = parse_post_folder(folder.name)
    if not parsed:
        return None

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
        date_str = date_str[:10]
    else:
        date_str = format_date(parsed["date_str"])

    collabs = extract_collaborators(folder.name, metadata)

    # Find primary media file for db_link
    db_link = ""
    media_dir = folder / "media"
    if media_dir.is_dir():
        media_files = sorted(f for f in media_dir.iterdir() if f.is_file() and not f.name.startswith("."))
        if media_files:
            db_link = str(media_files[0])

    dest = ARCHIVE_ROOT / username / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    # Determine if paired from folder name
    paired = " - PAIRED" in folder.name

    return ContentItem(
        timestamp=archive_date,
        shortcode=shortcode,
        real_name=metadata.get("full_name", ""),
        username=username,
        post_type="Post",
        downloader=downloader,
        post_date=date_str,
        collaborators=collabs,
        db_link=db_link,
        paired_content="Yes" if paired else "",
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        has_metadata_json=has_meta,
        folder_type=folder_type,
        content_section=content_section,
    )


def _build_profile_item(
    folder: Path,
    downloader: str,
    archive_date: str,
    folder_type: str,
    content_section: str,
) -> Optional[ContentItem]:
    """Create a ContentItem from a profile folder (Type D)."""
    parsed = parse_profile_folder(folder.name)
    if not parsed:
        return None

    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        timestamp=archive_date,
        shortcode=pseudo,
        real_name=parsed["full_name"],
        username=handle,
        post_type="Profile",
        downloader=downloader,
        post_date=date_str,
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        folder_type=folder_type,
        content_section=content_section,
    )


def _build_comment_thread_item(
    folder: Path,
    downloader: str,
    archive_date: str,
    folder_type: str,
    content_section: str,
) -> Optional[ContentItem]:
    """Create a ContentItem from a comment thread folder (Type D)."""
    parsed = parse_comment_folder(folder.name)
    if not parsed:
        return None

    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    paired = " - PAIRED" in folder.name

    return ContentItem(
        timestamp=archive_date,
        shortcode=pseudo,
        username=handle,
        post_type="Comment Thread",
        downloader=downloader,
        post_date=date_str,
        paired_content="Yes" if paired else "",
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        folder_type=folder_type,
        content_section=content_section,
    )


def _build_named_story_item(
    folder: Path,
    downloader: str,
    archive_date: str,
    folder_type: str,
    content_section: str,
) -> Optional[ContentItem]:
    """Create a ContentItem from a named story folder (Type E)."""
    parsed = parse_named_story_folder(folder.name)
    if not parsed:
        return None

    handle = parsed["handle"]
    date_str = parsed["date_str"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = ARCHIVE_ROOT / handle / folder.name
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        timestamp=archive_date,
        shortcode=pseudo,
        real_name=parsed.get("full_name", ""),
        username=handle,
        post_type="Story Collection",
        downloader=downloader,
        post_date=date_str,
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        folder_type=folder_type,
        content_section=content_section,
    )


# ── Story file helpers ────────────────────────────────────────────────────────

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
    root_dir: Path,
    story_groups: dict[str, dict],
    mo_column: str = "",
    mo_value: str = "",
) -> None:
    """Collect Type A story files from a folder."""
    try:
        for entry in sorted(folder.iterdir()):
            if entry.is_file():
                parsed = parse_story_filename(entry.name)
                if parsed:
                    _add_to_story_group(entry, parsed, root_dir, story_groups, mo_column=mo_column, mo_value=mo_value)
    except PermissionError:
        pass


def _add_to_story_group(
    file_path: Path,
    parsed: dict,
    root_dir: Path,
    story_groups: dict[str, dict],
    mo_column: str = "",
    mo_value: str = "",
    resharer_username: str = "",
    resharer_name: str = "",
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
        elif parsed["ext"] in ("jpg", "jpeg", "png"):
            group["media_type"] = "Image"

    # Path context
    if not group["ctx"]:
        try:
            rel = file_path.parent.relative_to(root_dir)
            group["ctx"] = parse_sat_daily_stories_context(rel.parts)
        except ValueError:
            group["ctx"] = {}

    # MO context (overrides if provided)
    if mo_column:
        group["ctx"]["mo_column"] = mo_column
        group["ctx"]["mo_value"] = mo_value

    # Resharer context
    if resharer_username:
        group["ctx"]["resharer_username"] = resharer_username
        group["ctx"]["resharer_name"] = resharer_name
