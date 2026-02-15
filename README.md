# SAT Instagram Content Archiver

CLI tool that scans SAT Daily folders, logs content metadata to Google Sheets, and moves files into organized archive folders.

## Setup

### 1. Install dependencies

```bash
cd ~/Downloads/sat-archiver
pip install -r requirements.txt
```

### 2. Google Sheets API (optional)

To log to Google Sheets:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select existing)
3. Enable **Google Sheets API** and **Google Drive API**
4. Create a **Service Account** (APIs & Services > Credentials > Create Credentials)
5. Download the JSON key file
6. Save it as `credentials/service_account.json`
7. Share your Google Sheet with the service account email (found in the JSON)
8. Copy the Sheet ID from the URL and put it in `config.json`

### 3. Configure

Edit `config.json`:
```json
{
    "sheet_id": "your-google-sheet-id-here",
    "default_initials": ""
}
```

## Usage

```bash
# Dry run against the latest SAT Daily folder
python -m sat_archiver --dry-run

# Dry run against a specific folder
python -m sat_archiver --dry-run --folder "~/Downloads/SAT Daily on 2026-01-26"

# Archive with Google Sheets logging
python -m sat_archiver --initials AK

# Archive without Google Sheets (CSV only)
python -m sat_archiver --no-sheet --initials AK
```

## Options

| Flag | Description |
|------|-------------|
| `--folder PATH` | Source folder (default: latest SAT Daily) |
| `--dry-run` | Scan only, no moves or sheet writes |
| `--sheet-id ID` | Google Sheet ID (overrides config.json) |
| `--creds PATH` | Service account key path |
| `--initials XX` | Archiver initials |
| `--no-sheet` | Skip Google Sheets, write CSV instead |

## Content Types Detected

- **Story** (Type A): Individual story files grouped by shortcode
- **Post** (Type B): Full post folders with metadata, comments, media
- **Profile** (Type D): Profile screenshot folders
- **Comment Thread** (Type D): Comment thread folders
- **Story Collection** (Type E): Named story folders

## Archive Structure

Files are moved to `~/Downloads/Instagram Archive/{username}/`.
