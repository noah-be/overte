#!/usr/bin/env python3
"""Actual HTTP/media transport checks; these are not native device evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

SERVER = Path(__file__).resolve().parents[1] / "fixture/serve.py"


class WebParityFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="overte-web-reference-")
        ready = Path(cls.temporary.name) / "ready.json"
        cls.process = subprocess.Popen([sys.executable, str(SERVER), "--ready-file", str(ready)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 5
        while not ready.exists() and cls.process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        if not ready.exists():
            cls.process.terminate()
            output = cls.process.communicate(timeout=5)
            cls.temporary.cleanup()
            raise AssertionError(f"fixture did not become ready: {output}")
        cls.ready = json.loads(ready.read_text())
        cls.media = (SERVER.parent / "parity/reference.mp4").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.communicate(timeout=5)
        cls.temporary.cleanup()

    def fetch(self, headers=None, method="GET", url=None):
        return urlopen(Request(url or self.ready["webParity"]["mediaUrl"], headers=headers or {}, method=method), timeout=3)

    def test_media_metadata_and_full_get_head_are_bound_to_actual_bytes(self):
        metadata = self.ready["webParity"]["media"]
        self.assertEqual(hashlib.sha256(self.media).hexdigest(), metadata["sha256"])
        self.assertEqual(len(self.media), metadata["bytes"])
        self.assertEqual("pending exact-artifact client observation", self.ready["webParity"]["acceptance"])
        with self.fetch() as response:
            self.assertEqual(200, response.status)
            self.assertEqual("video/mp4", response.headers["Content-Type"])
            self.assertEqual("bytes", response.headers["Accept-Ranges"])
            self.assertEqual("no-store", response.headers["Cache-Control"])
            self.assertEqual(self.media, response.read())
        with self.fetch({"Range": "bytes=0-1"}, "HEAD") as response:
            self.assertEqual(200, response.status)
            self.assertEqual(str(len(self.media)), response.headers["Content-Length"])
            self.assertIsNone(response.headers["Content-Range"])
            self.assertEqual(b"", response.read())

    def test_native_browser_single_byte_ranges_return_exact_encoded_bytes(self):
        size = len(self.media)
        for value, start, end in [("bytes=0-1", 0, 1), ("bytes=17-33", 17, 33),
                                  ("bytes=100-", 100, size - 1), ("bytes=-7", size - 7, size - 1),
                                  ("bytes=0-9999999", 0, size - 1), ("bytes=-9999999", 0, size - 1)]:
            with self.subTest(value=value), self.fetch({"Range": value}) as response:
                self.assertEqual(206, response.status)
                self.assertEqual(f"bytes {start}-{end}/{size}", response.headers["Content-Range"])
                self.assertEqual(str(end - start + 1), response.headers["Content-Length"])
                self.assertEqual(self.media[start:end + 1], response.read())

    def test_invalid_and_unsatisfiable_ranges_do_not_serve_misleading_video(self):
        for value in [f"bytes={len(self.media)}-", "bytes=20-10", "bytes=-0", "bytes=-", "items=0-1",
                      "bytes=0-1,3-4", "bytes=" + "9" * 130 + "-"]:
            with self.subTest(value=value), self.assertRaises(HTTPError) as caught:
                self.fetch({"Range": value})
            response = caught.exception
            self.assertEqual(416, response.code)
            self.assertEqual(f"bytes */{len(self.media)}", response.headers["Content-Range"])
            self.assertEqual(b"", response.read())
            response.close()

    def test_if_range_mismatch_returns_complete_representation(self):
        digest = self.ready["webParity"]["media"]["sha256"]
        with self.fetch({"Range": "bytes=0-1", "If-Range": '"different"'}) as response:
            self.assertEqual(200, response.status)
            self.assertEqual(self.media, response.read())
        with self.fetch({"Range": "bytes=0-1", "If-Range": '"' + digest + '"'}) as response:
            self.assertEqual(206, response.status)
            self.assertEqual(self.media[:2], response.read())

    def test_document_resources_are_available_and_legacy_scene_still_has_six_entities(self):
        origin = self.ready["baseUrl"]
        for resource in ("index.html", "reference.js", "injected.js", "client.js", "reference.json"):
            with self.subTest(resource=resource), self.fetch(url=origin + "/parity/" + resource) as response:
                self.assertEqual((SERVER.parent / "parity" / resource).read_bytes(), response.read())
        with self.fetch(url=self.ready["sceneUrl"]) as response:
            self.assertEqual(6, len(json.load(response)["Entities"]))


if __name__ == "__main__":
    unittest.main()
