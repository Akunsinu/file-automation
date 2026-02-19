"""Google Sheets integration via Apps Script web app."""

from __future__ import annotations

import csv
import json
import urllib.request
import urllib.error
from collections import defaultdict
from pathlib import Path

from .config import SHEET_HEADERS, TAB_STORIES, TAB_PV_MANUAL
from .models import ContentItem


def test_connection(url: str) -> tuple[str | None, str | None]:
    """GET url?action=test. Returns (ok_message, None) or (None, error_message)."""
    try:
        req = urllib.request.Request(f"{url}?action=test")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            if "<html" in body.lower():
                return None, (
                    "Google returned an HTML page instead of JSON. "
                    "Make sure the Apps Script is deployed as a Web app "
                    'with access set to "Anyone".'
                )
            return None, "Apps Script returned invalid JSON."
        if data.get("ok"):
            count = data.get("count", 0)
            counts = data.get("counts", {})
            parts = [f"{tab}: {c}" for tab, c in counts.items()]
            detail = f" ({', '.join(parts)})" if parts else ""
            return f"Connected. {count} existing entries{detail}.", None
        return None, data.get("error", "Unknown error from Apps Script.")
    except urllib.error.HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"Could not reach Apps Script URL: {exc.reason}"
    except Exception as exc:
        return None, f"Connection failed: {exc}"


def get_existing_shortcodes(url: str) -> set[str]:
    """GET url?action=shortcodes. Returns set of shortcode strings."""
    try:
        req = urllib.request.Request(f"{url}?action=shortcodes")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        return set(data.get("shortcodes", []))
    except Exception as exc:
        print(f"  Warning: could not read existing shortcodes: {exc}")
        return set()


def log_items_to_sheet(
    url: str, items: list[ContentItem], headers: list[str] | None = None
) -> bool:
    """POST rows as JSON to the Apps Script URL, grouped by target tab.

    Returns True if all tab writes succeed.
    """
    if not items:
        return True

    headers = headers or SHEET_HEADERS

    # Group items by target tab
    by_tab: dict[str, list[ContentItem]] = defaultdict(list)
    for item in items:
        by_tab[item.target_tab].append(item)

    all_ok = True
    for tab_name, tab_items in by_tab.items():
        rows = [item.to_row() for item in tab_items]
        payload = json.dumps({
            "headers": headers,
            "rows": rows,
            "tab": tab_name,
        }).encode()

        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            if data.get("ok"):
                print(f"  {tab_name}: {data.get('added', 0)} rows added.")
            else:
                print(f"  Apps Script error ({tab_name}): {data.get('error', 'unknown')}")
                all_ok = False
        except Exception as exc:
            print(f"  Sheet write failed ({tab_name}): {exc}")
            all_ok = False

    return all_ok


def write_csv_fallback(items: list[ContentItem], output_path: Path) -> None:
    """Write items to local CSV files, one per tab."""
    # Group by target tab
    by_tab: dict[str, list[ContentItem]] = defaultdict(list)
    for item in items:
        by_tab[item.target_tab].append(item)

    for tab_name, tab_items in by_tab.items():
        # Create tab-specific filename
        suffix = "_stories" if tab_name == TAB_STORIES else "_pv"
        csv_path = output_path.parent / f"{output_path.stem}{suffix}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(SHEET_HEADERS)
            for item in tab_items:
                writer.writerow(item.to_row())
        print(f"  Fallback CSV written to: {csv_path}")
