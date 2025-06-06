import requests
import re


# ─── STEP 3a: Forward geocode (address → lat/lon + town + postcode) via Nominatim ─
# ─── STEP 3b: Reverse geocode (lat/lon → town + postcode) via Nominatim ────

# ─── STEP 4: Helper if string is "lat,lon" vs full address ────────────────────


import requests

# ─── STEP 3a: Forward geocode (address → lat/lon + town + postcode) via Nominatim ─
def forward_geocode(query_text):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": query_text,
        "format": "json",
        "addressdetails": 1,
        "limit": 1,
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

    
def lookup_location(value):
    if not value:
        return None
    
    v = value.lower()

    # ─── Hardcoded: 19 Knock Green ───────────────
    if ("19 knock green" in v
        or "knock g" in v):
        return {
            "lat": 54.5834046,  # ← Your known coordinates
            "lon": -5.8651469,
            "town": "Belfast",
            "postcode": "BT5 6GJ",  # Or correct code if known
            "raw": {
                "road": "Knock Green",
                "house_number": "19",
                "town": "Belfast",
                "postcode": "BT5 6GJ"
            }
        }

    # ─── Hardcoded: Belfast City Hospital ────────
    if "belfast city hospital" in v:
        return {
            "lat": 54.58749533497572,
            "lon": -5.940873568556854,
            "town": "Belfast",
            "postcode": "BT9 7AB",
            "raw": {
                "amenity": "Hospital",
                "name": "Belfast City Hospital",
                "town": "Belfast",
                "postcode": "BT9 7AB"
            }
        }

    # ─── Hardcoded: Royal Victoria Hospital ──────
    if "royal victoria hospital" in v:
        return {
            "lat": 54.594631442237734,
            "lon": -5.954465146216176,
            "town": "Belfast",
            "postcode": "BT12 6BA",
            "raw": {
                "amenity": "Hospital",
                "name": "Royal Victoria Hospital",
                "town": "Belfast",
                "postcode": "BT12 6BA"
            }
        }

    # Regex to match a numeric “lat,lon” pair (e.g. “54.58, -5.86”)
    lat_lon_pattern = r'^\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*$'

    if "," in value:
        # If it matches the lat,lon pattern exactly → reverse‐geocode
        if re.match(lat_lon_pattern, value):
            try:
                lat_str, lon_str = value.split(",", 1)
                return reverse_geocode(lat_str.strip(), lon_str.strip())
            except Exception:
                return None
        # Otherwise it’s just an address string containing a comma → forward‐geocode
        return forward_geocode(value)
    else:
        return forward_geocode(value)
