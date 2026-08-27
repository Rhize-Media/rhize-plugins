import unittest

from src.pricing import discounted_total


class PricingTests(unittest.TestCase):
    def test_percentage_discount(self):
        self.assertEqual(discounted_total(200, 15), 170.0)


if __name__ == "__main__":
    unittest.main()
