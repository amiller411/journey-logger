import os
import requests
import re
import sys
import time
from dotenv import load_dotenv
import json
import pandas as pd
from typing import Optional, Tuple, List, Dict
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from journeylogger.map_utils import reverse_geocode, get_town_from_uk_postcode, make_empty_location_dict

from .sheet_writer import connect_to_sheet

sheet = connect_to_sheet()

# ─── Figure out which .env to load ─────────────────────────────────────────────
# Grab the script that kicked everything off:
entry_script = Path(sys.argv[0]).name

# Define where your env files live (adjust as needed):
root = Path(__file__).resolve().parent.parent.parent
dev_env  = root / ".env.development"
prod_env = root / ".env.production"   # if your production entry-point really is named __main__.py…

# Pick the file: if the launcher is "__main__.py" use prod, else dev
env_path = prod_env if entry_script == "__main__.py" else dev_env

# Finally load it:
load_dotenv(dotenv_path=env_path)

# ─── Now pull in your keys ───────────────────────────────────────────────────────
ORS_API_KEY    = os.getenv("ORS_API_KEY")
NOMINATUM_AGENT = os.getenv("NOMINATUM_AGENT")

from .map_utils import lookup_location
from .gmaps_utils import expand_google_maps_url, extract_addresses_from_gmaps_url

# Load known addresses JSON
addresses_path = Path(__file__).parent.parent / "journeylogger" / "secrets" / "addresses.json"

try:
    with open(addresses_path, "r", encoding="utf-8") as f:
        known_addresses = json.load(f)
except Exception as e:
    print(f"⚠️ Failed to load known addresses: {e}")
    known_addresses = {
        "home": [],
        "depot": []
    }


# load towns data
towns_data_path = Path(__file__).parent.parent.parent / "resources" / "data" / "towns.csv"
df_towns = pd.read_csv(towns_data_path)

# Clean settlement names: remove bracketed footnotes like [c], [e], etc.
df_towns["settlement"] = df_towns["settlement"].str.replace(r"\[.*?\]", "", regex=True).str.strip()

# Clean classification field: strip quotes and whitespace
df_towns["classification"] = df_towns["classification"].str.replace(r"['\"]", "", regex=True).str.strip()

# Define the classification priority mapping
classification_priority = {
    "small town": 1,
    "medium town": 2,
    "large town": 3,
    "small village or hamlet": 4,
    "village": 5,
    "intermediate settlement": 6
}

# Normalize and map classifications
df_towns["classification_lower"] = df_towns["classification"].str.lower().map(classification_priority)

# Drop rows that aren't part of our priority set
df_cleaned = df_towns.dropna(subset=["classification_lower"])

# Build a list of (settlement, priority)
settlement_priority = sorted(
    zip(df_cleaned["settlement"], df_cleaned["classification_lower"]),
    key=lambda x: x[1]  # sort by priority
)

# ——— UK postcode pattern (very common case) ———
# Compile postcode regex for NI format (BTxx xxx)
postcode_re = re.compile(r"\bBT\d{1,2}\s?\d[A-Z]{2}\b", re.IGNORECASE)

# Prepare list of settlements sorted by priority
ordered_settlements = [s for s, _ in settlement_priority]

