import unittest
from journeyhelper.gmaps_utils import expand_google_maps_url, extract_addresses_from_gmaps_url

class TestGoogleMapsIntegration(unittest.TestCase):

    def test_expand_and_extract_link_1(self):
        short_url = "https://maps.app.goo.gl/LCSFDg4kzm9AhFuZA?g_st=iw"
        full_url = expand_google_maps_url(short_url)
        self.assertIsNotNone(full_url)
        origin, destination = extract_addresses_from_gmaps_url(full_url)
        self.assertIsNotNone(origin)
        self.assertIsNotNone(destination)
        print("\n[1] Origin:", origin)
        print("[1] Destination:", destination)

    def test_expand_and_extract_link_2(self):
        short_url = "https://maps.app.goo.gl/tCN3sqKNpaKHHAEn8?g_st=it"
        full_url = expand_google_maps_url(short_url)
        self.assertIsNotNone(full_url)
        origin, destination = extract_addresses_from_gmaps_url(full_url)
        self.assertIsNotNone(origin)
        self.assertIsNotNone(destination)
        print("\n[2] Origin:", origin)
        print("[2] Destination:", destination)

    def test_expand_and_extract_link_3(self):
        short_url = "https://maps.app.goo.gl/GRkGRoWFJJ9eDm83A"
        full_url = expand_google_maps_url(short_url)
        self.assertIsNotNone(full_url)
        origin, destination = extract_addresses_from_gmaps_url(full_url)
        self.assertIsNotNone(origin)
        self.assertIsNotNone(destination)
        print("\n[3] Origin:", origin)
        print("[3] Destination:", destination)

if __name__ == "__main__":
    unittest.main()
