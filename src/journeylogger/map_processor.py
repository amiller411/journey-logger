import os
import requests
import re
import sys
import time
from dotenv import load_dotenv
import json
from pathlib import Path

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


# ─── CORE FUNCTION: process_maps_link ──────────────────────────────────────────
def process_maps_link(short_url):
    """
    Given a Google Maps short link, returns a dict with:
      - origin: { raw, lat, lon, town, postcode }
      - destination: { raw, lat, lon, town, postcode, visit_type }
      - distance_miles: float or None
    """
    # 1) Expand the short link
    full_url = expand_google_maps_url(short_url)
    if not full_url:
        return None

    # 2) Parse origin + destination strings
    origin_str, destination_str = extract_addresses_from_gmaps_url(full_url)

    # 3) Geocode origin
    origin_info = lookup_location(origin_str)

    # 4) Geocode destination (prefer embedded lat/lon if available)
    
    # if dest_lat and dest_lon:
    destination_info = lookup_location(destination_str)
    # else:
    #     full_url_dest = full_url.strip(origin_info['lat'])
    #     full_url_dest = full_url_dest.strip(origin_info['lon'])
    #     dest_lat, dest_lon = extract_lat_lon_from_url(full_url_dest)
    #     destination_info = reverse_geocode(dest_lat, dest_lon)
        

    # 5) Classify the visit type
    dest_raw_dict = destination_info.get("raw", {}) if destination_info else {}
    dest_full_text = " ".join(dest_raw_dict.values()).strip()
    visit_type = classify_visit_type(dest_full_text)

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


def get_town_from_uk_postcode(postcode):
    try:
        url = f"https://api.postcodes.io/postcodes/{postcode}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if data.get("status") != 200:
            return None

        result = data.get("result", {})
        return result.get("admin_district") or result.get("parish") or result.get("admin_ward")
    except Exception as e:
        print(f"Error fetching town for postcode {postcode}: {e}")
        return None



# ─── If run as a script, prompt for input and print output ────────────────────
if __name__ == "__main__":
    short_url = input("Paste Google Maps short link: ").strip()

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
