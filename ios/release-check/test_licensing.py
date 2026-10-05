"""Regression boundaries for stale or incomplete attribution evidence."""
# SPDX-License-Identifier: Apache-2.0
import unittest
from licensing import attribution_problems, is_license_file, ASSET_SUFFIXES


class AttributionTests(unittest.TestCase):
    def setUp(self):
        self.hashes = {"font.ttf": "a" * 64, "font-OFL.txt": "b" * 64}
        self.record = dict(sha256="a" * 64, license="OFL-1.1", source="tracked-source-reference",
                           copyright="Fixture font authors", noticeFile="font-OFL.txt", noticeSha256="b" * 64)

    def test_asset_and_notice_both_bind_evidence(self):
        self.assertEqual(attribution_problems(self.record, "font.ttf", self.hashes), [])
        self.hashes["font.ttf"] = "c" * 64
        self.assertIn("missing-or-stale-asset-hash", attribution_problems(self.record, "font.ttf", self.hashes))

    def test_changed_notice_requires_new_review(self):
        self.hashes["font-OFL.txt"] = "c" * 64
        self.assertIn("missing-or-stale-notice-hash", attribution_problems(self.record, "font.ttf", self.hashes))

    def test_missing_asset_cannot_pass_with_two_missing_hashes(self):
        self.record.pop("sha256")
        self.assertIn("missing-or-stale-asset-hash", attribution_problems(self.record, "missing.ttf", self.hashes))

    def test_unknown_copyright_and_untracked_notice_do_not_pass(self):
        self.record.update(copyright="UNKNOWN", noticeFile="outside-the-inventory")
        issues = attribution_problems(self.record, "font.ttf", self.hashes)
        self.assertIn("missing-copyright", issues)
        self.assertIn("missing-tracked-notice", issues)

    def test_font_and_media_coverage(self):
        self.assertTrue(is_license_file("CourierPrime-OFL.txt"))
        self.assertFalse(is_license_file("glow.frag"))
        self.assertTrue({".arfont", ".woff", ".woff2", ".mp4", ".ktx2"} <= ASSET_SUFFIXES)


if __name__ == "__main__":
    unittest.main()
