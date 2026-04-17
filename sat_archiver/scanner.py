"""Directory walker that discovers Instagram content items."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import (
    ARCHIVE_ROOT,
    COMMENT_FOLDER_RE,
    DATA_COLLECT_RE,
    FolderType,
    MO_PATH_TO_COLUMN,
    NAMED_STORY_FOLDER_RE,
    POST_FOLDER_RE,
    PROFILE_FOLDER_RE,
    RESHARE_FOLDER_RE,
    RS_CSV_RE,
    SAT_CHECKS_RE,
    STORIES_TXT_FOLDER_RE,
    STORY_CATEGORY_TO_COLUMN,
    STORY_FILE_RE,
)
from .models import ContentItem
from .mover import resolve_user_dir
from .parsers import (
    extract_collaborators,
    format_date,
    generate_pseudo_shortcode,
    parse_daily_mo_context,
    parse_data_collect_categories_context,
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


# ── Story group accumulator ──────────────────────────────────────────────────
# All story-scanning code paths share the same two-phase pattern: (1) collect
# story files into a dict keyed by shortcode, accumulating the 3 suffix variants
# plus username/real_name/date/context per group; (2) turn each group into a
# single ContentItem. This class consolidates phase 2.

def _new_story_groups() -> dict[str, dict]:
    """Factory for the story-group defaultdict used throughout the scanner."""
    return defaultdict(lambda: {
        "files": [],
        "username": "",
        "full_name": "",
        "shortcode": "",
        "date_str": "",
        "media_type": "",
        "ctx": {},
        "parent_dir": None,
    })


class StoryGroupAccumulator:
    """Groups story files by shortcode and emits ContentItems.

    Expose ``.groups`` to the existing walker helpers (they take a raw dict by
    argument). Call ``.to_items()`` after the walk to get the list of story
    ContentItems ready for moving/logging.
    """

    def __init__(
        self,
        downloader: str,
        archive_date: str,
        folder_type: str,
        content_section: str,
        include_batch_wpas: bool = True,
    ):
        self._downloader = downloader
        self._archive_date = archive_date
        self._folder_type = folder_type
        self._content_section = content_section
        # MO-style paths ({type}/{category}/) produce garbage batch/wpas values
        # when run through parse_sat_daily_stories_context (e.g. batch="PW").
        # MO callers opt out.
        self._include_batch_wpas = include_batch_wpas
        self.groups: dict[str, dict] = _new_story_groups()

    def to_items(self, notes_fn=None) -> list[ContentItem]:
        """Convert accumulated groups into ContentItems.

        ``notes_fn``: optional callable(group) -> str used to stamp
        manual_notes (for items pulled out of free-form Other/ buckets).
        """
        items: list[ContentItem] = []
        for shortcode, group in self.groups.items():
            dest = resolve_user_dir(group["username"], group["full_name"]) / "Stories"
            ctx = group["ctx"]
            item = ContentItem(
                timestamp=self._archive_date,
                shortcode=shortcode,
                real_name=group["full_name"],
                username=group["username"],
                post_type="Story",
                downloader=self._downloader,
                post_date=format_date(group["date_str"]),
                db_link=str(group["files"][0]) if group["files"] else "",
                batch=ctx.get("batch", "") if self._include_batch_wpas else "",
                wpas_code=ctx.get("wpas_code", "") if self._include_batch_wpas else "",
                manual_notes=notes_fn(group) if notes_fn else "",
                destination_path=str(dest),
                source_path=group["parent_dir"],
                source_files=group["files"],
                is_folder_item=False,
                folder_type=self._folder_type,
                content_section=self._content_section,
            )
            col = ctx.get("dropdown_column", "")
            val = ctx.get("dropdown_value", "")
            if col and val and hasattr(item, col):
                setattr(item, col, val)
            mo_col = ctx.get("mo_column", "")
            mo_val = ctx.get("mo_value", "")
            if mo_col and mo_val and hasattr(item, mo_col):
                setattr(item, mo_col, mo_val)
            items.append(item)
        return items


# ── Scan-wide diagnostic state ────────────────────────────────────────────────
# Paths the scanner couldn't read due to PermissionError during the most recent
# scan_folder() call. Populated by _note_skipped(); callers can read it via
# get_last_scan_skipped() to surface silent skips to the user.
_skipped_paths: list[Path] = []


def _note_skipped(path: Path) -> None:
    """Record a path that was skipped due to a permission error."""
    _skipped_paths.append(path)


def get_last_scan_skipped() -> list[Path]:
    """Return paths skipped due to PermissionError in the most recent scan."""
    return list(_skipped_paths)


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
            _note_skipped(source_dir)
        return FolderType.SAT_DAILY, ""

    if name.startswith("Daily MO on "):
        return FolderType.DAILY_MO, ""

    if name.startswith("Data Collect"):
        m = DATA_COLLECT_RE.match(name)
        if m:
            return FolderType.DATA_COLLECT, m.group(1)  # initials
        return FolderType.DATA_COLLECT, ""

    return FolderType.UNKNOWN, ""


def scan_folder(source_dir: Path) -> list[ContentItem]:
    """Scan a source folder and return all discovered content items.

    Dispatches to SAT Daily or Daily MO scanner based on folder type.
    """
    _skipped_paths.clear()
    folder_type, initials = detect_folder_type(source_dir)

    if folder_type == FolderType.SAT_DAILY:
        return _scan_sat_daily(source_dir, initials)
    elif folder_type == FolderType.DAILY_MO:
        return _scan_daily_mo(source_dir)
    elif folder_type == FolderType.DATA_COLLECT:
        return _scan_data_collect(source_dir, initials)
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
        _note_skipped(source_dir)

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
    acc = StoryGroupAccumulator(downloader, archive_date, "sat_daily", "stories")
    _walk_stories_tree(stories_dir, stories_dir, items, acc.groups, downloader, archive_date)
    items.extend(acc.to_items())
    return items


def _apply_context(item: ContentItem, parent: Path, root: Path, context_parser) -> None:
    """Apply context (dropdown/MO values) from the path hierarchy to an item."""
    try:
        rel = parent.relative_to(root)
        ctx = context_parser(rel.parts)
        item.batch = ctx.get("batch", "")
        col = ctx.get("dropdown_column", "")
        val = ctx.get("dropdown_value", "")
        if col and val and hasattr(item, col):
            setattr(item, col, val)
        mo_col = ctx.get("mo_column", "")
        mo_val = ctx.get("mo_value", "")
        if mo_col and mo_val and hasattr(item, mo_col):
            setattr(item, mo_col, mo_val)
    except ValueError:
        pass


def _walk_stories_tree(
    current: Path,
    stories_root: Path,
    items: list[ContentItem],
    story_groups: dict[str, dict],
    downloader: str,
    archive_date: str,
    context_parser=None,
    folder_type: str = "sat_daily",
    content_section: str = "stories",
) -> None:
    """Walk Stories/ tree, detecting content items at each level."""
    if context_parser is None:
        context_parser = parse_sat_daily_stories_context
    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        _note_skipped(current)
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
            item = _build_post_item(d, downloader, archive_date, folder_type, content_section)
            if item:
                _apply_context(item, d.parent, stories_root, context_parser)
                items.append(item)
            continue

        # Type D: Profile folder
        if PROFILE_FOLDER_RE.match(name):
            item = _build_profile_item(d, downloader, archive_date, folder_type, content_section)
            if item:
                items.append(item)
            continue

        # Type D: Comment thread folder
        if COMMENT_FOLDER_RE.match(name):
            item = _build_comment_thread_item(d, downloader, archive_date, folder_type, content_section)
            if item:
                items.append(item)
            continue

        # Type E: Named story folder or IG Stories TXT
        if NAMED_STORY_FOLDER_RE.match(name) or STORIES_TXT_FOLDER_RE.match(name):
            if _folder_contains_story_files(d):
                _collect_story_files_from_dir(d, stories_root, story_groups, context_parser=context_parser)
            else:
                item = _build_named_story_item(d, downloader, archive_date, folder_type, content_section)
                if item:
                    _apply_context(item, d.parent, stories_root, context_parser)
                    items.append(item)
            continue

        # Not a content folder -> recurse
        _walk_stories_tree(d, stories_root, items, story_groups, downloader, archive_date,
                           context_parser=context_parser, folder_type=folder_type,
                           content_section=content_section)

    # Check files for Type A story pattern
    for f in files:
        parsed = parse_story_filename(f.name)
        if parsed:
            _add_to_story_group(f, parsed, stories_root, story_groups, context_parser=context_parser)


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
        _note_skipped(pv_dir)

    return items


def _scan_sat_daily_mo(
    mo_dir: Path, downloader: str, archive_date: str,
    folder_type: str = "sat_daily", content_section: str = "mo",
) -> list[ContentItem]:
    """Scan Additional/MO/ section: {type}/{category}/..."""
    items: list[ContentItem] = []
    acc = StoryGroupAccumulator(
        downloader, archive_date, folder_type, content_section,
        include_batch_wpas=False,
    )

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

                _scan_mo_category(
                    category_dir, mo_column, mo_value,
                    items, acc.groups, mo_dir,
                    downloader, archive_date, folder_type, content_section,
                )
    except PermissionError:
        _note_skipped(mo_dir)

    items.extend(acc.to_items())
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
        _note_skipped(category_dir)
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
            else:
                # Unknown dir (e.g. username subdir) — recurse
                _scan_mo_category(
                    entry, mo_column, mo_value,
                    items, story_groups, root_dir,
                    downloader, archive_date, folder_type, content_section,
                )
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
    acc = StoryGroupAccumulator(
        "", archive_date, "daily_mo", "categories", include_batch_wpas=False,
    )

    try:
        for cat_dir in sorted(categories_dir.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.startswith("."):
                continue
            category_name = cat_dir.name  # "History - Character", etc.

            _scan_mo_category(
                cat_dir, "mo_pw", category_name,
                items, acc.groups, categories_dir,
                "", archive_date, "daily_mo", "categories",
            )
    except PermissionError:
        _note_skipped(categories_dir)

    items.extend(acc.to_items())
    return items


def _scan_daily_mo_reshares(reshares_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Reshares/ — IG Reshare folders and RS CSV files."""
    items: list[ContentItem] = []

    try:
        for entry in sorted(reshares_dir.iterdir()):
            if entry.name.startswith("."):
                continue

            # IG Reshare folder → one ContentItem per folder
            if entry.is_dir() and RESHARE_FOLDER_RE.match(entry.name):
                reshare_info = parse_reshare_folder(entry.name)
                if not reshare_info:
                    continue
                handle = reshare_info["handle"]
                full_name = reshare_info["full_name"]
                date_str = reshare_info["date_str"]
                pseudo = generate_pseudo_shortcode(handle, date_str, entry.name)
                dest = resolve_user_dir(handle, full_name) / "Reshares"
                all_files = [f for f in entry.rglob("*") if f.is_file() and not f.name.startswith(".")]
                db_link = str(all_files[0]) if all_files else ""

                items.append(ContentItem(
                    timestamp=archive_date,
                    shortcode=pseudo,
                    real_name=full_name,
                    username=handle,
                    post_type="Reshare",
                    post_date=date_str,
                    db_link=db_link,
                    sheet_categories="Reshare",
                    resharer_username=handle,
                    resharer_name=full_name,
                    destination_path=str(dest),
                    source_path=entry,
                    source_files=all_files,
                    is_folder_item=True,
                    folder_type="daily_mo",
                    content_section="reshares",
                ))
                continue

            # RS CSV files → archive only, no sheet entry
            if entry.is_file() and RS_CSV_RE.match(entry.name):
                pseudo = generate_pseudo_shortcode("rs_csv", archive_date, entry.name)
                # RS CSVs don't have a username; place in a shared location
                dest = ARCHIVE_ROOT / "Reshares"
                items.append(ContentItem(
                    timestamp=archive_date,
                    shortcode=pseudo,
                    post_type="RS CSV",
                    post_date=archive_date,
                    db_link=str(entry),
                    skip_sheet_log=True,
                    destination_path=str(dest),
                    source_path=entry,
                    source_files=[entry],
                    is_folder_item=False,
                    folder_type="daily_mo",
                    content_section="reshares",
                ))
    except PermissionError:
        _note_skipped(reshares_dir)

    return items


