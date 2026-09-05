from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
SCRIPT = Path(__file__).with_name("qt_source_store.py")
MANIFEST = ROOT / "android/phone/fdroid/manifests/qt-source.lock.json"
WRAPPER = ROOT / "android/phone/fdroid/scripts/prepare-sources.sh"
SPEC = importlib.util.spec_from_file_location("qt_source_store", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def archive_bytes(top: str, payload: bytes = b"source\n") -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        member = tarfile.TarInfo(f"{top}/payload.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    return buffer.getvalue()


def write_fixture_manifest(path: Path, source_store: Path) -> dict:
    document = MODULE.load_manifest(MANIFEST)
    for index, component in enumerate(document["components"]):
        payload = archive_bytes(component["id"], f"source-{index}\n".encode())
        digest = hashlib.sha256(payload).hexdigest()
        component["sha256"] = digest
        component["store_name"] = f"{digest}.tar.gz"
        (source_store / component["store_name"]).write_bytes(payload)
    path.write_text(json.dumps(document), encoding="utf-8")
    return document


class QtSourceStoreTest(unittest.TestCase):
    def test_real_manifest_is_exact_and_scanner_pending(self):
        document = MODULE.load_manifest(MANIFEST)
        self.assertEqual(17, len(document["components"]))
        self.assertEqual(
            MODULE.EXPECTED_COMPONENTS,
            {item["id"]: item["destination"] for item in document["components"]},
        )
        self.assertEqual(
            "SOURCE_AND_LICENSE_ARCHIVES_LOCKED_ATTRIBUTION_SCANNER_PENDING",
            document["status"],
        )
        self.assertEqual(4, len(document["qualification_blocks"]))

    def test_manifest_tampering_fails_closed(self):
        document = MODULE.load_manifest(MANIFEST)
        cases = []
        altered = copy.deepcopy(document)
        altered["status"] = "PASS"
        cases.append(altered)
        altered = copy.deepcopy(document)
        altered["components"][0]["sha256"] = "0" * 64
        cases.append(altered)
        altered = copy.deepcopy(document)
        altered["components"][0]["canonical_url"] = "https://example.invalid/source"
        cases.append(altered)
        altered = copy.deepcopy(document)
        altered["components"][1]["id"] = "qtwebengine"
        cases.append(altered)
        altered = copy.deepcopy(document)
        altered["archive_limits"]["max_archive_bytes"] = 0
        cases.append(altered)
        for case in cases:
            with self.subTest(case=case["status"]):
                with self.assertRaises(MODULE.SourceStoreError):
                    MODULE.validate_manifest(case)

    def test_duplicate_json_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.SourceStoreError, "duplicate JSON key"):
                MODULE.load_manifest(path)

    def test_archive_traversal_and_escaping_symlink_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            traversal = root / "traversal.tar.gz"
            with tarfile.open(traversal, mode="w:gz") as archive:
                member = tarfile.TarInfo("top/../../escape")
                member.size = 1
                archive.addfile(member, io.BytesIO(b"x"))
            with self.assertRaisesRegex(MODULE.SourceStoreError, "unsafe archive path"):
                MODULE.extract_archive(traversal, root / "out-a", 1)

            symlink = root / "symlink.tar.gz"
            with tarfile.open(symlink, mode="w:gz") as archive:
                member = tarfile.TarInfo("top/link")
                member.type = tarfile.SYMTYPE
                member.linkname = "../../outside"
                archive.addfile(member)
            with self.assertRaisesRegex(MODULE.SourceStoreError, "escaping archive link"):
                MODULE.extract_archive(symlink, root / "out-b", 1)

            duplicate = root / "duplicate.tar.gz"
            with tarfile.open(duplicate, mode="w:gz") as archive:
                for value in (b"a", b"b"):
                    member = tarfile.TarInfo("top/same")
                    member.size = 1
                    archive.addfile(member, io.BytesIO(value))
            with self.assertRaisesRegex(MODULE.SourceStoreError, "duplicate archive path"):
                MODULE.extract_archive(duplicate, root / "out-c", 1)

            sized = root / "sized.tar.gz"
            sized.write_bytes(archive_bytes("top", b"large"))
            with self.assertRaisesRegex(MODULE.SourceStoreError, "unpacked-size"):
                MODULE.extract_archive(sized, root / "out-d", 1, max_unpacked_bytes=1)

    def test_compose_verifies_all_inputs_and_attests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_store = root / "store"
            source_store.mkdir()
            manifest = root / "manifest.json"
            document = write_fixture_manifest(manifest, source_store)
            output = root / "composed"
            result = MODULE.compose(manifest, source_store, output)
            self.assertEqual(17, result["component_count"])
            self.assertEqual(
                "COMPOSED_SOURCE_AND_LICENSE_LOCKED_ATTRIBUTION_SCANNER_PENDING",
                result["status"],
            )
            self.assertEqual(
                "73112c92373d338b14a8f1e88691d6d3e185f75ec8abe6cb0dee2fec55336474",
                result["license_lock_sha256"],
            )
            self.assertTrue((output / "qt5/qtbase/payload.txt").is_file())
            self.assertTrue(
                (
                    output
                    / "qt5/qtlocation/src/3rdparty/mapbox-gl-native/payload.txt"
                ).is_file()
            )
            attestation = json.loads(
                (output / "COMPOSITION.json").read_text(encoding="utf-8")
            )
            self.assertEqual(result, attestation)
            self.assertEqual(
                {item["id"] for item in document["components"]},
                set(attestation["component_sha256"]),
            )
            self.assertEqual(
                MODULE.EXPECTED_TOP_LEVEL_DIRECTORIES,
                {
                    path.name
                    for path in (output / "qt5").iterdir()
                    if path.is_dir()
                },
            )

    def test_unselected_superproject_directories_are_pruned(self):
        with tempfile.TemporaryDirectory() as temporary:
            qt_root = Path(temporary) / "qt5"
            (qt_root / "qtbase").mkdir(parents=True)
            (qt_root / "qtwebengine").mkdir()
            (qt_root / "qtwebengine/source").write_text("forbidden", encoding="utf-8")
            (qt_root / "coin").mkdir()
            removed = MODULE.prune_unselected_top_level(qt_root)
            self.assertEqual(["coin", "qtwebengine"], removed)
            self.assertTrue((qt_root / "qtbase").is_dir())
            self.assertFalse((qt_root / "qtwebengine").exists())

    def test_missing_tampered_source_and_existing_output_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_store = root / "store"
            source_store.mkdir()
            manifest = root / "manifest.json"
            document = write_fixture_manifest(manifest, source_store)
            first = source_store / document["components"][0]["store_name"]
            first.write_bytes(b"tampered")
            with self.assertRaisesRegex(MODULE.SourceStoreError, "digest mismatch"):
                MODULE.compose(manifest, source_store, root / "output-a")
            first.unlink()
            with self.assertRaisesRegex(MODULE.SourceStoreError, "source missing"):
                MODULE.compose(manifest, source_store, root / "output-b")
            existing = root / "output-c"
            existing.mkdir()
            with self.assertRaisesRegex(MODULE.SourceStoreError, "already exists"):
                MODULE.compose(manifest, source_store, existing)

    def test_wrapper_has_no_implicit_source_or_network_path(self):
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("OVERTE_SOURCE_STORE", text)
        self.assertIn("OVERTE_QT_SOURCE_ROOT", text)
        for forbidden in ("curl", "wget", "git clone", "profile detect", "--build=missing"):
            self.assertNotIn(forbidden, text.lower())
        self.assertTrue(os.stat(WRAPPER).st_mode & 0o111)


if __name__ == "__main__":
    unittest.main()
