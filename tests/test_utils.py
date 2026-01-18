"""Tests for utility helpers."""

from __future__ import annotations

import unittest

from src.utils import generate_batch_id


class TestUtils(unittest.TestCase):
    def test_generate_batch_id_unique(self) -> None:
        ids = {generate_batch_id() for _ in range(100)}
        self.assertEqual(len(ids), 100)


if __name__ == "__main__":
    unittest.main()
