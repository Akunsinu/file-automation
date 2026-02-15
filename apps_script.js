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
 */

// Must match SHEET_HEADERS in config.py
var HEADERS = [
  "Shortcode",
  "Username",
  "Full Name",
  "Content Type",
  "Category",
  "WPAS Code",
  "Date Posted",
  "Media Type",
  "Like Count",
  "Comment Count",
  "Caption",
  "Post URL",
  "Batch",
  "Section",
  "Archiver Initials",
  "Archive Date",
  "Destination Path"
];

function doGet(e) {
  var action = (e && e.parameter && e.parameter.action) || "test";
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

  if (action === "test") {
    var lastRow = sheet.getLastRow();
    var count = lastRow > 1 ? lastRow - 1 : 0; // exclude header
    return ContentService
      .createTextOutput(JSON.stringify({ ok: true, count: count }))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (action === "shortcodes") {
    var shortcodes = [];
    var lastRow = sheet.getLastRow();
    if (lastRow > 1) {
      var values = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (var i = 0; i < values.length; i++) {
        var v = values[i][0];
        if (v) shortcodes.push(String(v));
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
    var headers = payload.headers || HEADERS;
    var rows = payload.rows || [];

    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();

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
      .createTextOutput(JSON.stringify({ ok: true, added: rows.length }))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService
      .createTextOutput(JSON.stringify({ ok: false, error: err.toString() }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
