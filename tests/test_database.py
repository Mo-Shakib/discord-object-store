"""Tests for database module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src import database


class TestDatabaseOperations(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        database.init_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _sample_batch(self) -> dict:
        return {
            "batch_id": "BATCH_20260118_ABCD",
            "original_path": "/tmp/data",
            "original_name": "data",
            "total_size": 1024,
            "compressed_size": 512,
            "chunk_count": 2,
            "file_count": 1,
            "encryption_salt": "salt",
            "is_directory": 1,
            "title": "My Batch",
            "tags": "tag1, tag2",
            "description": "Sample description",
            "status": "complete",
            "archive_message_id": "123",
            "thread_id": "456",
        }

    def _sample_chunk(self) -> dict:
        return {
            "chunk_id": "chunk_0",
            "batch_id": "BATCH_20260118_ABCD",
            "chunk_index": 0,
            "discord_message_id": "msg1",
            "discord_attachment_url": "https://example.com/chunk",
            "file_hash": "hash",
            "size": 256,
        }

    def test_create_and_get_batch(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        batch = database.get_batch("BATCH_20260118_ABCD", self.db_path)
        self.assertIsNotNone(batch)
        self.assertEqual(batch["original_name"], "data")

    def test_add_and_get_chunks(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        database.add_chunk(self._sample_chunk(), self.db_path)
        chunks = database.get_chunks("BATCH_20260118_ABCD", self.db_path)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["chunk_index"], 0)

    def test_update_batch_status(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        database.update_batch_status(
            "BATCH_20260118_ABCD", "failed", self.db_path)
        batch = database.get_batch("BATCH_20260118_ABCD", self.db_path)
        self.assertEqual(batch["status"], "failed")

    def test_list_batches(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        batches = database.list_batches(self.db_path)
        self.assertEqual(len(batches), 1)

    def test_get_storage_stats(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        stats = database.get_storage_stats(self.db_path)
        self.assertEqual(stats["batch_count"], 1)
        self.assertEqual(stats["total_size"], 1024)

    def test_delete_batch(self) -> None:
        database.create_batch(self._sample_batch(), self.db_path)
        database.delete_batch("BATCH_20260118_ABCD", self.db_path)
        batch = database.get_batch("BATCH_20260118_ABCD", self.db_path)
        self.assertIsNone(batch)


if __name__ == "__main__":
    unittest.main()
