"""File/folder move operations for archiving."""

from __future__ import annotations

import shutil
from pathlib import Path

from .models import ContentItem


def move_items(items: list[ContentItem], dry_run: bool = False) -> tuple[int, int]:
    """Move all content items to their destination paths.

    Posts/Comment Threads: move entire folder as-is under Posts/.
    Everything else: move files loose into the destination folder.

    Returns (success_count, error_count).
    """
    success = 0
    errors = 0

    for item in items:
        try:
            dest = Path(item.destination_path)
            if item.post_type in ("Post", "Comment Thread") and item.source_path:
                source_folder = Path(item.source_path)
                if dry_run:
                    print(f"  [DRY RUN] Would move folder {source_folder.name} -> {dest}")
                else:
                    _move_folder(source_folder, dest)
            else:
                if dry_run:
                    print(f"  [DRY RUN] Would move {len(item.source_files)} files -> {dest}")
                else:
                    _move_files(item.source_files, dest)
            success += 1

        except Exception as exc:
            print(f"  Error moving {item.shortcode}: {exc}")
            errors += 1

    return success, errors


def _move_folder(source_folder: Path, dest_parent: Path) -> None:
    """Move entire folder as-is into the destination parent directory."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    target = dest_parent / source_folder.name
    if target.exists():
        print(f"  Skipping existing folder: {source_folder.name}")
        return
    shutil.move(str(source_folder), str(target))


def _move_files(files: list[Path], dest_folder: Path) -> None:
    """Move files directly into the destination folder."""
    dest_folder.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = dest_folder / f.name
        if target.exists():
            print(f"  Skipping existing file: {f.name}")
            continue
        shutil.move(str(f), str(target))
