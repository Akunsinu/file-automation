"""File/folder move operations for archiving."""

from __future__ import annotations

import shutil
from pathlib import Path

from .models import ContentItem


def move_items(items: list[ContentItem], dry_run: bool = False) -> tuple[int, int]:
    """Move all content items to their destination paths.

    Returns (success_count, error_count).
    """
    success = 0
    errors = 0

    for item in items:
        try:
            dest = Path(item.destination_path)
            if dry_run:
                print(f"  [DRY RUN] Would move -> {dest}")
                success += 1
                continue

            if item.is_folder_item:
                _move_folder(item.source_path, dest)
            else:
                _move_story_group(item.source_files, dest)
            success += 1

        except Exception as exc:
            print(f"  Error moving {item.shortcode}: {exc}")
            errors += 1

    return success, errors


def _move_folder(source: Path, dest: Path) -> None:
    """Move an entire folder to destination."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists():
        # Append shortcode-based suffix to avoid collision
        dest = dest.parent / f"{dest.name}_dup"
        print(f"  Destination exists, using: {dest.name}")

    shutil.move(str(source), str(dest))


def _move_story_group(files: list[Path], dest_folder: Path) -> None:
    """Move a group of story files into a new subfolder."""
    dest_folder.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = dest_folder / f.name
        if target.exists():
            print(f"  Skipping existing file: {f.name}")
            continue
        shutil.move(str(f), str(target))
