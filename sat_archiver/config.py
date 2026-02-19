"""Constants, regex patterns, and paths for SAT Archiver."""

import re
from enum import Enum
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ARCHIVE_ROOT = Path.home() / "Downloads" / "Instagram Archive"
SOURCE_GLOBS = [
    str(Path.home() / "Downloads" / "SAT Daily on ????-??-??"),
    str(Path.home() / "Downloads" / "Daily MO on ????-??-??"),
]
# Legacy single glob (still used by some call sites)
SOURCE_GLOB = SOURCE_GLOBS[0]

# Dynamic SAT Checks subdir detection: "SAT Checks - {initials} - RTA"
SAT_CHECKS_RE = re.compile(r"^SAT Checks - (.+?) - RTA$")

# ── Tab names ──────────────────────────────────────────────────────────────────
TAB_STORIES = "Stories"
TAB_PV_MANUAL = "P&V Manual Backup"

# ── Folder type enum ──────────────────────────────────────────────────────────
class FolderType(Enum):
    SAT_DAILY = "sat_daily"
    DAILY_MO = "daily_mo"
    UNKNOWN = "unknown"

# ── Content type regex patterns (applied to filenames/folder names) ──────────

# Type A: Story files
# {prefix}_story_{YYYYMMDD}_{HHMMSS}_{seq}_{shortcode}_{suffix}.{ext}
STORY_FILE_RE = re.compile(
    r"^(.+)_story_(\d{8})_(\d{6})_(\d{2})_(.+)_(raw|screencapture|screenshot)\.(mp4|jpg|jpeg|png)$"
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
# IG Stories - YYYY-MM-DD - Name - handle
NAMED_STORY_FOLDER_RE = re.compile(
    r"^IG Stories - (\d{4}-\d{2}-\d{2}) - (.+?) - ([\w.]+)$"
)

# Type E variant: IG Stories TXT folders
# IG Stories TXT - ... - @handle
STORIES_TXT_FOLDER_RE = re.compile(
    r"^IG Stories TXT\b.*?(\d{4}-\d{2}-\d{2}).*?@([\w.]+)$"
)

# IG Reshare folder: IG Reshare - YYYY-MM-DD - Name - handle
RESHARE_FOLDER_RE = re.compile(
    r"^IG Reshare - (\d{4}-\d{2}-\d{2}) - (.+?) - ([\w.]+)$"
)

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
STORY_SUFFIXES = {"raw", "screencapture", "screenshot"}

# ── Collaborator extraction from folder name ─────────────────────────────────
# e.g. healingthesource_IG_POST_20260213_DUs81C4FFly_collab_mayuwater
COLLAB_FOLDER_RE = re.compile(r"_collab_([\w.]+(?:_[\w.]+)*)$")

# ── Story category → column field mapping ────────────────────────────────────
# Maps SAT Daily Stories category folder names to ContentItem field names
STORY_CATEGORY_TO_COLUMN = {
    "Books": "books",
    "Conditions": "conditions",
    "Emotional Support": "emotional_support",
    "Fear": "fear",
    "Food": "food",
    "Healing Stories": "healing_stories",
    "Healing Tools": "healing_tools",
    "Healing Tools More": "healing_tools_more",
    "History": "history",
    "Miscellaneous": "miscellaneous",
    "MM Science": "mm_science",
    "Other": "other",
    "PW Trends": "pw_trends",
    "Resources": "resources",
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

# ── Google Sheet column headers (37 columns, A-AK) ──────────────────────────
SHEET_HEADERS = [
    "Timestamp",                  # A
    "Shortcode",                  # B
    "Real Name",                  # C
    "Username",                   # D
    "Post Type",                  # E
    "Downloader",                 # F
    "Post Date",                  # G
    "Collaborators",              # H
    "Manual Notes",               # I
    "DB Link",                    # J
    "Paired Content",             # K
    "Stories Reshare Links",      # L
    "Primary Beginning Tags",     # M
    "Secondary Beginning Tags",   # N
    "General Triggers",           # O
    "Sheet Categories",           # P
    "Books",                      # Q
    "Conditions",                 # R
    "Emotional Support",          # S
    "Fear",                       # T
    "Food",                       # U
    "Healing Stories",            # V
    "Healing Tools",              # W
    "Healing Tools More",         # X
    "History",                    # Y
    "Miscellaneous",              # Z
    "MM Science",                 # AA
    "Other",                      # AB
    "PW Trends",                  # AC
    "Resources",                  # AD
    "Supporting",                 # AE
    "MO-Publication",             # AF
    "MO-PW",                      # AG
    "MO-RPT",                     # AH
    "MO-SI",                      # AI
    "MO-TS",                      # AJ
    "MO-WTS",                     # AK
]
