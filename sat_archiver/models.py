"""ContentItem dataclass for SAT Archiver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ContentItem:
    """A single piece of Instagram content to be archived."""

    # ── Sheet columns ─────────────────────────────────────────────────────
    shortcode: str = ""
    username: str = ""
    full_name: str = ""
    content_type: str = ""          # Story, Post, Profile, Comment Thread, Story Collection
    category: str = ""
    wpas_code: str = ""
    date_posted: str = ""           # YYYY-MM-DD
    media_type: str = ""            # Video, Image, Mixed
    like_count: int = 0
    comment_count: int = 0
    caption: str = ""               # truncated to 500 chars
    post_url: str = ""
    batch: str = ""
    section: str = ""
    archiver_initials: str = ""
    archive_date: str = ""          # YYYY-MM-DD (date of archiving)
    destination_path: str = ""

    # ── Internal fields (not written to sheet) ────────────────────────────
    source_path: Optional[Path] = None          # primary source path
    source_files: list[Path] = field(default_factory=list)  # all files in this item
    is_folder_item: bool = False                # True for Type B/D/E
    has_metadata_json: bool = False

    def to_row(self) -> list[str]:
        """Return sheet row as list of strings."""
        return [
            self.shortcode,
            self.username,
            self.full_name,
            self.content_type,
            self.category,
            self.wpas_code,
            self.date_posted,
            self.media_type,
            str(self.like_count) if self.like_count else "",
            str(self.comment_count) if self.comment_count else "",
            self.caption[:500] if self.caption else "",
            self.post_url,
            self.batch,
            self.section,
            self.archiver_initials,
            self.archive_date,
            self.destination_path,
        ]