def parse_address(dest_str: str) -> Tuple[Optional[str], Optional[str], Optional[str], List[str]]:
    """
    Parse an address string and extract street, primary town, postcode, and other candidate towns.

    The primary town is selected based on the global 'ordered_settlements' priority list.
    Any additional matches are returned as 'other_towns'.

    Args:
        dest_str (str): The full address string to parse.

    Returns:
        Tuple containing:
            - street (Optional[str]): The street component, if detectable.
            - town (Optional[str]): The highest-priority matched town.
            - postcode (Optional[str]): The extracted postcode in uppercase, if any.
            - other_towns (List[str]): Other matched towns, ordered by descending priority.
    """
    s = dest_str.strip()
    postcode: Optional[str] = None
    street: Optional[str] = None
    town: Optional[str] = None
    other_towns: List[str] = []

    # 1) Extract postcode
    pc_match = postcode_re.search(s)
    if pc_match:
        postcode = pc_match.group(0).upper()
        s = s[:pc_match.start()].rstrip(', ').strip()

    # 2) Split into parts
    parts = [p.strip() for p in s.split(',') if p.strip()]
    if not parts:
        return None, None, postcode, other_towns

    # 3) Find matching settlements
    raw_matches: List[str] = []
    for sett in ordered_settlements:
        # compile a pattern like r'\bMaghera\b'
        pattern = re.compile(rf"\b{re.escape(sett)}\b", re.IGNORECASE)
        if any(pattern.search(part) for part in parts):
            raw_matches.append(sett)

    # Deduplicate while preserving order
    matches = list(dict.fromkeys(raw_matches))

    if matches:
        town = matches[0]
        other_towns = matches[1:]
        # Determine street as first component before primary town
        for idx, part in enumerate(parts):
            if town.lower() in part.lower():
                if idx > 0:
                    street = parts[0]
                break
    else:
        # Fallback: use second component as town if available
        if len(parts) > 1:
            street, town = parts[0], parts[1]
        else:
            street = parts[0]

    return street, town, postcode, other_towns

# ─── STEP 5: Pull destination's embedded lat/lon from the full URL ─────────────
def extract_lat_lon_from_url(full_url):
    # look for !1d<lon>!2d<lat> pattern
    match = re.search(r"!1d(-?\d+\.\d+)!2d(-?\d+\.\d+)", full_url)
    if match:
        lon = match.group(1)
        lat = match.group(2)
        return lat, lon
    return None, None


# ─── STEP 6: Classify the visit type based on known‐location rules ────────────
def classify_visit_type(address_string):
    addr = (address_string or "").lower()

    # Check for home
    if any(home in addr for home in known_addresses.get("home", [])):
        if "19" in addr:
            return "home"

    # Check for hospital
    if "hospital" in addr:
        return "hospital"

    # Check for depot
    if any(depot in addr for depot in known_addresses.get("depot", [])):
        return "depot"

    return "visit"


# ─── STEP 7: Get driving‐route distance from OpenRouteService ──────────────────
def get_route_distance_via_ors(lat1, lon1, lat2, lon2, api_key):
    url = "https://api.openrouteservice.org/v2/directions/driving-car"
    headers = {
        "Authorization": api_key,
        "Content-Type": "application/json"
    }
    body = {
        "coordinates": [
            [float(lon1), float(lat1)],
            [float(lon2), float(lat2)]
        ]
    }

    try:
        time.sleep(1)  # Rate limit: ORS allows 1 request per second for free tier
        response = requests.post(url, headers=headers, json=body, timeout=10)
        if response.status_code != 200:
            print("❌ ORS API error:", response.status_code)
            print("Message:", response.text)
            return None

        data = response.json()
        # In the v2/directions JSON, distance is under routes[0].summary.distance
        meters = data["routes"][0]["summary"]["distance"]
        miles = meters / 1609.344
        return miles

    except Exception as e:
        print("❌ ORS request failed:", e)
        return None
    

def parse_apple_maps_url(url: str):
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    # Prefer saddr/daddr if present, else fallback to 'address' or 'q'
    origin = query.get("saddr", [None])[0]
    destination = query.get("daddr", [None])[0] or query.get("address", [None])[0] or query.get("q", [None])[0]

    return {
        "origin_str": origin,
        "destination_str": destination,
        "latlon": query.get("ll", [None])[0],
    }


