import unittest

from src.operations import add


class MathTests(unittest.TestCase):
    def test_add(self):
        self.assertEqual(add(20, 22), 42)


if __name__ == "__main__":
    unittest.main()
