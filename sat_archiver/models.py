"""ContentItem dataclass for SAT Archiver."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ContentItem:
    """A single piece of Instagram content to be archived.

    Stories tab: 38 columns (A-AL).
    P&V Manual Backup tab: 41 columns (A-AO) — adds url, media_count,
    comment_count, caption_preview; omits stories_reshare_links.
    """

    # ── Sheet columns (shared base fields) ───────────────────────────────
    timestamp: str = ""               # A (both tabs)
    shortcode: str = ""               # B (both tabs)
    real_name: str = ""               # C (Stories) / D (P&V)
    username: str = ""                # D (Stories) / E (P&V)
    post_type: str = ""               # E / F — Story, Post, Profile, etc.
    downloader: str = ""              # F / J — archiver initials
    post_date: str = ""               # G / K — YYYY-MM-DD
    collaborators: str = ""           # H / L — comma-separated
    manual_notes: str = ""            # I / M
    db_link: str = ""                 # J / N — primary media file path
    paired_content: str = ""          # K / O
    stories_reshare_links: str = ""   # L (Stories only — not in P&V)

    # ── P&V-only columns ─────────────────────────────────────────────────
    url: str = ""                     # C (P&V only) — post URL
    media_count: str = ""             # G (P&V only)
    comment_count: str = ""           # H (P&V only)
    caption_preview: str = ""         # I (P&V only)

    # ── Sheet columns: tag dropdowns ─────────────────────────────────────
    primary_beginning_tags: str = ""  # M / P
    secondary_beginning_tags: str = ""  # N / Q
    general_triggers: str = ""        # O / R
    sheet_categories: str = ""        # P / S

    # ── Sheet columns: content category dropdowns ────────────────────────
    projects: str = ""                # Q / T
    books: str = ""                   # R / U
    original_audio: str = ""          # S / V
    food: str = ""                    # T / W
    healing_stories: str = ""         # U / X
    healing_stories_exception: str = ""  # V / Y
    healing_tools: str = ""           # W / Z
    healing_tools_more: str = ""      # X / AA
    miscellaneous: str = ""           # Y / AB
    other: str = ""                   # Z / AC
    pets: str = ""                    # AA / AD
    resources: str = ""               # AB / AE
    special: str = ""                 # AC / AF
    special_occasions: str = ""       # AD / AG
    spiritual: str = ""               # AE / AH
    supporting: str = ""              # AF / AI

    # ── Sheet columns: MO dropdowns ──────────────────────────────────────
    mo_publication: str = ""          # AG / AJ
    mo_pw: str = ""                   # AH / AK
    mo_rpt: str = ""                  # AI / AL
    mo_si: str = ""                   # AJ / AM
    mo_ts: str = ""                   # AK / AN
    mo_wts: str = ""                  # AL / AO

    # ── Internal fields (not written to sheet) ────────────────────────────
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
        if self.post_type in ("Story", "Story Collection"):
            return "Stories"
        return "P&V Manual Backup"

    @property
    def dest_db_link(self) -> str:
        """DB Link pointing to the archive destination (not source)."""
        if not self.db_link or not self.destination_path:
            return self.db_link
        src = Path(self.db_link)
        dest = Path(self.destination_path)
        if self.post_type in ("Post", "Comment Thread") and self.source_path:
            # Post folder is moved as-is: dest / folder_name / relative_path
            folder = Path(self.source_path)
            try:
                rel = src.relative_to(folder)
                return str(dest / folder.name / rel)
            except ValueError:
                return str(dest / src.name)
        # Loose files: dest / filename
        return str(dest / src.name)

    def to_row(self) -> list[str]:
        """Return sheet row matching the target tab's column layout."""
        if self.target_tab == "Stories":
            return self._to_stories_row()
        return self._to_pv_row()

    def _to_stories_row(self) -> list[str]:
        """38-element list for Stories tab (A-AL)."""
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
            self.dest_db_link,
            self.paired_content,
            self.stories_reshare_links,
            self.primary_beginning_tags,
            self.secondary_beginning_tags,
            self.general_triggers,
            self.sheet_categories,
            self.projects,
            self.books,
            self.original_audio,
            self.food,
            self.healing_stories,
            self.healing_stories_exception,
            self.healing_tools,
            self.healing_tools_more,
            self.miscellaneous,
            self.other,
            self.pets,
            self.resources,
            self.special,
            self.special_occasions,
            self.spiritual,
            self.supporting,
            self.mo_publication,
            self.mo_pw,
            self.mo_rpt,
            self.mo_si,
            self.mo_ts,
            self.mo_wts,
        ]

    def _to_pv_row(self) -> list[str]:
        """41-element list for P&V Manual Backup tab (A-AO)."""
        return [
            self.timestamp,
            self.shortcode,
            self.url,
            self.real_name,
            self.username,
            self.post_type,
            self.media_count,
            self.comment_count,
            self.caption_preview,
            self.downloader,
            self.post_date,
            self.collaborators,
            self.manual_notes,
            self.dest_db_link,
            self.paired_content,
            self.primary_beginning_tags,
            self.secondary_beginning_tags,
            self.general_triggers,
            self.sheet_categories,
            self.projects,
            self.books,
            self.original_audio,
            self.food,
            self.healing_stories,
            self.healing_stories_exception,
            self.healing_tools,
            self.healing_tools_more,
            self.miscellaneous,
            self.other,
            self.pets,
            self.resources,
            self.special,
            self.special_occasions,
            self.spiritual,
            self.supporting,
            self.mo_publication,
            self.mo_pw,
            self.mo_rpt,
            self.mo_si,
            self.mo_ts,
            self.mo_wts,
        ]
