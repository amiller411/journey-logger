import unittest
from journeylogger.map_processor import process_maps_link, get_town_from_uk_postcode

class TestProcessMapsLinkIntegration(unittest.TestCase):

    def test_link_1(self):
        url = "https://maps.app.goo.gl/LCSFDg4kzm9AhFuZA?g_st=iw"
        result = process_maps_link(url)

        self.assertIsNotNone(result)
        self.assertIn("origin", result)
        self.assertIn("destination", result)

        # Check origin fields
        origin = result["origin"]
        self.assertIsNotNone(origin.get("lat"))
        self.assertIsNotNone(origin.get("lon"))
        self.assertIsNotNone(origin.get("postcode"))

        # Check destination fields
        dest = result["destination"]
        self.assertIsNotNone(dest.get("lat"))
        self.assertIsNotNone(dest.get("lon"))
        self.assertIsNotNone(dest.get("postcode"))
        self.assertIsNotNone(dest.get("visit_type"))

        # Check distance
        self.assertIsInstance(result.get("distance_miles"), float)

    def test_link_2(self):
        url = "https://maps.app.goo.gl/tCN3sqKNpaKHHAEn8?g_st=it"
        result =  process_maps_link(url)
        self.assertIsNotNone(result)

    def test_link_3(self):
        url = "https://maps.app.goo.gl/GRkGRoWFJJ9eDm83A"
        result =  process_maps_link(url)
        self.assertIsNotNone(result)

if __name__ == "__main__":
    unittest.main()


class TestPostcodeLookup(unittest.TestCase):
    def test_known_postcode_belfast(self):
        postcode = "BT6 9QT"
        town = get_town_from_uk_postcode(postcode)
        self.assertIsNotNone(town, "Town should not be None")
        self.assertIn("Belfast", town, f"Expected 'Belfast' in result, got: {town}")

    def test_invalid_postcode(self):
        postcode = "INVALID123"
        town = get_town_from_uk_postcode(postcode)
        self.assertIsNone(town, "Invalid postcode should return None")

if __name__ == "__main__":
    unittest.main()

