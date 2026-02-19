"""File/folder move operations for archiving."""

from __future__ import annotations

import shutil
from pathlib import Path

from .models import ContentItem


def move_items(items: list[ContentItem], dry_run: bool = False) -> tuple[int, int]:
    """Move all content items to their destination paths.

    Destination is a category folder (e.g. username/Posts, username/Stories).
    All files are moved directly into that folder — no per-item subfolders.

    Returns (success_count, error_count).
    """
    success = 0
    errors = 0

    for item in items:
        try:
            dest = Path(item.destination_path)
            if dry_run:
                print(f"  [DRY RUN] Would move {len(item.source_files)} files -> {dest}")
                success += 1
                continue

            _move_files(item.source_files, dest)
            success += 1

        except Exception as exc:
            print(f"  Error moving {item.shortcode}: {exc}")
            errors += 1

    return success, errors


def _move_files(files: list[Path], dest_folder: Path) -> None:
    """Move files directly into the destination folder."""
    dest_folder.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = dest_folder / f.name
        if target.exists():
            print(f"  Skipping existing file: {f.name}")
            continue
        shutil.move(str(f), str(target))
