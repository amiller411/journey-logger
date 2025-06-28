import unittest
from journeylogger.map_processor import process_maps_link
import os
from pathlib import Path
from dotenv import load_dotenv

class TestAppleMapsIntegration(unittest.TestCase):
    def test_real_apple_maps_link(self):
        url = "https://maps.apple.com/?address=14%20University%20Avenue,%20Belfast,%20Northern%20Ireland"
        result = process_maps_link(url)

        # Check output structure
        self.assertIsInstance(result, dict)
        self.assertIn("origin", result)
        self.assertIn("destination", result)
        self.assertIn("distance_miles", result)

        # Check origin details
        origin = result["origin"]
        self.assertEqual(origin["town"], "Belfast")
        self.assertTrue(origin["lat"])
        self.assertTrue(origin["lon"])

        # Check destination details
        destination = result["destination"]
        self.assertEqual(destination["town"], "Belfast")
        self.assertIn("visit_type", destination)
        self.assertTrue(destination["lat"])
        self.assertTrue(destination["lon"])

        # Check distance
        self.assertIsInstance(result["distance_miles"], float)
        self.assertGreater(result["distance_miles"], 0)

if __name__ == '__main__':
    unittest.main()
