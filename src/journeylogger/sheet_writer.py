# sheet_writer.py

import os
from pathlib import Path
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo
from oauth2client.service_account import ServiceAccountCredentials
from .map_processor import process_maps_link
from dotenv import load_dotenv

# ─── Configurable Constants ─────────────────────────────────────────────────────

root = Path(__file__).resolve().parent.parent.parent
env_file = root / ".env.production"
load_dotenv(env_file)

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
DEFAULT_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# ─── Setup Connection to Google Sheet ───────────────────────────────────────────

def connect_to_sheet(sheet_id: str = DEFAULT_SHEET_ID):
    if not os.path.exists(SERVICE_ACCOUNT_FILE):
        raise FileNotFoundError(f"Service account file not found: {SERVICE_ACCOUNT_FILE}")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id).sheet1  # or use .worksheet("Sheet1") for named tabs

# ─── Append a Single Row of Journey Data ────────────────────────────────────────

def append_journey_to_sheet(sheet, result_dict, short_url: str, timestamp: datetime | None = None, note=""):
    """
    Appends one row to the sheet with structure:
    Processed Timestamp, Calendar Day, Journey Type, Origin Town, Origin Postcode,
    Destination Town, Destination Postcode, Estimated Mileage (ORS), Raw URL, Notes
    """
    origin = result_dict["origin"]
    dest = result_dict["destination"]
    distance = result_dict.get("distance_miles")

    # Use now if no timestamp provided
    timestamp = timestamp or datetime.now(ZoneInfo("Europe/London"))

    processed_str = timestamp.strftime("%d %B %Y, %H:%M %Z")
    calendar_day_str = timestamp.strftime("%d %B %Y")

    row = [
        processed_str,                     # Processed Timestamp
        calendar_day_str,                 # Calendar Day
        dest.get("visit_type", ""),       # Journey Type
        origin.get("town", ""),           # Origin Town
        origin.get("postcode", ""),       # Origin Postcode
        dest.get("town", ""),             # Destination Town
        dest.get("postcode", ""),         # Destination Postcode
        f"{distance:.2f}" if distance else "",  # Estimated Mileage (ORS)
        short_url,                        # Raw URL
        note,                               # Notes (can be edited manually later)
    ]

    try:
        sheet.append_row(row)
        print("✅ Row appended to Google Sheet.")
    except Exception as e:
        print("❌ Failed to append to Google Sheet:", e)


def process_and_log_journey(short_url: str, timestamp=None) -> dict:
    """Expands URL, parses it, logs it to the Google Sheet, and returns result dict."""
    result = process_maps_link(short_url)
    if not result:
        raise ValueError("Failed to parse short_url")

    if not timestamp:
        timestamp = datetime.now(ZoneInfo("Europe/London"))

    sheet = connect_to_sheet()
    append_journey_to_sheet(sheet, result, short_url=short_url, timestamp=timestamp)

    return result


def get_all_records(sheet, header_row: int = 1, default_blank: str = "") -> list[dict]:
    """
    Fetch all rows from the given gspread Worksheet as a list of dicts,
    using the specified header_row for column names.

    Args:
        sheet: gspread.models.Worksheet instance
        header_row: 1-indexed row number containing your column headers
        default_blank: value to substitute for empty cells

    Returns:
        List of dicts, one per data row, mapping header → cell value.
    """
    # 1) pull all rows as lists of strings
    all_values = sheet.get_all_values()

    # 2) ensure we have at least the header
    if len(all_values) < header_row:
        return []

    # 3) extract headers
    headers = all_values[header_row - 1]

    # 4) build list of record-dicts
    records = []
    for row in all_values[header_row:]:
        # pad/truncate row to match headers length
        row_extended = (row + [default_blank] * len(headers))[: len(headers)]
        record = {
            headers[i]: (cell if cell != "" else default_blank)
            for i, cell in enumerate(row_extended)
        }
        records.append(record)

    return records