def _scan_daily_mo_manual(manual_dir: Path, archive_date: str) -> list[ContentItem]:
    """Scan Manual/ — IG Stories and IG Reshare folder patterns."""
    items: list[ContentItem] = []

    try:
        for entry in sorted(manual_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue

            # IG Stories folder — preserved as folder
            if NAMED_STORY_FOLDER_RE.match(entry.name) or STORIES_TXT_FOLDER_RE.match(entry.name):
                item = _build_named_story_item(entry, "", archive_date, "daily_mo", "manual")
                if item:
                    item.move_as_folder = True
                    items.append(item)
                continue

            # IG Reshare folder — flatten categories, archive to Reshares/
            if RESHARE_FOLDER_RE.match(entry.name):
                reshare_info = parse_reshare_folder(entry.name)
                if reshare_info:
                    handle = reshare_info["handle"]
                    full_name = reshare_info["full_name"]
                    date_str = reshare_info["date_str"]
                    pseudo = generate_pseudo_shortcode(handle, date_str, entry.name)
                    dest = resolve_user_dir(handle, full_name) / "Reshares"
                    all_files = [f for f in entry.rglob("*") if f.is_file() and not f.name.startswith(".")]
                    db_link = str(all_files[0]) if all_files else ""

                    items.append(ContentItem(
                        timestamp=archive_date,
                        shortcode=pseudo,
                        real_name=full_name,
                        username=handle,
                        post_type="Reshare",
                        post_date=date_str,
                        db_link=db_link,
                        sheet_categories="Reshare",
                        resharer_username=handle,
                        resharer_name=full_name,
                        destination_path=str(dest),
                        source_path=entry,
                        source_files=all_files,
                        is_folder_item=True,
                        folder_type="daily_mo",
                        content_section="manual",
                    ))
                continue

    except PermissionError:
        _note_skipped(manual_dir)

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
                dest = resolve_user_dir(username) / "Profile"

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
        _note_skipped(profile_dir)

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
                dest = resolve_user_dir(handle, full_name) / "VE"

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
        _note_skipped(ve_dir)

    return items


# ── Data Collect Scanner ─────────────────────────────────────────────────────

def _scan_data_collect(source_dir: Path, downloader: str) -> list[ContentItem]:
    """Scan a Data Collect folder.

    Canonical layout:
      {root}/SAT Checks/Categories/...
      {root}/SAT Checks/Other/...
      {root}/MOT Checks/Categories/...
      {root}/MOT Checks/Other/...
      {root}/MOT Checks/{Profile,Reshares,VE}/...
    Legacy fallback: {root}/Categories/... (no SAT Checks wrapper).
    """
    items: list[ContentItem] = []
    archive_date = today_str()

    # ── SAT Checks section ──
    sat_dir = source_dir / "SAT Checks"
    if sat_dir.is_dir():
        sat_categories = sat_dir / "Categories"
        if sat_categories.is_dir():
            items.extend(_scan_data_collect_categories(sat_categories, downloader, archive_date))
        sat_other = sat_dir / "Other"
        if sat_other.is_dir():
            items.extend(_walk_other_tree(sat_other, downloader, archive_date, "sat_other"))
    else:
        # Legacy flat layout
        cat_dir = source_dir / "Categories"
        if cat_dir.is_dir():
            items.extend(_scan_data_collect_categories(cat_dir, downloader, archive_date))

    # ── MOT Checks section ──
    mot_dir = source_dir / "MOT Checks"
    if mot_dir.is_dir():
        items.extend(_scan_mot_checks(mot_dir, downloader, archive_date))

    return items


def _scan_data_collect_categories(
    cat_dir: Path, downloader: str, archive_date: str,
) -> list[ContentItem]:
    """Scan Data Collect Categories/ section using _walk_stories_tree."""
    items: list[ContentItem] = []
    acc = StoryGroupAccumulator(downloader, archive_date, "data_collect", "categories")
    _walk_stories_tree(
        cat_dir, cat_dir, items, acc.groups, downloader, archive_date,
        context_parser=parse_data_collect_categories_context,
        folder_type="data_collect",
        content_section="categories",
    )
    items.extend(acc.to_items())
    return items


def _scan_mot_checks(
    mot_dir: Path, downloader: str, archive_date: str,
) -> list[ContentItem]:
    """Scan MOT Checks/ section (Categories/PW, Profile, Reshares, VE)."""
    items: list[ContentItem] = []

    # ── Categories (reuses MO scanner for PW/RPT/etc. structure) ──
    categories_dir = mot_dir / "Categories"
    if categories_dir.is_dir():
        mot_items = _scan_sat_daily_mo(
            categories_dir, downloader, archive_date,
            folder_type="data_collect", content_section="mot_checks",
        )
        items.extend(mot_items)

    # ── Profile ──
    profile_dir = mot_dir / "Profile"
    if profile_dir.is_dir():
        for item in _scan_daily_mo_profile(profile_dir, archive_date):
            item.downloader = downloader
            item.folder_type = "data_collect"
            item.content_section = "profile"
            items.append(item)

    # ── Reshares ──
    reshares_dir = mot_dir / "Reshares"
    if reshares_dir.is_dir():
        for item in _scan_daily_mo_reshares(reshares_dir, archive_date):
            item.downloader = downloader
            item.folder_type = "data_collect"
            item.content_section = "reshares"
            items.append(item)

    # ── VE ──
    ve_dir = mot_dir / "VE"
    if ve_dir.is_dir():
        for item in _scan_daily_mo_ve(ve_dir, archive_date):
            item.downloader = downloader
            item.folder_type = "data_collect"
            item.content_section = "ve"
            items.append(item)

    # ── Other/ — free-form buckets (Regular Comment, Projects, etc.) ──
    other_dir = mot_dir / "Other"
    if other_dir.is_dir():
        items.extend(_walk_other_tree(other_dir, downloader, archive_date, "mot_other"))

    return items


def _walk_other_tree(
    root: Path,
    downloader: str,
    archive_date: str,
    content_section: str,
) -> list[ContentItem]:
    """Recursively walk an Other/ bucket and dispatch content to existing builders.

    The path from Other/ down to (but not including) the content leaf is captured
    into manual_notes so the sheet preserves the bucket context (e.g.
    "Projects / Project Hope" or "Regular Comment / Thread") without forcing
    these items into the regular dropdown taxonomy.
    """
    items: list[ContentItem] = []
    acc = StoryGroupAccumulator(
        downloader, archive_date, "data_collect", content_section,
        include_batch_wpas=False,
    )

    def label_for(container: Path) -> str:
        try:
            rel = container.relative_to(root)
        except ValueError:
            return ""
        parts = [p for p in rel.parts if p]
        return " / ".join(parts)

    def visit(current: Path) -> None:
        try:
            entries = sorted(current.iterdir())
        except PermissionError:
            _note_skipped(current)
            return

        for entry in entries:
            if entry.name.startswith("."):
                continue

            if entry.is_dir():
                name = entry.name

                if POST_FOLDER_RE.match(name):
                    item = _build_post_item(
                        entry, downloader, archive_date, "data_collect", content_section,
                    )
                    if item:
                        item.manual_notes = label_for(entry.parent)
                        items.append(item)
                    continue

                if PROFILE_FOLDER_RE.match(name):
                    item = _build_profile_item(
                        entry, downloader, archive_date, "data_collect", content_section,
                    )
                    if item:
                        item.manual_notes = label_for(entry.parent)
                        items.append(item)
                    continue

                if COMMENT_FOLDER_RE.match(name):
                    item = _build_comment_thread_item(
                        entry, downloader, archive_date, "data_collect", content_section,
                    )
                    if item:
                        item.manual_notes = label_for(entry.parent)
                        items.append(item)
                    continue

                if NAMED_STORY_FOLDER_RE.match(name) or STORIES_TXT_FOLDER_RE.match(name):
                    if _folder_contains_story_files(entry):
                        _collect_story_files_from_dir(entry, root, acc.groups)
                    else:
                        item = _build_named_story_item(
                            entry, downloader, archive_date, "data_collect", content_section,
                        )
                        if item:
                            item.manual_notes = label_for(entry.parent)
                            items.append(item)
                    continue

                # Plain directory — recurse
                visit(entry)

            elif entry.is_file():
                parsed = parse_story_filename(entry.name)
                if parsed:
                    _add_to_story_group(entry, parsed, root, acc.groups)

    visit(root)

    def _notes_for_story(group: dict) -> str:
        parent = group["parent_dir"]
        return label_for(parent) if parent is not None else ""

    items.extend(acc.to_items(notes_fn=_notes_for_story))
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

    real_name = metadata.get("full_name", "")
    dest = resolve_user_dir(username, real_name) / "Posts"
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    # Determine if paired from folder name
    paired = " - PAIRED" in folder.name

    # P&V-only fields from metadata
    post_url = metadata.get("post_url", "")
    meta_media_count = str(metadata.get("media_count", "")) if metadata.get("media_count") else ""
    meta_comment_count = str(metadata.get("comment_count", "")) if metadata.get("comment_count") else ""
    caption = metadata.get("caption", "")
    caption_prev = caption[:200] if caption else ""

    return ContentItem(
        timestamp=archive_date,
        shortcode=shortcode,
        real_name=real_name,
        username=username,
        post_type="Post",
        downloader=downloader,
        post_date=date_str,
        collaborators=collabs,
        db_link=db_link,
        paired_content="Yes" if paired else "",
        url=post_url,
        media_count=meta_media_count,
        comment_count=meta_comment_count,
        caption_preview=caption_prev,
        destination_path=str(dest),
        source_path=folder,
        source_files=all_files,
        is_folder_item=True,
        has_metadata_json=has_meta,
        move_as_folder=True,
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
    full_name = parsed["full_name"]
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = resolve_user_dir(handle, full_name) / "Profile"
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        timestamp=archive_date,
        shortcode=pseudo,
        real_name=full_name,
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
    dest = resolve_user_dir(handle) / "Posts"
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
        move_as_folder=True,
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
    full_name = parsed.get("full_name", "")
    pseudo = generate_pseudo_shortcode(handle, date_str, folder.name)
    dest = resolve_user_dir(handle, full_name) / "Stories"
    all_files = [f for f in folder.rglob("*") if f.is_file() and not f.name.startswith(".")]

    return ContentItem(
        timestamp=archive_date,
        shortcode=pseudo,
        real_name=full_name,
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
        _note_skipped(folder)
    return False


def _collect_story_files_from_dir(
    folder: Path,
    root_dir: Path,
    story_groups: dict[str, dict],
    mo_column: str = "",
    mo_value: str = "",
    context_parser=None,
) -> None:
    """Collect Type A story files from a folder."""
    try:
        for entry in sorted(folder.iterdir()):
            if entry.is_file():
                parsed = parse_story_filename(entry.name)
                if parsed:
                    _add_to_story_group(entry, parsed, root_dir, story_groups,
                                        mo_column=mo_column, mo_value=mo_value,
                                        context_parser=context_parser)
    except PermissionError:
        _note_skipped(folder)


def _add_to_story_group(
    file_path: Path,
    parsed: dict,
    root_dir: Path,
    story_groups: dict[str, dict],
    mo_column: str = "",
    mo_value: str = "",
    resharer_username: str = "",
    resharer_name: str = "",
    context_parser=None,
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
        parser = context_parser or parse_sat_daily_stories_context
        try:
            rel = file_path.parent.relative_to(root_dir)
            group["ctx"] = parser(rel.parts)
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
