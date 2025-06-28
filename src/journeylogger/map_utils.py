import requests
import re
import os
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pathlib import Path
import json

load_dotenv()

# # Load your .env file
ORS_API_KEY = os.getenv("ORS_API_KEY")

# Load known addresses from secrets JSON
known_addresses_path = Path(__file__).parent / "secrets" / "known_addresses.json"
with open(known_addresses_path, "r", encoding="utf-8") as f:
    known_addresses = json.load(f)

def forward_geocode(address: str) -> tuple[float, float] | None:
    """
    Forward-geocodes a free-text address into (lat, lon) using OpenRouteService.
    Returns a tuple (latitude, longitude), or None if no result.
    """
    if not address:
        return None

    url = "https://api.openrouteservice.org/geocode/search"
    headers = {
        "Authorization": ORS_API_KEY,
        "Accept": "application/json"
    }
    params = {
        "api_key": ORS_API_KEY,   # some endpoints still require this in params
        "text": address,
        "size": 1                 # only need the top hit
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        features = data.get("features", [])
        if not features:
            return None

        # ORS returns coordinates as [lon, lat]
        lon, lat = features[0]["geometry"]["coordinates"]
        return lat, lon

    except requests.RequestException as e:
        print(f"❌ ORS geocoding error for '{address}':", e)
        return None

# ─── STEP 3a: Forward geocode (address → lat/lon + town + postcode) via Nominatim ─
def forward_geocode_nominatim(query_text):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query_text,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
        "countrycodes": "gb", 
        # You can optionally add an email parameter to appease Nominatim’s usage policy:
        # "email": "your_email@example.com"
    }
    headers = {
        "User-Agent": "JourneyLoggerBot/1.0 (contact: mr.milldrew@gmail.com)",
        "Referer": "https://journey-helper.local"
    }


    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)

        # 1) If status_code is not 200, print and return None
        if response.status_code != 200:
            print(f"❌ Nominatim forward‐geocode HTTP {response.status_code}: {response.text.strip()}")
            return None

        # 2) Attempt to parse JSON
        try:
            data = response.json()
        except ValueError as ve:
            print("❌ Nominatim forward‐geocode returned invalid JSON:", ve)
            print("   Raw response body:", response.text[:200])
            return None

        # 3) If the JSON is empty (no results), bail
        if not data:
            print(f"ℹ️  No forward‐geocode results for '{query_text}'.")
            return None

        # 4) Otherwise grab the first result
        result = data[0]
        address = result.get("address", {})

        # Convert string coords to float immediately
        try:
            lat_f = float(result["lat"])
            lon_f = float(result["lon"])
        except (KeyError, ValueError) as e:
            print("❌ Unexpected lat/lon format in Nominatim response:", e)
            return None

        return {
            "lat":      lat_f,
            "lon":      lon_f,
            "town":     address.get("town") or address.get("city") or address.get("village"),
            "postcode": address.get("postcode"),
            "raw":      address  # full dict of address components
        }

    except requests.RequestException as e:
        print("❌ Error in forward geocoding (network issue):", e)
        return None


# ─── STEP 3b: Reverse geocode (lat/lon → town + postcode) via Nominatim ────
def reverse_geocode(lat, lon):
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {
        "lat": lat,
        "lon": lon,
        "format": "json",
        "addressdetails": 1,
        # Optionally include your email here too:
        # "email": "your_email@example.com"
    }
    headers = {
        "User-Agent": "JourneyLoggerBot/1.0 (contact: mr.milldrew@gmail.com)",
        "Referer": "https://journey-helper.local"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)

        # 1) Check HTTP status
        if response.status_code != 200:
            print(f"❌ Nominatim reverse‐geocode HTTP {response.status_code}: {response.text.strip()}")
            return None

        # 2) Parse JSON
        try:
            data = response.json()
        except ValueError as ve:
            print("❌ Nominatim reverse‐geocode returned invalid JSON:", ve)
            print("   Raw response body:", response.text[:200])
            return None

        # 3) Extract address field if present
        address = data.get("address", {})
        if not address:
            print(f"ℹ️  No reverse‐geocode address found for {lat}, {lon}.")
            return None

        # 4) Convert lat/lon to floats
        try:
            lat_f = float(lat)
            lon_f = float(lon)
        except ValueError:
            print("❌ Invalid numeric format for lat/lon:", lat, lon)
            return None

        return {
            "lat":      lat_f,
            "lon":      lon_f,
            "town":     address.get("town") or address.get("city") or address.get("village"),
            "postcode": address.get("postcode"),
            "raw":      address  # full dict of address components
        }

    except requests.RequestException as e:
        print("❌ Error in reverse geocoding (network issue):", e)
        return None
    
def geocode_with_photon(address: str):
    """Free forward-geocode via Komoot’s Photon service."""
    url = "https://photon.komoot.io/api/"
    params = {"q": address, "limit": 1}
    r = requests.get(url, params=params, timeout=5).json()
    feats = r.get("features")
    if feats:
        lon, lat = feats[0]["geometry"]["coordinates"]
        return lat, lon
    return None

def extract_from_pb(full_url: str):
    """Pull coords from a ?pb=…!3dLAT!4dLON payload."""
    qs = parse_qs(urlparse(full_url).query)
    pb = qs.get("pb", [""])[0]
    m = re.search(r"!3d([-0-9\.]+)!4d([-0-9\.]+)", pb)
    if m:
        return float(m.group(1)), float(m.group(2))
    return None

def scrape_meta_coords(full_url: str):
    """Scrape <meta name='ICBM'> from Maps’ classic HTML."""
    r = requests.get(full_url + "&output=classic", timeout=5)
    soup = BeautifulSoup(r.text, "html.parser")
    icbm = soup.find("meta", {"name": "ICBM"})
    if icbm and "content" in icbm.attrs:
        lat, lon = map(float, icbm["content"].split(","))
        return lat, lon
    return None

def geocode_with_geonames(address: str, username: str):
    """Free forward-geocode via GeoNames (requires free signup)."""
    url = "http://api.geonames.org/searchJSON"
    params = {"q": address, "maxRows": 1, "username": username}
    r = requests.get(url, params=params, timeout=5).json()
    gn = r.get("geonames")
    if gn:
        return float(gn[0]["lat"]), float(gn[0]["lng"])
    return None

def lookup_location(value):
    if not value:
        return None

    v = value.lower()

    # Check known addresses
    for key in known_addresses:
        if key in v:
            return known_addresses[key]

    # Regex to match lat,lon (e.g. "54.58, -5.86")
    lat_lon_pattern = r'^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$'
    if "," in value:
        if re.match(lat_lon_pattern, value):
            try:
                lat_str, lon_str = value.split(",", 1)
                return reverse_geocode(lat_str.strip(), lon_str.strip())
            except Exception:
                return None
        else:
            return forward_geocode_nominatim(value)
    else:
        return forward_geocode_nominatim(value)
    
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