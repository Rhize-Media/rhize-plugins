import unittest

from src.operations import headline


class TextTests(unittest.TestCase):
    def test_headline(self):
        self.assertEqual(headline("  field report "), "Field Report")


if __name__ == "__main__":
    unittest.main()
