"""Constants, regex patterns, and paths for SAT Archiver."""

import re
from enum import Enum
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ARCHIVE_ROOT = Path.home() / "Downloads" / "Instagram Archive"
SOURCE_GLOBS = [
    str(Path.home() / "Downloads" / "SAT Daily on ????-??-??"),
    str(Path.home() / "Downloads" / "Daily MO on ????-??-??"),
    str(Path.home() / "Downloads" / "Data Collect on ????-??-?? - * - *"),
]
# Legacy single glob (still used by some call sites)
SOURCE_GLOB = SOURCE_GLOBS[0]

# Dynamic SAT Checks subdir detection: "SAT Checks - {initials} - RTA"
SAT_CHECKS_RE = re.compile(r"^SAT Checks - (.+?) - RTA$")

# ── Tab names ──────────────────────────────────────────────────────────────────
TAB_STORIES = "Stories"
TAB_PV_MANUAL = "P&V Manual Backup"
TAB_VE = "VE"

# ── Folder type enum ──────────────────────────────────────────────────────────
class FolderType(Enum):
    SAT_DAILY = "sat_daily"
    DAILY_MO = "daily_mo"
    DATA_COLLECT = "data_collect"
    UNKNOWN = "unknown"

# Data Collect folder name: "Data Collect on YYYY-MM-DD - INITIALS - SUFFIX"
DATA_COLLECT_RE = re.compile(r"^Data Collect on \d{4}-\d{2}-\d{2} - (.+?) - (.+)$")

# ── Content type regex patterns (applied to filenames/folder names) ──────────

# Type A: Story files
# Standard:  {prefix}_story_{YYYYMMDD}_{HHMMSS}_{seq}_{shortcode}_{suffix}.{ext}
# Long-ID:   {prefix}_story_{YYYYMMDD}_{HHMMSS}_{longid}_{suffix}.{ext}
STORY_FILE_RE = re.compile(
    r"^(.+)_story_(\d{8})_(\d{6})_(\d+)_(?:(.+?)_)?(raw|screencapture|screenshot|original)\.(mp4|jpg|jpeg|png|webp)$"
)

# Type B: Post folders
# {username}_IG_POST_{YYYYMMDD}_{shortcode}[ - PAIRED][_collab_...]
POST_FOLDER_RE = re.compile(
    r"^(.+?)_IG_POST_(\d{8})_(.+?)(?:\s+-\s+PAIRED)?$"
)

# Type C: Comment files (inside post folders - grouped with parent)
COMMENT_FILE_RE = re.compile(
    r"^(.+?)_IG_POST_(\d{8})_(.+?)_COMMENT_(\d+)_(\d{8})_([\w.]+)\.(jpg|png)$"
)

# Type D: Profile folders
# IG Profile - YYYY-MM-DD - Name - @handle
PROFILE_FOLDER_RE = re.compile(
    r"^IG Profile - (\d{4}-\d{2}-\d{2}) - (.+?) - @([\w.]+)$"
)

# Type D: Comment thread folders
# IG Regular Comment - ... - @handle[ - PAIRED]
COMMENT_FOLDER_RE = re.compile(
    r"^IG Regular Comment\b.*?(\d{4}-\d{2}-\d{2}).*?- @([\w.]+)(?:\s+-\s+PAIRED)?$"
)

# Type E: Named story folders
# IG Stories - YYYY-MM-DD - Name - handle[ - With TRANSL]
NAMED_STORY_FOLDER_RE = re.compile(
    r"^IG Stories - (\d{4}-\d{2}-\d{2}) - (.+?) - @?([\w.]+)(?:\s+-\s+.+)?$"
)

# Type E variant: IG Stories TXT folders
# IG Stories TXT - ... - @handle
STORIES_TXT_FOLDER_RE = re.compile(
    r"^IG Stories TXT\b.*?(\d{4}-\d{2}-\d{2}).*?@([\w.]+)$"
)

# IG Reshare folder: IG Reshare - YYYY-MM-DD - Name - @?handle
RESHARE_FOLDER_RE = re.compile(
    r"^IG Reshare - (\d{4}-\d{2}-\d{2}) - (.+?) - @?([\w.]+)$"
)

# RS CSV files: IG_RS[_L]*.csv
RS_CSV_RE = re.compile(r"^IG_RS[_L].*\.csv$", re.IGNORECASE)

# IG VE files: IG VE - date(s) - Name - handle[ - N].MP4
VE_FILE_RE = re.compile(
    r"^IG VE - (.+?) - (.+?) - ([\w.]+?)(?:\s+-\s+\d+)?\.MP4$",
    re.IGNORECASE,
)

# Profile screenshot files: {username}_profile_{YYYYMMDD}.png
PROFILE_FILE_RE = re.compile(
    r"^([\w.]+)_profile_(\d{8})\.(png|jpg)$"
)

