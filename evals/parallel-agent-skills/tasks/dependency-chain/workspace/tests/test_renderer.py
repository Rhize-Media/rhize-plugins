import unittest

from src.renderer import render_user
from src.schema import UserRecord


class RendererTests(unittest.TestCase):
    def test_renderer_uses_full_name(self):
        self.assertEqual(render_user(UserRecord(full_name="Ada")), "User: Ada")


if __name__ == "__main__":
    unittest.main()
