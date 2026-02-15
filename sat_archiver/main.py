"""CLI entry point and orchestration for SAT Archiver."""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

from .config import ARCHIVE_ROOT, SOURCE_GLOB
from .mover import move_items
from .scanner import scan_folder
from .sheets import (
    get_existing_shortcodes,
    log_items_to_sheet,
    test_connection,
    write_csv_fallback,
)


def find_latest_source_folder() -> Path | None:
    """Find the most recent SAT Daily folder by name sort."""
    folders = sorted(glob.glob(SOURCE_GLOB), reverse=True)
    if not folders:
        return None
    return Path(folders[0])


def load_config(config_path: Path) -> dict:
    """Load config.json if it exists."""
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def print_preview(items, label: str = "Items") -> None:
    """Print a summary table of discovered items."""
    type_counts: dict[str, int] = {}
    for item in items:
        type_counts[item.content_type] = type_counts.get(item.content_type, 0) + 1

    print(f"\n{'='*70}")
    print(f"  {label}: {len(items)} total")
    for ct, count in sorted(type_counts.items()):
        print(f"    {ct}: {count}")
    print(f"{'='*70}")

    print(f"\n{'Shortcode':<35} {'Type':<18} {'User':<25} {'Batch'}")
    print("-" * 100)
    for item in sorted(items, key=lambda i: (i.batch, i.content_type, i.username)):
        sc = item.shortcode
        if len(sc) > 33:
            sc = sc[:30] + "..."
        print(f"  {sc:<33} {item.content_type:<18} {item.username:<25} {item.batch}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SAT Instagram Content Archiver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--folder",
        type=Path,
        help="Source folder to scan (default: latest SAT Daily folder)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan and report without moving files or writing to sheet",
    )
    parser.add_argument(
        "--apps-script-url",
        help="Apps Script web app URL (overrides config.json)",
    )
    parser.add_argument(
        "--initials",
        help="Archiver initials (will prompt if not provided)",
    )

    args = parser.parse_args(argv)

    # ── Load config ──────────────────────────────────────────────────────
    project_root = Path(__file__).resolve().parent.parent
    config = load_config(project_root / "config.json")

    # ── Resolve source folder ────────────────────────────────────────────
    source_dir = args.folder
    if source_dir is None:
        source_dir = find_latest_source_folder()
        if source_dir is None:
            print("Error: No SAT Daily folder found in ~/Downloads/")
            return 1

    if not source_dir.is_dir():
        print(f"Error: {source_dir} is not a directory")
        return 1

    print(f"Source: {source_dir}")

    # ── Get archiver initials ────────────────────────────────────────────
    initials = args.initials
    if not initials and not args.dry_run:
        initials = input("Archiver initials: ").strip()
        if not initials:
            print("Error: Initials required")
            return 1
    initials = initials or "DRY"

    # ── Scan ─────────────────────────────────────────────────────────────
    print("\nScanning...")
    items = scan_folder(source_dir)

    if not items:
        print("No content items found.")
        return 0

    # Set initials on all items
    for item in items:
        item.archiver_initials = initials

    # ── Deduplicate against Google Sheet ──────────────────────────────────
    apps_script_url = args.apps_script_url or config.get("apps_script_url", "")
    existing_shortcodes: set[str] = set()

    if not args.dry_run and apps_script_url:
        print("\nConnecting to Google Sheet via Apps Script...")
        ok_msg, err = test_connection(apps_script_url)
        if err:
            print(f"  Warning: {err}")
            print("  Will fall back to CSV if needed.")
        else:
            print(f"  {ok_msg}")
            print("  Fetching existing shortcodes...")
            existing_shortcodes = get_existing_shortcodes(apps_script_url)
            print(f"  Found {len(existing_shortcodes)} existing entries.")

    # Filter out duplicates
    new_items = [i for i in items if i.shortcode not in existing_shortcodes]
    skipped = len(items) - len(new_items)

    if skipped:
        print(f"\n  Skipping {skipped} duplicate(s) already in sheet.")

    # ── Preview ──────────────────────────────────────────────────────────
    print_preview(new_items, label="New items to archive")

    if not new_items:
        print("\nNothing new to archive.")
        return 0

    # ── Confirm ──────────────────────────────────────────────────────────
    if args.dry_run:
        print("\n[DRY RUN] No files will be moved or logged.")
        return 0

    confirm = input(f"\nProceed with archiving {len(new_items)} items? [y/N] ").strip().lower()
    if confirm != "y":
        print("Aborted.")
        return 0

    # ── Move files ───────────────────────────────────────────────────────
    print(f"\nMoving files to {ARCHIVE_ROOT}...")
    moved, move_errors = move_items(new_items)
    print(f"  Moved: {moved}, Errors: {move_errors}")

    # ── Log to Google Sheet ──────────────────────────────────────────────
    if apps_script_url:
        print("\nLogging to Google Sheet via Apps Script...")
        ok = log_items_to_sheet(apps_script_url, new_items)
        if not ok:
            csv_path = source_dir / "archive_log_fallback.csv"
            print("  Sheet write failed. Writing CSV fallback...")
            write_csv_fallback(new_items, csv_path)
    else:
        csv_path = source_dir / "archive_log.csv"
        print(f"\nNo Apps Script URL configured. Writing CSV to {csv_path}")
        write_csv_fallback(new_items, csv_path)

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  Archive complete!")
    print(f"  Items archived: {moved}")
    print(f"  Duplicates skipped: {skipped}")
    print(f"  Errors: {move_errors}")
    print(f"  Archive root: {ARCHIVE_ROOT}")
    print(f"{'='*70}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
