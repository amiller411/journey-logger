import requests
from urllib.parse import urlparse, parse_qs, unquote

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
            return origin, destination

    except Exception as e:
        print("❌ Error extracting addresses:", e)

    return None, None