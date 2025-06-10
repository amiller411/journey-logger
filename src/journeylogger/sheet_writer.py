# sheet_writer.py

import os
import gspread
from datetime import datetime
from zoneinfo import ZoneInfo
from oauth2client.service_account import ServiceAccountCredentials

# ─── Configurable Constants ─────────────────────────────────────────────────────

SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
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