# ── WPAS code extraction ──────────────────────────────────────────────────────
WPAS_RE = re.compile(r"^WPAS\s+(.+)$")

# ── Story file suffixes (the 3 files per story) ──────────────────────────────
STORY_SUFFIXES = {"raw", "screencapture", "screenshot", "original"}

# ── Collaborator extraction from folder name ─────────────────────────────────
# e.g. healingthesource_IG_POST_20260213_DUs81C4FFly_collab_mayuwater
COLLAB_FOLDER_RE = re.compile(r"_collab_([\w.]+(?:_[\w.]+)*)$")

# ── Story category → column field mapping ────────────────────────────────────
# Maps SAT Daily Stories category folder names to ContentItem field names
STORY_CATEGORY_TO_COLUMN = {
    "Projects": "projects",
    "Books": "books",
    "Original Audio": "original_audio",
    "Food": "food",
    "Healing Stories": "healing_stories",
    "Healing Stories Exception": "healing_stories_exception",
    "Healing Tools": "healing_tools",
    "Healing Tools More": "healing_tools_more",
    "Miscellaneous": "miscellaneous",
    "Other": "other",
    "Pets": "pets",
    "Resources": "resources",
    "Special": "special",
    "Special Occasions": "special_occasions",
    "Spiritual": "spiritual",
    "Supporting": "supporting",
}

# ── MO sub-path → column field mapping ───────────────────────────────────────
# Maps Additional/MO/{type} folder names to ContentItem field names
MO_PATH_TO_COLUMN = {
    "PW": "mo_pw",
    "RPT": "mo_rpt",
    "SI": "mo_si",
    "TS": "mo_ts",
    "WTS": "mo_wts",
}

# ── Google Sheet column headers ──────────────────────────────────────────────
# Stories tab: 38 columns (A-AL)
SHEET_HEADERS_STORIES = [
    "timestamp",                  # A
    "shortcode",                  # B
    "real_name",                  # C
    "username",                   # D
    "post_type",                  # E
    "downloader",                 # F
    "post_date",                  # G
    "collaborators",              # H
    "manual notes",               # I
    "DB Link",                    # J
    "paired content",             # K
    "stories reshare links",      # L
    "Primary Beginning Tags",     # M
    "Secondary Beginning Tags",   # N
    "General Triggers",           # O
    "Sheet Categories",           # P
    "Projects",                   # Q
    "Books",                      # R
    "Original Audio",             # S
    "Food",                       # T
    "Healing Stories",            # U
    "Healing Stories Exception",  # V
    "Healing Tools",              # W
    "Healing Tools More",         # X
    "Miscellaneous",              # Y
    "Other",                      # Z
    "Pets",                       # AA
    "Resources",                  # AB
    "Special",                    # AC
    "Special Occasions",          # AD
    "Spiritual",                  # AE
    "Supporting",                 # AF
    "MO - Publication",           # AG
    "MO - PW",                    # AH
    "MO - RPT",                   # AI
    "MO - SI",                    # AJ
    "MO - TS",                    # AK
    "MO - WTS",                   # AL
]

# VE tab: 8 columns (A-H)
SHEET_HEADERS_VE = [
    "timestamp",                  # A
    "shortcode",                  # B
    "real_name",                  # C
    "username",                   # D
    "downloader",                 # E
    "post_date",                  # F
    "DB Link",                    # G
    "manual notes",               # H
]

# P&V Manual Backup tab: 41 columns (A-AO)
SHEET_HEADERS_PV = [
    "timestamp",                  # A
    "shortcode",                  # B
    "url",                        # C
    "real_name",                  # D
    "username",                   # E
    "post_type",                  # F
    "media_count",                # G
    "comment_count",              # H
    "caption_preview",            # I
    "downloader",                 # J
    "post_date",                  # K
    "collaborators",              # L
    "manual notes",               # M
    "DB Link",                    # N
    "paired content",             # O
    "Primary Beginning Tags",     # P
    "Secondary Beginning Tags",   # Q
    "General Triggers",           # R
    "Sheet Categories",           # S
    "Projects",                   # T
    "Books",                      # U
    "Original Audio",             # V
    "Food",                       # W
    "Healing Stories",            # X
    "Healing Stories Exception",  # Y
    "Healing Tools",              # Z
    "Healing Tools More",         # AA
    "Miscellaneous",              # AB
    "Other",                      # AC
    "Pets",                       # AD
    "Resources",                  # AE
    "Special",                    # AF
    "Special Occasions",          # AG
    "Spiritual",                  # AH
    "Supporting",                 # AI
    "MO - Publication",           # AJ
    "MO - PW",                    # AK
    "MO - RPT",                   # AL
    "MO - SI",                    # AM
    "MO - TS",                    # AN
    "MO - WTS",                   # AO
]
