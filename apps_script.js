/**
 * SAT Archiver — Google Apps Script Web App
 *
 * Setup:
 *   1. Open your Google Sheet
 *   2. Extensions > Apps Script
 *   3. Paste this entire file, replacing any existing code
 *   4. Click Deploy > New deployment
 *   5. Type: Web app, Execute as: Me, Who has access: Anyone
 *   6. Copy the URL and paste it into SAT Archiver settings
 *
 * Sheet must have two tabs: "Stories" and "P&V Manual Backup"
 */

// Headers are sent per-tab from Python (SHEET_HEADERS_STORIES / SHEET_HEADERS_PV).
// These defaults are used only as fallback if payload.headers is missing.
var HEADERS_STORIES = [
  "timestamp", "shortcode", "real_name", "username", "post_type",
  "downloader", "post_date", "collaborators", "manual notes", "DB Link",
  "paired content", "stories reshare links",
  "Primary Beginning Tags", "Secondary Beginning Tags", "General Triggers",
  "Sheet Categories", "Projects", "Books", "Original Audio", "Food",
  "Healing Stories", "Healing Stories Exception", "Healing Tools",
  "Healing Tools More", "Miscellaneous", "Other", "Pets", "Resources",
  "Special", "Special Occasions", "Spiritual", "Supporting",
  "MO - Publication", "MO - PW", "MO - RPT", "MO - SI", "MO - TS", "MO - WTS"
];

var HEADERS_PV = [
  "timestamp", "shortcode", "url", "real_name", "username", "post_type",
  "media_count", "comment_count", "caption_preview",
  "downloader", "post_date", "collaborators", "manual notes", "DB Link",
  "paired content",
  "Primary Beginning Tags", "Secondary Beginning Tags", "General Triggers",
  "Sheet Categories", "Projects", "Books", "Original Audio", "Food",
  "Healing Stories", "Healing Stories Exception", "Healing Tools",
  "Healing Tools More", "Miscellaneous", "Other", "Pets", "Resources",
  "Special", "Special Occasions", "Spiritual", "Supporting",
  "MO - Publication", "MO - PW", "MO - RPT", "MO - SI", "MO - TS", "MO - WTS"
];

var TAB_STORIES = "Stories";
var TAB_PV_MANUAL = "P&V Manual Backup";

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || "test";
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  if (action === "test") {
    var counts = {};
    var tabs = [TAB_STORIES, TAB_PV_MANUAL];
    var totalCount = 0;
    for (var t = 0; t < tabs.length; t++) {
      var sheet = ss.getSheetByName(tabs[t]);
      if (sheet) {
        var lastRow = sheet.getLastRow();
        var count = lastRow > 1 ? lastRow - 1 : 0;
        counts[tabs[t]] = count;
        totalCount += count;
      }
    }
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, count: totalCount, counts: counts }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (action === "shortcodes") {
    // Read shortcodes from column B (Shortcode) across BOTH tabs
    var shortcodes = [];
    var tabs = [TAB_STORIES, TAB_PV_MANUAL];
    for (var t = 0; t < tabs.length; t++) {
      var sheet = ss.getSheetByName(tabs[t]);
      if (!sheet) continue;
      var lastRow = sheet.getLastRow();
      if (lastRow > 1) {
        var values = sheet.getRange(2, 2, lastRow - 1, 1).getValues(); // column B
        for (var i = 0; i < values.length; i++) {
          var v = values[i][0];
          if (v) shortcodes.push(String(v));
        }
      }
    }
    return ContentService
      .createTextOutput(JSON.stringify({ shortcodes: shortcodes }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService
    .createTextOutput(JSON.stringify({ error: "Unknown action: " + action }))
    .setMimeType(ContentService.MimeType.JSON);
}

function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents);
    var tabName = payload.tab || TAB_STORIES;
    var defaultHeaders = (tabName === TAB_PV_MANUAL) ? HEADERS_PV : HEADERS_STORIES;
    var headers = payload.headers || defaultHeaders;
    var rows = payload.rows || [];

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(tabName);

    if (!sheet) {
      // Create the tab if it doesn't exist
      sheet = ss.insertSheet(tabName);
    }

    // Ensure header row
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(headers);
    } else {
      var existing = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
      var needsUpdate = false;
      for (var i = 0; i < headers.length; i++) {
        if (existing[i] !== headers[i]) { needsUpdate = true; break; }
      }
      if (needsUpdate) {
        sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      }
    }

    // Append rows
    if (rows.length > 0) {
      sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
    }

    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, added: rows.length, tab: tabName }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
