"""Constants, regex patterns, and paths for SAT Archiver."""

import re
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────
ARCHIVE_ROOT = Path.home() / "Downloads" / "Instagram Archive"
SOURCE_GLOB = str(Path.home() / "Downloads" / "SAT Daily on ????-??-??")
SAT_CHECKS_SUBDIR = "SAT Checks - TO - RTA"

# ── Content type regex patterns (applied to filenames/folder names) ──────────

# Type A: Story files
# {prefix}_story_{YYYYMMDD}_{HHMMSS}_{seq}_{shortcode}_{suffix}.{ext}
# prefix = optional "Display Name " + username
# shortcode can contain [A-Za-z0-9_-]
STORY_FILE_RE = re.compile(
    r"^(.+)_story_(\d{8})_(\d{6})_(\d{2})_(.+)_(raw|screencapture|screenshot)\.(mp4|jpg|png)$"
)

# Type B: Post folders
# {username}_IG_POST_{YYYYMMDD}_{shortcode}[ - PAIRED]
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

# ── WPAS code extraction ──────────────────────────────────────────────────────
WPAS_RE = re.compile(r"^WPAS\s+(.+)$")

# ── Story file suffixes (the 3 files per story) ──────────────────────────────
STORY_SUFFIXES = {"raw", "screencapture", "screenshot"}

# ── Google Sheet column headers ───────────────────────────────────────────────
SHEET_HEADERS = [
    "Shortcode",
    "Username",
    "Full Name",
    "Content Type",
    "Category",
    "WPAS Code",
    "Date Posted",
    "Media Type",
    "Like Count",
    "Comment Count",
    "Caption",
    "Post URL",
    "Batch",
    "Section",
    "Archiver Initials",
    "Archive Date",
    "Destination Path",
]
