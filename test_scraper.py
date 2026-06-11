import unittest
import os
import json
from scraper import MedofastScraper

class TestScraper(unittest.TestCase):
    def test_settings_initialization(self):
        scraper = MedofastScraper()
        # Updated default values in scraper.py
        self.assertEqual(scraper.click_delay, 2.0)
        self.assertFalse(scraper.skip_explanation)

    def test_pause_resume(self):
        scraper = MedofastScraper()
        self.assertTrue(scraper.pause_event.is_set())
        scraper.pause()
        self.assertFalse(scraper.pause_event.is_set())
        scraper.resume()
        self.assertTrue(scraper.pause_event.is_set())

    def test_stop(self):
        scraper = MedofastScraper()
        self.assertFalse(scraper.is_stopped)
        scraper.stop()
        self.assertTrue(scraper.is_stopped)
        self.assertTrue(scraper.pause_event.is_set())

if __name__ == "__main__":
    unittest.main()
