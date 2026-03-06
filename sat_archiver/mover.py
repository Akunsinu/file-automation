"""File/folder move operations for archiving."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from .config import ARCHIVE_ROOT
from .models import ContentItem

# Characters unsafe for filesystem paths
_UNSAFE_CHARS_RE = re.compile(r'[/:\x00]')


def resolve_user_dir(username: str, real_name: str = "") -> Path:
    """Find or create a named archive directory for a username."""
    suffix = f" - @{username}"
    # 1. Look for existing "* - @{username}" folder
    if ARCHIVE_ROOT.is_dir():
        for d in ARCHIVE_ROOT.iterdir():
            if d.is_dir() and d.name.endswith(suffix):
                return d
    # 2. Bare "{username}" folder exists -> rename if real_name known
    bare = ARCHIVE_ROOT / username
    if bare.is_dir():
        if real_name:
            safe_name = _UNSAFE_CHARS_RE.sub("", real_name).strip()
            new_path = ARCHIVE_ROOT / f"{safe_name}{suffix}"
            bare.rename(new_path)
            return new_path
        return bare
    # 3. Create new path
    if real_name:
        safe_name = _UNSAFE_CHARS_RE.sub("", real_name).strip()
        return ARCHIVE_ROOT / f"{safe_name}{suffix}"
    return ARCHIVE_ROOT / f"@{username}"


def move_items(items: list[ContentItem], dry_run: bool = False) -> tuple[int, int]:
    """Move all content items to their destination paths.

    Returns (success_count, error_count).
    """
    success = 0
    errors = 0

    for item in items:
        try:
            dest = Path(item.destination_path)
            if item.post_type == "Reshare" and item.source_path:
                source_folder = Path(item.source_path)
                if dry_run:
                    print(f"  [DRY RUN] Would move+flatten folder {source_folder.name} -> {dest}")
                else:
                    _move_folder_flattened(source_folder, dest)
            elif item.move_as_folder and item.source_path:
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


def _move_folder_flattened(source_folder: Path, dest_parent: Path) -> None:
    """Move folder to dest, flattening all subdirectory contents into one level."""
    dest_parent.mkdir(parents=True, exist_ok=True)
    target = dest_parent / source_folder.name
    target.mkdir(parents=True, exist_ok=True)
    for f in source_folder.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            file_target = target / f.name
            if not file_target.exists():
                shutil.move(str(f), str(file_target))
    shutil.rmtree(str(source_folder), ignore_errors=True)


def _move_files(files: list[Path], dest_folder: Path) -> None:
    """Move files directly into the destination folder."""
    dest_folder.mkdir(parents=True, exist_ok=True)

    for f in files:
        target = dest_folder / f.name
        if target.exists():
            print(f"  Skipping existing file: {f.name}")
            continue
        shutil.move(str(f), str(target))
