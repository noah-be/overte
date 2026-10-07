#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Exercise the actual fixture handler with temporary files and loopback HTTP.

No TLS signing, laboratory services, browser, world assets or GPU are used.
"""
import hashlib
import http.client
import http.server
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.parse import quote

LAB = Path(__file__).resolve().parents[1] / "lab"
sys.path.insert(0, str(LAB))
spec = importlib.util.spec_from_file_location("https_fixture_handler", LAB / "https-fixtures.py")
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="direct-https-contract-")
        self.root = Path(self.temporary.name)
        self.assets = self.root / "assets"
        self.assets.mkdir()
        (self.assets / "actual.bin").write_bytes(b"original asset\x00\xff")
        (self.assets / "Unicode name \u00e4.bin").write_bytes(b"unicode asset")
        (self.root / "outside.bin").write_bytes(b"outside fixture must remain private")
        (self.assets / "inside.bin").symlink_to("actual.bin")
        (self.assets / "outside-link.bin").symlink_to(self.root / "outside.bin")
        (self.assets / "dangling.bin").symlink_to(self.root / "missing.bin")
        self.previous = (fixtures.DIRECTORY, fixtures.AUDIT, fixtures.ASSET_HASHES,
                         fixtures.Assets.asset_files)
        fixtures.DIRECTORY = self.assets
        fixtures.AUDIT = self.root / "requests.jsonl"
        fixtures.ASSET_HASHES = {}
        fixtures.Assets.asset_files = fixtures.asset_inventory(self.assets)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), fixtures.Assets)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)
        (fixtures.DIRECTORY, fixtures.AUDIT, fixtures.ASSET_HASHES,
         fixtures.Assets.asset_files) = self.previous
        self.temporary.cleanup()

    def request(self, path, method="GET"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        try:
            connection.request(method, path, headers={"User-Agent": "Chrome/contract"})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_exact_bytes_headers_and_audit_match_the_opened_file(self):
        for _ in range(2):
            status, headers, body = self.request("/actual.bin?ignored=query")
            self.assertEqual(status, 200)
            self.assertEqual(body, b"original asset\x00\xff")
            self.assertEqual(int(headers["Content-Length"]), len(body))
            self.assertEqual(headers["Access-Control-Allow-Origin"], fixtures.ORIGIN)
            self.assertEqual(headers["Cache-Control"], "no-store")
        records = [json.loads(line) for line in fixtures.AUDIT.read_text().splitlines()]
        self.assertEqual(len(records), 2)
        for record in records:
            self.assertEqual(record["relativePath"], "actual.bin")
            self.assertEqual(record["servedSHA256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(record["bytes"], len(body))
            self.assertEqual(record["clientClass"], "Chrome")
        self.assertEqual(fixtures.AUDIT.stat().st_mode & 0o777, 0o600)

    def test_head_and_options_preserve_the_fixture_contract(self):
        status, headers, body = self.request("/actual.bin", "HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(int(headers["Content-Length"]), len(b"original asset\x00\xff"))
        status, _, body = self.request("/actual.bin", "OPTIONS")
        self.assertEqual((status, body), (204, b""))

    def test_unicode_and_in_tree_aliases_serve_original_bytes(self):
        self.assertEqual(self.request(quote("/Unicode name \u00e4.bin"))[::2], (200, b"unicode asset"))
        self.assertEqual(self.request("/inside.bin")[::2], (200, b"original asset\x00\xff"))

    def test_traversal_absolute_and_double_encoded_names_are_unavailable(self):
        for path in ("/../outside.bin", "/%2e%2e/outside.bin", "/%2f../outside.bin",
                     "/%252e%252e/outside.bin", "//outside.bin", "/assets/../actual.bin",
                     quote(str(self.root / "outside.bin"))):
            with self.subTest(path=path):
                self.assertEqual(self.request(path)[0], 404)
        self.assertFalse(fixtures.AUDIT.exists())

    def test_bad_path_characters_are_rejected(self):
        for path in ("/actual.bin%00", "/..%5coutside.bin"):
            self.assertEqual(self.request(path)[0], 400)

    def test_outside_dangling_missing_and_directory_names_are_unavailable(self):
        for path in ("/outside-link.bin", "/dangling.bin", "/missing.bin", "/"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertFalse(fixtures.AUDIT.exists())

    def test_files_added_after_inventory_cannot_expand_request_authority(self):
        (self.assets / "late.bin").write_bytes(b"not inventoried")
        self.assertEqual(self.request("/late.bin")[0], 404)

    def test_removed_and_replaced_outside_targets_are_rechecked(self):
        (self.assets / "actual.bin").unlink()
        self.assertEqual(self.request("/actual.bin")[0], 404)
        (self.assets / "actual.bin").symlink_to(self.root / "outside.bin")
        self.assertEqual(self.request("/actual.bin")[0], 404)
        self.assertFalse(fixtures.AUDIT.exists())


if __name__ == "__main__":
    unittest.main()
