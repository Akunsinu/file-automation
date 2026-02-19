"""Flask-based web GUI for SAT Archiver."""

from __future__ import annotations

import glob
import json
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, render_template, request

from .config import ARCHIVE_ROOT, SOURCE_GLOBS
from .main import find_latest_source_folder, load_config
from .mover import move_items
from .scanner import scan_folder
from .sheets import (
    get_existing_shortcodes,
    log_items_to_sheet,
    test_connection,
    write_csv_fallback,
)

app = Flask(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"

# Single-user local state between scan and archive
_state: dict = {
    "items": [],
    "source_folder": None,
    "apps_script_url": None,
    "existing_shortcodes": set(),
}

# All 37 sheet fields on ContentItem (for serialization)
_SHEET_FIELDS = [
    "timestamp", "shortcode", "real_name", "username", "post_type",
    "downloader", "post_date", "collaborators", "manual_notes", "db_link",
    "paired_content", "stories_reshare_links",
    "primary_beginning_tags", "secondary_beginning_tags",
    "general_triggers", "sheet_categories",
    "books", "conditions", "emotional_support", "fear", "food",
    "healing_stories", "healing_tools", "healing_tools_more",
    "history", "miscellaneous", "mm_science", "other",
    "pw_trends", "resources", "supporting",
    "mo_publication", "mo_pw", "mo_rpt", "mo_si", "mo_ts", "mo_wts",
]


def _save_config(data: dict) -> None:
    """Write config.json atomically."""
    existing = load_config(CONFIG_PATH)
    existing.update(data)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4)
        f.write("\n")


def _list_folders() -> list[dict]:
    """Return all source folders (SAT Daily + Daily MO) sorted newest-first."""
    paths = []
    for pattern in SOURCE_GLOBS:
        paths.extend(glob.glob(pattern))
    paths = sorted(paths, reverse=True)
    return [{"path": p, "name": Path(p).name} for p in paths if Path(p).is_dir()]


def _item_to_dict(item, existing_shortcodes: set) -> dict:
    """Serialize a ContentItem to a JSON-safe dict."""
    d = {}
    for field in _SHEET_FIELDS:
        d[field] = getattr(item, field, "")
    # Add internal fields useful for the UI
    d["target_tab"] = item.target_tab
    d["batch"] = item.batch
    d["wpas_code"] = item.wpas_code
    d["content_section"] = item.content_section
    d["folder_type"] = item.folder_type
    d["file_count"] = len(item.source_files)
    d["is_duplicate"] = item.shortcode in existing_shortcodes
    d["resharer_username"] = item.resharer_username
    d["resharer_name"] = item.resharer_name
    return d


@app.route("/")
def index():
    config = load_config(CONFIG_PATH)
    folders = _list_folders()
    latest = find_latest_source_folder()
    return render_template(
        "index.html",
        apps_script_url=config.get("apps_script_url", ""),
        default_initials=config.get("default_initials", ""),
        folders=folders,
        default_folder=str(latest) if latest else "",
        archive_root=str(ARCHIVE_ROOT),
    )


@app.route("/api/folders")
def api_folders():
    folders = _list_folders()
    latest = find_latest_source_folder()
    return jsonify({
        "ok": True,
        "folders": folders,
        "default": str(latest) if latest else "",
    })


@app.route("/api/settings", methods=["POST"])
def save_settings():
    data = request.get_json(silent=True) or {}
    apps_script_url = data.get("apps_script_url", "").strip()
    default_initials = data.get("default_initials", "").strip()
    _save_config({"apps_script_url": apps_script_url, "default_initials": default_initials})
    return jsonify({"ok": True, "message": "Settings saved."})


@app.route("/api/test-connection", methods=["POST"])
def api_test_connection():
    data = request.get_json(silent=True) or {}
    url = data.get("apps_script_url", "").strip()
    if not url:
        return jsonify({"ok": False, "message": "Apps Script URL is empty."}), 400

    ok_msg, err_msg = test_connection(url)
    if err_msg:
        return jsonify({"ok": False, "message": err_msg}), 400

    return jsonify({"ok": True, "message": ok_msg})


