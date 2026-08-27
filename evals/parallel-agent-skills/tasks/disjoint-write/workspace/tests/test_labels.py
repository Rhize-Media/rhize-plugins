import unittest

from src.labels import slugify


class LabelTests(unittest.TestCase):
    def test_slug_normalization(self):
        self.assertEqual(slugify("  Priority   Client  "), "priority-client")


if __name__ == "__main__":
    unittest.main()
