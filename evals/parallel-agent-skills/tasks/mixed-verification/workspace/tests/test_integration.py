import unittest

from src.operations import summary


class IntegrationTests(unittest.TestCase):
    def test_summary(self):
        self.assertEqual(summary("field report", 3), "Field Report: 3")


if __name__ == "__main__":
    unittest.main()