# ─── CORE FUNCTION: process_maps_link ──────────────────────────────────────────
def process_maps_link(short_url):
    """
    Given a Google Maps short link, returns a dict with:
      - origin: { raw, lat, lon, town, postcode }
      - destination: { raw, lat, lon, town, postcode, visit_type }
      - distance_miles: float or None
    """
    # 1) Expand the short link
    if short_url.startswith("https://maps.app.goo.gl/"):
        full_url = expand_google_maps_url(short_url)
        if not full_url:
            return None

        # 2) Parse origin + destination strings
        origin_str, destination_str = extract_addresses_from_gmaps_url(full_url)

    elif short_url.startswith("https://maps.apple.com/"):
        full_url = short_url  # Apple links aren't usually shortened
        parsed = parse_apple_maps_url(full_url)
        origin_str = parsed["origin_str"]
        destination_str = parsed["destination_str"]

        # Fallback: use latlon if destination_str is missing
        if not destination_str and parsed["latlon"]:
            lat_str, lon_str = parsed["latlon"].split(",")
            destination_info = reverse_geocode(float(lat_str), float(lon_str))
            destination_str = destination_info.get("raw", {}).get("road")  # fallback raw text
        else:
            destination_info = None  # will be set later via lookup_location
            

    else:
        return None  # Unsupported link
    
    last_url_parsed = None

    if not origin_str:
        # Get current calendar day
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/London"))
        current_day = now.strftime("%d %B %Y")

        # 2) Pull all rows and filter to today’s entries
        #    (requires sheet = connect_to_sheet() in scope)
        records = sheet.get_all_records()
        todays = []
        for r in records:
            if r.get("Calendar Day", "").lower() == current_day.lower():
                todays.append(r)


        if todays:
            # 3a) Use the last logged destination as your new origin
            last = todays[-1]
            town = last.get("Destination Town")
            postcode = last.get("Destination Postcode")
            last_url = last.get("Raw URL")
            last_url_parsed = parse_apple_maps_url(last_url)

            if town and postcode:
            # TODO handle if previous day has a blank destination, defaults to home currently
                origin_str = f"{town}, {postcode}"
            else:
                # missing data – fall back to home
                origin_str = known_addresses["home"][0]
        else:
            # 3b) First journey of the day – start from home
            origin_str = known_addresses["home"][0]


    # 3) Geocode origin
    origin_info = lookup_location(origin_str)
    
    # handle case where previous destination is somewhere where the intial village
    # can't be forward geocoded but valid lat/lon is available. This could result in
    # a large milage discrepancy and the origin post code for the current entry will
    # not match the previous destination post code.
    if last_url_parsed and last_url_parsed.get("latlon"):
        lat_str, lon_str = last_url_parsed["latlon"].split(",")

        coords_differ = (
            origin_info is None or
            origin_info.get("lat") != lat_str or
            origin_info.get("lon") != lon_str
        )

        if coords_differ:
            origin_info = {
                "lat": lat_str,
                "lon": lon_str,
                "postcode": postcode or "",
            }


    # 4) Geocode destination (prefer embedded lat/lon if available)
    
    # if dest_lat and dest_lon:
    destination_info = lookup_location(destination_str)

    if not destination_info:
        destination_info = make_empty_location_dict()

    # check fields against what can be parsed from the dest str
    parsed_addr, parsed_town, parsed_postcode, other_towns = parse_address(destination_str)
    
    # Trust the parsed address over any forward geocoded options, won't align precisely with 
    # co-ordinates which are only used for distance calculation
    if parsed_addr:
        if destination_info["town"] != parsed_town:
            destination_info["town"] = parsed_town
    if parsed_postcode:
        if destination_info["postcode"] != parsed_postcode:
            destination_info["postcode"] = parsed_postcode
    if parsed_addr:
        if destination_info["raw"].get("road") != parsed_addr:
            destination_info["raw"]["road"] = parsed_addr
        
    # attempt to get lat and lon again
    if destination_info["lat"] == '' or destination_info["lon"] == '':
        towns_only = f"{other_towns}, {parsed_town}" if parsed_town else ""
        cleaned_towns = towns_only.replace("[", "").replace("]", "").replace("'", "")
        retry_dest_info = lookup_location(cleaned_towns)
        if retry_dest_info:
            destination_info["lat"] = retry_dest_info["lat"]
            destination_info["lon"] = retry_dest_info["lon"]
        else:
            # try again with just the larger nearest town
            retry_dest_info = lookup_location(parsed_town)
            if retry_dest_info:
                destination_info["lat"] = retry_dest_info["lat"]
                destination_info["lon"] = retry_dest_info["lon"]
            else:
                # set lat lon to none
                destination_info["lat"] = None
                destination_info["lon"] = None


    # 5) Classify the visit type
    dest_raw_dict = destination_info.get("raw", {}) if destination_info else {}
    dest_full_text = " ".join(dest_raw_dict.values()).strip()
    visit_type_full = classify_visit_type(dest_full_text)
    visit_type_str = classify_visit_type(destination_str)

    if visit_type_full != 'visit' and visit_type_str == 'visit':
        visit_type = visit_type_full
    elif visit_type_full == 'visit' and visit_type_str != 'visit':
        visit_type = visit_type_str
    else:
        visit_type = visit_type_full

    # 6) Compute driving‐route distance via ORS
    distance_miles = None
    if origin_info and destination_info and ORS_API_KEY:
        distance_miles = get_route_distance_via_ors(
            origin_info["lat"],
            origin_info["lon"],
            destination_info["lat"],
            destination_info["lon"],
            ORS_API_KEY
        )

    # 7) Build the result dict
    result = {
        "origin": {
            "raw":      origin_str,
            "lat":      origin_info.get("lat")      if origin_info else None,
            "lon":      origin_info.get("lon")      if origin_info else None,
            "town":     origin_info.get("town")     if origin_info else None,
            "postcode": origin_info.get("postcode") if origin_info else None,
        },
        "destination": {
            "raw":       destination_str,
            "lat":       destination_info.get("lat")      if destination_info else None,
            "lon":       destination_info.get("lon")      if destination_info else None,
            "town":      destination_info.get("town")     if destination_info else None,
            "postcode":  destination_info.get("postcode") if destination_info else None,
            "visit_type": visit_type,
        },
        "distance_miles": distance_miles
    }

    # Town check
    if result["origin"]["town"] is None:
        result["origin"]["town"] = get_town_from_uk_postcode(result["origin"]["postcode"])
    if result["destination"]["town"] is None:
        result["destination"]["town"] = get_town_from_uk_postcode(result["destination"]["postcode"])

    return result


