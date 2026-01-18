"""Tests for file processing utilities."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from src.file_processor import (
    calculate_file_hash,
    create_archive,
    extract_archive,
    merge_chunks,
    scan_path,
    split_file,
)


class TestFileProcessing(unittest.TestCase):
    def test_scan_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            file_a = base / "a.txt"
            file_b = base / "nested" / "b.txt"
            file_b.parent.mkdir(parents=True, exist_ok=True)
            file_a.write_text("hello", encoding="utf-8")
            file_b.write_text("world", encoding="utf-8")

            files = scan_path(base)
            self.assertEqual(len(files), 2)

            archive = base / "archive.tar.gz"
            create_archive(files, archive)
            extract_dir = base / "extract"
            extract_archive(archive, extract_dir)

            self.assertTrue((extract_dir / "a.txt").exists())
            self.assertTrue((extract_dir / "nested" / "b.txt").exists())

    def test_split_and_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            file_path = base / "data.bin"
            original = b"x" * 1024 * 1024
            file_path.write_bytes(original)

            chunk_paths = asyncio.run(split_file(file_path, 128 * 1024))
            merged = base / "merged.bin"
            asyncio.run(merge_chunks(chunk_paths, merged))

            self.assertEqual(original, merged.read_bytes())

    def test_calculate_file_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "hash.bin"
            file_path.write_bytes(b"hash")
            digest = asyncio.run(calculate_file_hash(file_path))
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
