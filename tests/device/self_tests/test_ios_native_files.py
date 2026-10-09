"""Bounded current file reads, transport errors and handle cleanup."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios.native_files import read_file


class NativeFiles(unittest.IsolatedAsyncioTestCase):
    def files(self):
        files = AsyncMock()
        files.fopen.return_value = 42
        return files

    async def test_reads_current_bytes_without_an_outdated_size_query(self):
        files = self.files()
        files.fread.return_value = b'{"sequence":123,"newField":true}'
        self.assertEqual(await read_file(files, '/Documents/owned/probe.json', 4096), files.fread.return_value)
        files.stat.assert_not_awaited()
        files.fclose.assert_awaited_once_with(42)

    async def test_oversize_file_is_rejected_and_closed(self):
        files = self.files()
        files.fread.return_value = b'x' * 11
        with self.assertRaisesRegex(RuntimeError, 'byte bound'):
            await read_file(files, '/Documents/owned/probe.json', 10)
        files.fclose.assert_awaited_once_with(42)

    async def test_native_transport_error_is_not_treated_as_eof(self):
        files = self.files()
        files.fread.side_effect = ConnectionError('native transport failed')
        with self.assertRaises(ConnectionError):
            await read_file(files, '/Documents/owned/probe.json', 10, eof_status=14)
        files.fclose.assert_awaited_once_with(42)

    async def test_only_exact_native_eof_status_finishes_a_complete_chunk(self):
        class EndOfFile(Exception):
            status = 14
        files = self.files()
        files.fread.side_effect = [b'x' * (256 * 1024), EndOfFile()]
        self.assertEqual(len(await read_file(files, '/Documents/owned/probe.json', 300000, eof_status=14)), 256 * 1024)
        files.fclose.assert_awaited_once_with(42)

    async def test_cancelled_read_still_closes_the_owned_file(self):
        import asyncio
        files = self.files()
        files.fread.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await read_file(files, '/Documents/owned/probe.json', 10)
        files.fclose.assert_awaited_once_with(42)