# ─── If run as a script, prompt for input and print output ────────────────────
if __name__ == "__main__":
    short_url = input("Paste Maps link: ").strip()

    result = process_maps_link(short_url)
    if not result:
        print("❌ Failed to process the link.")
        exit()

    # Print expanded URL, origin, and destination strings
    full_url = expand_google_maps_url(short_url)
    origin_str, destination_str = extract_addresses_from_gmaps_url(full_url)
    print("\nExpanded URL:", full_url)
    print("Origin:     ", origin_str)
    print("Destination:", destination_str)

    # Print origin info
    origin_info = result["origin"]
    if origin_info and origin_info["lat"] and origin_info["lon"]:
        print("\n✅ Origin Info:")
        print("  Town:     ", origin_info.get("town"))
        print("  Postcode: ", origin_info.get("postcode"))
        print("  Lat/Lon:  ", origin_info.get("lat"), origin_info.get("lon"))
    else:
        print("\n❌ Could not resolve origin info.")

    # Print destination info
    destination_info = result["destination"]
    if destination_info and destination_info["lat"] and destination_info["lon"]:
        print("\n✅ Destination Info:")
        print("  Town:       ", destination_info.get("town"))
        print("  Postcode:   ", destination_info.get("postcode"))
        print("  Lat/Lon:    ", destination_info.get("lat"), destination_info.get("lon"))
        print("  Visit Type: ", destination_info.get("visit_type"))
    else:
        print("\n❌ Could not resolve destination info.")

    # Print distance
    if result.get("distance_miles") is not None:
        print(f"\n🛣️ Road Distance (ORS): {result['distance_miles']:.2f} miles")

    # Print the raw result dict for inspection
    print("\n── RESULT DICT ──────────────────────────────────────")
    print(result)

