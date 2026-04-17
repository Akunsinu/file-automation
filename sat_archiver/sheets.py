"""Google Sheets integration via Apps Script web app."""

from __future__ import annotations

import csv
import json
import time
import urllib.request
import urllib.error
from collections import defaultdict
from pathlib import Path

from .config import (
    SHEET_BATCH_SIZE,
    SHEET_DELAY_BETWEEN_BATCHES,
    SHEET_HEADERS_STORIES,
    SHEET_HEADERS_PV,
    SHEET_HEADERS_VE,
    SHEET_MAX_RETRIES,
    SHEET_REQUEST_TIMEOUT,
    SHEET_RETRY_BACKOFF_BASE,
    TAB_STORIES,
    TAB_PV_MANUAL,
    TAB_VE,
)
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


def log_items_to_sheet(url: str, items: list[ContentItem]) -> dict:
    """POST rows as JSON to the Apps Script URL, grouped by target tab.

    Returns dict with keys:
        ok (bool): True if all writes succeeded.
        rows_written (int): Total rows successfully written.
        rows_failed (int): Total rows that failed.
        errors (list[str]): Human-readable error messages.
    """
    result = {"ok": True, "rows_written": 0, "rows_failed": 0, "errors": []}

    if not items:
        return result

    # Filter out items that shouldn't be logged to sheet
    items = [i for i in items if not i.skip_sheet_log]
    if not items:
        return result

    # Group items by target tab
    by_tab: dict[str, list[ContentItem]] = defaultdict(list)
    for item in items:
        by_tab[item.target_tab].append(item)

    batch_size = SHEET_BATCH_SIZE
    max_retries = SHEET_MAX_RETRIES
    delay_between_batches = SHEET_DELAY_BETWEEN_BATCHES

    for tab_name, tab_items in by_tab.items():
        if tab_name == TAB_STORIES:
            headers = SHEET_HEADERS_STORIES
        elif tab_name == TAB_VE:
            headers = SHEET_HEADERS_VE
        else:
            headers = SHEET_HEADERS_PV
        rows = [item.to_row() for item in tab_items]
        total_batches = (len(rows) + batch_size - 1) // batch_size

        # Send in batches with retries and delays
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            batch_num = i // batch_size + 1
            payload = json.dumps({
                "headers": headers,
                "rows": batch,
                "tab": tab_name,
            }).encode()

            success = False
            last_error = ""
            for attempt in range(1, max_retries + 1):
                try:
                    req = urllib.request.Request(
                        url,
                        data=payload,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urllib.request.urlopen(req, timeout=SHEET_REQUEST_TIMEOUT) as resp:
                        data = json.loads(resp.read().decode())
                    if data.get("ok"):
                        added = data.get("added", 0)
                        print(f"  {tab_name}: batch {batch_num}/{total_batches} — {added} rows added.")
                        result["rows_written"] += added
                        success = True
                        break
                    else:
                        last_error = data.get("error", "unknown Apps Script error")
                        print(f"  Apps Script error ({tab_name}, batch {batch_num}, attempt {attempt}): {last_error}")
                except urllib.error.HTTPError as exc:
                    last_error = f"HTTP {exc.code}: {exc.reason}"
                    print(f"  Sheet write failed ({tab_name}, batch {batch_num}, attempt {attempt}/{max_retries}): {last_error}")
                except urllib.error.URLError as exc:
                    last_error = f"Could not reach Apps Script: {exc.reason}"
                    print(f"  Sheet write failed ({tab_name}, batch {batch_num}, attempt {attempt}/{max_retries}): {last_error}")
                except Exception as exc:
                    last_error = str(exc)
                    print(f"  Sheet write failed ({tab_name}, batch {batch_num}, attempt {attempt}/{max_retries}): {last_error}")

                if attempt < max_retries:
                    wait = SHEET_RETRY_BACKOFF_BASE ** attempt
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)

            if not success:
                failed_count = len(batch)
                result["rows_failed"] += failed_count
                result["ok"] = False
                result["errors"].append(
                    f"{tab_name} batch {batch_num}/{total_batches} ({failed_count} rows): {last_error}"
                )

            # Delay between batches to avoid overwhelming Apps Script
            if i + batch_size < len(rows):
                time.sleep(delay_between_batches)

    return result


def write_csv_fallback(items: list[ContentItem], output_path: Path) -> None:
    """Write items to local CSV files, one per tab."""
    items = [i for i in items if not i.skip_sheet_log]
    # Group by target tab
    by_tab: dict[str, list[ContentItem]] = defaultdict(list)
    for item in items:
        by_tab[item.target_tab].append(item)

    for tab_name, tab_items in by_tab.items():
        # Create tab-specific filename
        if tab_name == TAB_STORIES:
            suffix = "_stories"
            headers = SHEET_HEADERS_STORIES
        elif tab_name == TAB_VE:
            suffix = "_ve"
            headers = SHEET_HEADERS_VE
        else:
            suffix = "_pv"
            headers = SHEET_HEADERS_PV
        csv_path = output_path.parent / f"{output_path.stem}{suffix}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for item in tab_items:
                writer.writerow(item.to_row())
        print(f"  Fallback CSV written to: {csv_path}")
