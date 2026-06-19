import unittest
import os
import json
from scraper import MedofastScraper

class TestScraper(unittest.TestCase):
    def test_settings_initialization(self):
        scraper = MedofastScraper()
        self.assertEqual(scraper.click_delay, 2.0)
        self.assertFalse(scraper.skip_explanation)

    def test_pause_resume(self):
        scraper = MedofastScraper()
        # New implementation uses is_paused boolean
        self.assertFalse(scraper.is_paused)
        scraper.pause()
        self.assertTrue(scraper.is_paused)
        scraper.resume()
        self.assertFalse(scraper.is_paused)

    def test_stop(self):
        scraper = MedofastScraper()
        self.assertFalse(scraper.is_stopped)
        scraper.stop()
        self.assertTrue(scraper.is_stopped)

if __name__ == "__main__":
    unittest.main()
