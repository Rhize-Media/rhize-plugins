import unittest

from src.normalizer import normalize_phone


class PhoneTests(unittest.TestCase):
    def test_phone_keeps_digits_only(self):
        self.assertEqual(normalize_phone("+1 (615) 555-0199"), "16155550199")


if __name__ == "__main__":
    unittest.main()
