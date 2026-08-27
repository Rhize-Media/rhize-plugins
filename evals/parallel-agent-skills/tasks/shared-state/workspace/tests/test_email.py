import unittest

from src.normalizer import normalize_email


class EmailTests(unittest.TestCase):
    def test_email_is_trimmed_and_lowercase(self):
        self.assertEqual(normalize_email("  PERSON@Example.COM "), "person@example.com")


if __name__ == "__main__":
    unittest.main()
