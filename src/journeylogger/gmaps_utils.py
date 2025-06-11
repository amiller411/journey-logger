import requests
from urllib.parse import urlparse, parse_qs, unquote
from .map_utils import *
import polyline
import openrouteservice
from openrouteservice import convert
from dotenv import load_dotenv
import os

load_dotenv()

# # Load your .env file
ORS_API_KEY = os.getenv("ORS_API_KEY")

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

            origin = unquote(segments[0].replace("+", " ")).strip() if len(segments) >= 1 else None
            destination = unquote(segments[1].replace("+", " ")).strip() if len(segments) >= 2 else None

            # Try to extract coordinates from @lat,lon,...
            lat_lon = None
            for segment in segments:
                if segment.startswith("@"):
                    try:
                        latlon = segment[1:].split(",")
                        lat = latlon[0]
                        lon = latlon[1]
                        lat_lon = f"{lat}, {lon}"
                        break
                    except (ValueError, IndexError):
                        continue

            return origin, lat_lon

        # Case 2: /place/<destination>
        if "/place/" in path:
            address = path.split("/place/", 1)[1].split("/")[0]
            return None, unquote(address.replace("+", " ")).strip()

        # Case 3: ?daddr=...&saddr=... from mobile Maps app
        if "daddr" in query:
            destination = unquote(query["daddr"][0])
            origin = unquote(query["saddr"][0]) if "saddr" in query else None
            
            # ensure dest is lat and long and not an address
            lat_lon_pattern = r'^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$'
            if not re.match(lat_lon_pattern, destination):
                # Call cascade function
                destination = geocode_destination(query)

            
            return origin, destination

    except Exception as e:
        print("❌ Error extracting addresses:", e)

    return None, None

# ─── FALLBACK: Geocode by Place ID ─────────────────────────────────────────────
def geocode_by_place_id(place_id: str) -> str | None:
    """
    Uses Google Geocoding API to get lat/lng from a place_id.
    Returns "lat, lon" string or None.
    """
    if not GOOGLE_API_KEY:
        raise EnvironmentError("GOOGLE_API_KEY environment variable is required")

    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"place_id": place_id, "key": GOOGLE_API_KEY},
            timeout=10
        )
        data = resp.json()
        if data.get("status") == "OK" and data.get("results"):
            loc = data["results"][0]["geometry"]["location"]
            return f"{loc['lat']}, {loc['lng']}"
    except requests.RequestException as e:
        print("❌ Error geocoding place_id:", e)
    return None

# ─── FALLBACK: Decode Encoded Polyline ───────────────────────────────────────────
def decode_polyline(poly: str) -> list[tuple[float, float]]:
    """
    Decodes a Google-encoded polyline string into a list of (lat, lon) tuples.
    """
    try:
        return polyline.decode(poly)
    except Exception as e:
        print("❌ Error decoding polyline:", e)
        return []

# ─── STUB: Decode Google geocode token (undocumented) ───────────────────────────
def decode_geocode_token(token: str) -> tuple[float, float] | None:
    """
    Placeholder for decoding Google internal geocode tokens.
    Not supported by public APIs.
    """
    print("⚠️ decode_geocode_token is not implemented")
    return None


def geocode_destination(query: dict, geonames_username: str = None):
    """
    Given the parsed mobile-Maps query, return:
      (lat, lon, town, postcode)
    or (None, None, None, None) if all fallbacks fail.
    """
    # helper to stop when we get coords
    def try_coords(fn, *args):
        try:
            return fn(*args)
        except Exception:
            return None

    full_url = query.get("_full_url")  # if you pass it in
    daddr    = query.get("daddr", [""])[0]

    # 1) your primary forward_geocode (e.g. ORS)
    coords = try_coords(forward_geocode, daddr)
    # 2) free: Nominatim
    if not coords:
        coords = try_coords(forward_geocode_nominatim, daddr)

    # 2.d try openrouteservice
    # if not coords:
    #     _, coords = get_route_coords_from_query(query)

    # 3) free: Photon
    if not coords:
        coords = try_coords(geocode_with_photon, daddr)

    # 4) pb-param scrape
    if not coords and full_url:
        coords = try_coords(extract_from_pb, full_url)

    # 5) meta‐tag scrape
    if not coords and full_url:
        coords = try_coords(scrape_meta_coords, full_url)

    # 6) Google place_id
    # if not coords and "ftid" in query:
    #     coords = try_coords(geocode_by_place_id, query["ftid"][0])

    # 7) encoded polyline
    if not coords and "g_ep" in query:
        pts = try_coords(decode_polyline, query["g_ep"][0])
        if pts:
            coords = pts[-1]

    # 8) Google internal token
    if not coords and "geocode" in query and len(query["geocode"]) > 1:
        coords = try_coords(decode_geocode_token, query["geocode"])

    # 9) free: GeoNames
    if not coords and geonames_username:
        coords = try_coords(geocode_with_geonames, daddr, geonames_username)

    # 10) region-appended fallback
    if not coords:
        coords = try_coords(forward_geocode, f"{daddr}, Northern Ireland, UK")

    if not coords:
        return None
    
    if isinstance(coords, dict):
        # If we got a dict, extract lat/lon
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat is not None and lon is not None:
            return f"{lat}, {lon}"
    
    # town, postcode = reverse_geocode(lat, lon)
    return str(coords).strip(')').strip('(').strip('[').strip(']')


def get_route_coords_from_query(query: dict) -> tuple[list[float], list[float]]:
    """
    Given a query dict from a Google Maps link,
    returns (start_coords, end_coords) in [lon, lat] format.
    """
    # Parse saddr ("lat,lon" string)
    client = openrouteservice.Client(key=ORS_API_KEY)
    try:
        lat_str, lon_str = query["saddr"][0].split(",")
        start_coords = [float(lon_str), float(lat_str)]  # ORS expects [lon, lat]
    except Exception as e:
        raise ValueError(f"Invalid saddr format: {e}")

    # Geocode daddr
    try:
        location = query["daddr"][0]
        geocode_result = client.pelias_search(text=location)
        coords = geocode_result["features"][0]["geometry"]["coordinates"]
        end_coords = [coords[0], coords[1]]  # [lon, lat]
    except Exception as e:
        raise ValueError(f"Failed to geocode daddr: {e}")

    return start_coords, end_coords