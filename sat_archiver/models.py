"""ContentItem dataclass for SAT Archiver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ContentItem:
    """A single piece of Instagram content to be archived.

    Sheet columns match the 37-column schema (A-AK).
    """

    # ── Sheet columns (A-L: standard fields) ───────────────────────────────
    timestamp: str = ""               # A - archive date
    shortcode: str = ""               # B
    real_name: str = ""               # C
    username: str = ""                # D
    post_type: str = ""               # E - Story, Post, Profile, etc.
    downloader: str = ""              # F - archiver initials
    post_date: str = ""               # G - YYYY-MM-DD
    collaborators: str = ""           # H - comma-separated
    manual_notes: str = ""            # I
    db_link: str = ""                 # J - primary media file path
    paired_content: str = ""          # K
    stories_reshare_links: str = ""   # L

    # ── Sheet columns (M-P: tag dropdowns) ─────────────────────────────────
    primary_beginning_tags: str = ""  # M
    secondary_beginning_tags: str = ""  # N
    general_triggers: str = ""        # O
    sheet_categories: str = ""        # P

    # ── Sheet columns (Q-AE: content category dropdowns) ───────────────────
    books: str = ""                   # Q
    conditions: str = ""              # R
    emotional_support: str = ""       # S
    fear: str = ""                    # T
    food: str = ""                    # U
    healing_stories: str = ""         # V
    healing_tools: str = ""           # W
    healing_tools_more: str = ""      # X
    history: str = ""                 # Y
    miscellaneous: str = ""           # Z
    mm_science: str = ""              # AA
    other: str = ""                   # AB
    pw_trends: str = ""               # AC
    resources: str = ""               # AD
    supporting: str = ""              # AE

    # ── Sheet columns (AF-AK: MO dropdowns) ────────────────────────────────
    mo_publication: str = ""          # AF
    mo_pw: str = ""                   # AG
    mo_rpt: str = ""                  # AH
    mo_si: str = ""                   # AI
    mo_ts: str = ""                   # AJ
    mo_wts: str = ""                  # AK

    # ── Internal fields (not written to sheet) ──────────────────────────────
    source_path: Optional[Path] = None
    source_files: list[Path] = field(default_factory=list)
    is_folder_item: bool = False
    has_metadata_json: bool = False
    folder_type: str = ""             # "sat_daily" or "daily_mo"
    content_section: str = ""         # "stories", "pv", "mo", "categories", etc.
    batch: str = ""
    wpas_code: str = ""
    destination_path: str = ""
    resharer_username: str = ""
    resharer_name: str = ""

    @property
    def target_tab(self) -> str:
        """Determine which sheet tab this item belongs to."""
        if self.content_section == "stories":
            return "Stories"
        return "P&V Manual Backup"

    def to_row(self) -> list[str]:
        """Return sheet row as 37-element list of strings."""
        return [
            self.timestamp,
            self.shortcode,
            self.real_name,
            self.username,
            self.post_type,
            self.downloader,
            self.post_date,
            self.collaborators,
            self.manual_notes,
            self.db_link,
            self.paired_content,
            self.stories_reshare_links,
            self.primary_beginning_tags,
            self.secondary_beginning_tags,
            self.general_triggers,
            self.sheet_categories,
            self.books,
            self.conditions,
            self.emotional_support,
            self.fear,
            self.food,
            self.healing_stories,
            self.healing_tools,
            self.healing_tools_more,
            self.history,
            self.miscellaneous,
            self.mm_science,
            self.other,
            self.pw_trends,
            self.resources,
            self.supporting,
            self.mo_publication,
            self.mo_pw,
            self.mo_rpt,
            self.mo_si,
            self.mo_ts,
            self.mo_wts,
        ]
