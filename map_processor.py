import os
import requests
import re
from urllib.parse import urlparse, unquote, parse_qs
from dotenv import load_dotenv
from map_utils import lookup_location, reverse_geocode

# ─── Load ORS API key from .env ────────────────────────────────────────────────
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")  # put your OpenRouteService key in a .env file


# ─── STEP 1: Expand the short Google Maps URL ──────────────────────────────────
def expand_google_maps_url(short_url):
    try:
        response = requests.get(short_url, allow_redirects=True, timeout=10)
        final_url = response.url

        # Handle Google consent redirect
        if "consent.google.com" in final_url:
            query = urlparse(final_url).query
            params = parse_qs(query)
            if "continue" in params:
                return unquote(params["continue"][0])
        
        # Return final resolved Google Maps URL
        return final_url

    except requests.RequestException as e:
        print("❌ Error expanding URL:", e)
        return None



# ─── STEP 2: Extract origin + destination from a /dir/ or /place/ URL ──────────
def extract_addresses_from_gmaps_url(full_url):
    try:
        parts = urlparse(full_url)
        path = parts.path
        query = parse_qs(parts.query)

        # Case 1: /dir/<origin>/<destination>
        if "/dir/" in path:
            segments = path.split("/dir/", 1)[1].split("/")
            if len(segments) >= 2:
                origin = unquote(segments[0].replace("+", " ")).strip()
                destination = unquote(segments[1].replace("+", " ")).strip()
                return origin, destination

        # Case 2: /place/<destination>
        if "/place/" in path:
            address = path.split("/place/", 1)[1].split("/")[0]
            return None, unquote(address.replace("+", " ")).strip()

        # ✅ Case 3: ?daddr=...&saddr=... from mobile Maps app
        if "daddr" in query:
            destination = unquote(query["daddr"][0])
            origin = unquote(query["saddr"][0]) if "saddr" in query else None
            return origin, destination

    except Exception as e:
        print("❌ Error extracting addresses:", e)

    return None, None

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

    # Home address rule
    if "19 knock green" in addr:
        return "home"
    
    if "knock gr" in addr and "19" in addr:
        return "home"

    # Any hospital
    if "hospital" in addr:
        return "hospital"

    # Sciensus depot in Belfast
    if (
        "holly business park" in addr 
        or "bt11 9dt" in addr 
        or "kennedy way industrial estate" in addr
        or "kennedy way" in addr
        or "bt11 9aj" in addr
        or "holly business park" in addr):

        return "depot"

    # Default → generic visit
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

    return result


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
