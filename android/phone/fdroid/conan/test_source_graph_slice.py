import copy
import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "android/phone/fdroid/manifests/source-graph-slice.lock.json"
EXPECTED_REF = "openssl/3.5.8@overte/stable"
EXPECTED_URL = (
    "https://github.com/openssl/openssl/releases/download/"
    "openssl-3.5.8/openssl-3.5.8.tar.gz"
)
EXPECTED_SOURCE_SHA256 = (
    "a8f84a39918ec6415ce765d9b429d313ba97b8143169c172e734b9514464f5b2"
)


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_manifest():
    return json.loads(
        MANIFEST.read_text(encoding="utf-8"),
        object_pairs_hook=reject_duplicate_keys,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_document(document):
    assert document["schema_version"] == 1
    assert document["node"] == "SH-001"
    assert document["status"] == "IMPLEMENTATION_COMPLETE_VERIFICATION_PENDING"
    assert document["source"] == {
        "ref": EXPECTED_REF,
        "url": EXPECTED_URL,
        "sha256": EXPECTED_SOURCE_SHA256,
        "license": "Apache-2.0",
        "license_file": "LICENSE.txt",
    }
    assert document["consumer_contract"]["openssl_ref"] == EXPECTED_REF
    assert document["consumer_contract"]["root_node_22_23_2_untouched"] is True
    assert document["provider_policy"] == {
        "shared": True,
        "modules": False,
        "default_provider": "built-in",
        "fips": False,
        "openssldir": "/etc/ssl",
    }
    assert document["tool_contract"] == {
        "perl_conf": "user.overte:perl_path",
        "make_conf": "user.overte:make_path",
        "implicit_path_lookup": False,
    }
    assert document["historical_lock_disposition"] == (
        "EVIDENCE_ONLY_CONTAINS_OPENSSL_1_1_1Q_DO_NOT_EDIT"
    )
    assert len(document["required_before_pass"]) == 7


class SourceGraphSliceTest(unittest.TestCase):
    def test_manifest_and_bound_file_digests(self):
        document = load_manifest()
        validate_document(document)
        for relative, expected in document["bound_files"].items():
            self.assertEqual(expected, digest(ROOT / relative), relative)
        for relative, expected in document["historical_locks"].items():
            self.assertEqual(expected, digest(ROOT / relative), relative)

    def test_recipe_is_exact_and_source_only(self):
        recipe = (
            ROOT / "android/common/conan/recipes/openssl/conanfile.py"
        ).read_text(encoding="utf-8")
        data = (
            ROOT / "android/common/conan/recipes/openssl/conandata.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('version = "3.5.8"', recipe)
        self.assertIn('license = "Apache-2.0"', recipe)
        self.assertIn('"user.overte:perl_path"', recipe)
        self.assertIn('"user.overte:make_path"', recipe)
        self.assertIn('"no-module"', recipe)
        self.assertIn('"no-fips"', recipe)
        self.assertNotIn('"no-apps"', recipe)
        self.assertIn(EXPECTED_URL, data)
        self.assertIn(EXPECTED_SOURCE_SHA256, data)
        forbidden = re.compile(
            r"(?i)(\bcurl\b|\bwget\b|\bsudo\b|\bapt(?:-get)?\b|"
            r"profile\s+detect|--build[= ]missing|cache[ _-]?restore|artifactory)"
        )
        self.assertIsNone(forbidden.search(recipe))

    def test_smallest_android_consumers_use_exact_openssl(self):
        libnode = (
            ROOT / "android/common/conan/recipes/libnode/conanfile.py"
        ).read_text(encoding="utf-8")
        pico = (ROOT / "android/common/conan/conanfile-pico.py").read_text(
            encoding="utf-8"
        )
        root_recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
        self.assertIn(EXPECTED_REF, libnode)
        self.assertIn(EXPECTED_REF, pico)
        self.assertNotIn("openssl/1.1", libnode)
        self.assertNotIn("openssl/1.1", pico)
        self.assertIn("libnode/22.23.2@overte/stable", root_recipe)

    def test_historical_locks_remain_explicitly_unqualified(self):
        document = load_manifest()
        for relative in document["historical_locks"]:
            lock_text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("openssl/1.1.1q", lock_text)
        self.assertNotEqual(document["status"], "PASS")

    def test_tampered_manifest_fails_closed(self):
        document = load_manifest()
        altered = copy.deepcopy(document)
        altered["source"]["sha256"] = "0" * 64
        with self.assertRaises(AssertionError):
            validate_document(altered)
        altered = copy.deepcopy(document)
        altered["status"] = "PASS"
        with self.assertRaises(AssertionError):
            validate_document(altered)


if __name__ == "__main__":
    unittest.main()
