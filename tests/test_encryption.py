"""Tests for encryption module."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.encryption import (
    calculate_hash,
    decrypt_chunk,
    decrypt_file,
    derive_key,
    encrypt_chunk,
    encrypt_file,
    generate_salt,
)


class TestEncryption(unittest.TestCase):
    def setUp(self) -> None:
        self.master_key = "V8FvyhMZVZ1s31Q0IVcqUslq-9l0j5H8y1H2QZ9JRp0="
        self.salt = generate_salt()
        self.key = derive_key(self.master_key, self.salt)

    def test_encrypt_decrypt_chunk(self) -> None:
        data = b"hello world"
        encrypted = encrypt_chunk(data, self.key)
        decrypted = decrypt_chunk(encrypted, self.key)
        self.assertEqual(data, decrypted)

    def test_encrypt_decrypt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "input.bin"
            encrypted_path = Path(temp_dir) / "encrypted.bin"
            output_path = Path(temp_dir) / "output.bin"
            input_path.write_bytes(b"a" * 1024 * 1024)
            encrypt_file(input_path, encrypted_path, self.key)
            decrypt_file(encrypted_path, output_path, self.key)
            self.assertEqual(input_path.read_bytes(), output_path.read_bytes())

    def test_calculate_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "hash.txt"
            file_path.write_text("hash-me", encoding="utf-8")
            digest = calculate_hash(file_path)
            self.assertEqual(len(digest), 64)


if __name__ == "__main__":
    unittest.main()
