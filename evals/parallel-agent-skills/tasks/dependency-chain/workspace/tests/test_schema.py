import unittest

from src.schema import UserRecord


class SchemaTests(unittest.TestCase):
    def test_full_name_contract(self):
        self.assertEqual(UserRecord(full_name="Ada").full_name, "Ada")


if __name__ == "__main__":
    unittest.main()