@app.route("/api/scan", methods=["POST"])
def scan():
    data = request.get_json(silent=True) or {}
    initials = data.get("initials", "").strip()
    if not initials:
        return jsonify({"ok": False, "message": "Initials are required."}), 400

    # Use explicitly selected folder, or fall back to latest
    folder_path = data.get("folder", "").strip()
    if folder_path:
        source = Path(folder_path)
        if not source.is_dir():
            return jsonify({
                "ok": False,
                "message": f"Selected folder does not exist: {folder_path}",
            }), 400
    else:
        source = find_latest_source_folder()
    if not source:
        return jsonify({
            "ok": False,
            "message": "No source folder found in ~/Downloads/",
        }), 400

    items = scan_folder(source)
    if not items:
        return jsonify({
            "ok": False,
            "message": "No content items found in source folder.",
        }), 400

    for item in items:
        if not item.downloader:
            item.downloader = initials

    # Try to fetch existing shortcodes for dedup
    config = load_config(CONFIG_PATH)
    apps_script_url = config.get("apps_script_url", "")
    existing_shortcodes: set[str] = set()

    if apps_script_url:
        existing_shortcodes = get_existing_shortcodes(apps_script_url)

    # Store state
    _state["items"] = items
    _state["source_folder"] = source
    _state["apps_script_url"] = apps_script_url
    _state["existing_shortcodes"] = existing_shortcodes

    # Build response
    type_counts: dict[str, int] = {}
    tab_counts: dict[str, int] = {}
    items_json = []
    for item in sorted(items, key=lambda i: (i.target_tab, i.content_section, i.post_type, i.username)):
        type_counts[item.post_type] = type_counts.get(item.post_type, 0) + 1
        tab_counts[item.target_tab] = tab_counts.get(item.target_tab, 0) + 1
        items_json.append(_item_to_dict(item, existing_shortcodes))

    return jsonify({
        "ok": True,
        "source_folder": str(source),
        "total": len(items),
        "duplicates": sum(1 for i in items if i.shortcode in existing_shortcodes),
        "type_counts": type_counts,
        "tab_counts": tab_counts,
        "items": items_json,
    })


@app.route("/api/update-item", methods=["POST"])
def update_item():
    """Update a single field on an in-memory ContentItem."""
    data = request.get_json(silent=True) or {}
    shortcode = data.get("shortcode", "")
    field = data.get("field", "")
    value = data.get("value", "")

    if not shortcode or not field:
        return jsonify({"ok": False, "message": "shortcode and field are required."}), 400

    # Find item by shortcode
    for item in _state["items"]:
        if item.shortcode == shortcode:
            if hasattr(item, field):
                setattr(item, field, value)
                return jsonify({"ok": True})
            return jsonify({"ok": False, "message": f"Unknown field: {field}"}), 400

    return jsonify({"ok": False, "message": f"Item not found: {shortcode}"}), 404


@app.route("/api/archive", methods=["POST"])
def archive():
    data = request.get_json(silent=True) or {}
    selected_shortcodes = set(data.get("shortcodes", []))

    if not selected_shortcodes:
        return jsonify({"ok": False, "message": "No items selected."}), 400

    if not _state["items"]:
        return jsonify({"ok": False, "message": "No scan results. Run scan first."}), 400

    # Filter to selected items
    to_archive = [i for i in _state["items"] if i.shortcode in selected_shortcodes]
    if not to_archive:
        return jsonify({"ok": False, "message": "Selected items not found in scan results."}), 400

    # Move files
    moved, move_errors = move_items(to_archive)

    # Log to sheet
    sheet_logged = False
    csv_path = None
    apps_script_url = _state.get("apps_script_url")
    if apps_script_url:
        sheet_logged = log_items_to_sheet(apps_script_url, to_archive)
        if not sheet_logged and _state["source_folder"]:
            csv_path = _state["source_folder"] / "archive_log_fallback.csv"
            write_csv_fallback(to_archive, csv_path)
    elif _state["source_folder"]:
        csv_path = _state["source_folder"] / "archive_log.csv"
        write_csv_fallback(to_archive, csv_path)

    # Clear state
    _state["items"] = []
    _state["apps_script_url"] = None
    _state["existing_shortcodes"] = set()

    return jsonify({
        "ok": True,
        "moved": moved,
        "errors": move_errors,
        "sheet_logged": sheet_logged,
        "csv_path": str(csv_path) if csv_path else None,
        "message": f"Archived {moved} items. Errors: {move_errors}."
            + (" Logged to Google Sheet." if sheet_logged else "")
            + (f" CSV written to {csv_path}." if csv_path else ""),
    })


def run_gui(host: str = "127.0.0.1", port: int = 5000) -> None:
    """Launch the Flask GUI and open the browser."""
    url = f"http://{host}:{port}"
    Timer(1.0, webbrowser.open, args=[url]).start()
    print(f"SAT Archiver GUI running at {url}")
    app.run(host=host, port=port, debug=False)
