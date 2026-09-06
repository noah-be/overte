import copy
import hashlib
import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT = Path(__file__).with_name("source_closure_store.py")
SPEC = importlib.util.spec_from_file_location("source_closure_store", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceClosureStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "locks").mkdir()
        (self.root / "recipes/demo/1.0").mkdir(parents=True)
        self.recipe = self.root / "recipes/demo/1.0/conanfile.py"
        self.recipe.write_text("license = 'MIT'\n", encoding="utf-8")
        self.rrev = "1" * 32
        self.lock = self.root / "locks/target.lock"
        self.lock.write_text(json.dumps({
            "version": "0.5",
            "requires": [f"demo/1.0#{self.rrev}%1"],
            "build_requires": [], "python_requires": [], "config_requires": [],
        }), encoding="utf-8")
        self.archive = self.root / "demo.zip"
        with zipfile.ZipFile(self.archive, "w") as output:
            output.writestr("demo-1.0/LICENSE", "fixture MIT license\n")
            output.writestr("demo-1.0/source.c", "int answer = 42;\n")
        archive_sha = MODULE.sha256_file(self.archive)
        license_sha = hashlib.sha256(b"fixture MIT license\n").hexdigest()
        self.index = self.root / "recipe-index.json"
        self.index.write_text('{"schema_version":1}\n', encoding="utf-8")
        self.pkglist = self.root / "pkglist.json"
        self.pkglist.write_text('{}\n', encoding="utf-8")
        self.toolchain = self.root / "toolchain.json"
        self.toolchain.write_text('{"schema":1}\n', encoding="utf-8")
        self.document = {
            "schema_version": 1, "node": "TEST", "node_count": 1,
            "recipe_export_index": {
                "path": self.index.name, "sha256": MODULE.sha256_file(self.index),
                "pkglist_path": self.pkglist.name,
                "pkglist_sha256": MODULE.sha256_file(self.pkglist),
            },
            "toolchain_binding": {
                "path": self.toolchain.name,
                "sha256": MODULE.sha256_file(self.toolchain),
            },
            "graphs": {"target": {"path": "locks/target.lock", "sha256": MODULE.sha256_file(self.lock)}},
            "nodes": [{
                "reference": "demo/1.0", "recipe_revision": self.rrev,
                "classification": "source-bearing",
                "contexts": [{"graph": "target", "role": "requires"}],
                "lineage": {"direct_dependencies": [], "graph_roots": ["target"]},
                "recipe": {
                    "path": "recipes/demo/1.0/conanfile.py", "sha256": MODULE.sha256_file(self.recipe),
                    "exported_files": {"recipes/demo/1.0/conanfile.py": MODULE.sha256_file(self.recipe)},
                },
                "sources": [{
                    "id": "demo/1.0", "retrieval": "https-archive",
                    "canonical_url": "https://example.org/demo-1.0.zip", "immutable_ref": "v1.0",
                    "sha256": archive_sha, "max_bytes": 1024 * 1024, "archive_format": "zip",
                    "strip_components": 1,
                    "store_path": f"objects/sha256/{archive_sha[:2]}/{archive_sha}",
                    "approved_redirect_hosts": ["example.org"],
                    "license": {
                        "spdx": "MIT", "public_source": "https://example.org/demo-1.0.zip#LICENSE",
                        "path": "LICENSE", "sha256": license_sha,
                    },
                    "redistribution": "allowed-foss-source", "fdroid_exception": "none",
                }],
            }],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def write_manifest(self, document=None):
        path = self.root / "source-closure.json"
        path.write_text(json.dumps(document or self.document), encoding="utf-8")
        return path

    def test_positive_manifest_acquire_resume_verify_and_stage(self):
        manifest = self.write_manifest()
        document = MODULE.validate_manifest(manifest, self.root)
        store = self.root / "store"
        (store / ".staging").mkdir(parents=True)
        source = document["nodes"][0]["sources"][0]
        (store / ".staging" / f"{source['sha256']}.part").write_bytes(self.archive.read_bytes())
        first = MODULE.acquire(document, store)
        self.assertEqual("ACQUIRED_VERIFIED", first[0]["state"])
        second = MODULE.acquire(document, store)
        self.assertEqual("REUSED_VERIFIED", second[0]["state"])
        self.assertEqual(1, len(MODULE.verify(document, store)))
        destination = self.root / "conan-download-cache"
        MODULE.stage_conan_cache(document, store, destination)
        self.assertTrue((destination / "s" / source["sha256"]).is_file())

    def test_missing_entry_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["nodes"] = []
        document["node_count"] = 0
        with self.assertRaises(MODULE.ClosureError):
            MODULE.validate_manifest(self.write_manifest(document), self.root)

    def test_extra_graph_node_is_rejected(self):
        document = copy.deepcopy(self.document)
        extra = copy.deepcopy(document["nodes"][0])
        extra["reference"] = "foreign/9"
        extra["recipe_revision"] = "2" * 32
        document["nodes"].append(extra)
        document["node_count"] = 2
        with self.assertRaises(MODULE.ClosureError):
            MODULE.validate_manifest(self.write_manifest(document), self.root)

    def test_host_target_context_leakage_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["nodes"][0]["contexts"][0]["graph"] = "host-tools"
        with self.assertRaisesRegex(MODULE.ClosureError, "host-target"):
            MODULE.validate_manifest(self.write_manifest(document), self.root)

    def test_mutable_ref_is_rejected(self):
        document = copy.deepcopy(self.document)
        document["nodes"][0]["sources"][0]["immutable_ref"] = "main"
        with self.assertRaisesRegex(MODULE.ClosureError, "mutable"):
            MODULE.validate_manifest(self.write_manifest(document), self.root)

    def test_bad_archive_hash_is_rejected(self):
        source = copy.deepcopy(self.document["nodes"][0]["sources"][0])
        source["sha256"] = "f" * 64
        with self.assertRaisesRegex(MODULE.ClosureError, "source digest"):
            MODULE._verify_one(self.archive, source)

    def test_wrong_license_identity_is_rejected(self):
        source = copy.deepcopy(self.document["nodes"][0]["sources"][0])
        source["license"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(MODULE.ClosureError, "license digest"):
            MODULE._verify_one(self.archive, source)

    def test_unapproved_redirect_is_rejected(self):
        handler = MODULE._AllowlistedRedirect(["example.org"])
        with self.assertRaisesRegex(MODULE.ClosureError, "not approved"):
            handler.redirect_request(None, None, 302, "Found", {}, "https://evil.invalid/payload")

    def test_partial_and_offline_incomplete_store_are_rejected(self):
        document = MODULE.validate_manifest(self.write_manifest(), self.root)
        store = self.root / "partial-store"
        source = document["nodes"][0]["sources"][0]
        object_dir = store / source["store_path"]
        object_dir.mkdir(parents=True)
        (object_dir / "source").write_bytes(self.archive.read_bytes()[:10])
        with self.assertRaisesRegex(MODULE.ClosureError, "incomplete"):
            MODULE.verify(document, store)

    def test_nonempty_stage_destination_is_rejected(self):
        document = MODULE.validate_manifest(self.write_manifest(), self.root)
        destination = self.root / "not-empty"
        destination.mkdir()
        (destination / "foreign").write_text("binary", encoding="utf-8")
        with self.assertRaises(MODULE.ClosureError):
            MODULE.stage_conan_cache(document, self.root / "absent", destination)


if __name__ == "__main__":
    unittest.main()
