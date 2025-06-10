from journeyhelper.sheet_writer import connect_to_sheet, append_journey_to_sheet

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    # Dummy test structure
    dummy_result = {
        "origin": {
            "town": "Belfast",
            "postcode": "BT5 6FP",
            "lat": 54.58,
            "lon": -5.86,
        },
        "destination": {
            "town": "Belfast",
            "postcode": "BT9 7AB",
            "lat": 54.58,
            "lon": -5.93,
            "visit_type": "hospital"
        },
        "distance_miles": 4.32
    }

    sheet = connect_to_sheet()
    append_journey_to_sheet(sheet, dummy_result, "https://maps.app.goo.gl/abc123")
