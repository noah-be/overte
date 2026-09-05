import hashlib
import json
import re
import tarfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MANIFEST = ROOT / "android/phone/fdroid/manifests/recipe-source.lock.json"
LOCK_DIR = ROOT / "android/phone/fdroid/locks"


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path):
    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicate_keys
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock_identity(path):
    document = load_json(path)
    for key in ("requires", "build_requires", "python_requires", "config_requires"):
        document[key] = [item.split("%", 1)[0] for item in document[key]]
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def refs(lock, context):
    return {item.split("%", 1)[0] for item in lock[context]}


class ReproducibleGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = load_json(MANIFEST)

    def test_manifest_fails_closed_and_binds_every_input(self):
        self.assertEqual(1, self.manifest["schema_version"])
        self.assertEqual("SH-001", self.manifest["node"])
        self.assertEqual(
            "IMPLEMENTATION_COMPLETE_VERIFICATION_PENDING",
            self.manifest["status"],
        )
        self.assertNotEqual("PASS", self.manifest["status"])
        self.assertEqual(0, self.manifest["cold_build"]["attempts_consumed"])
        self.assertEqual(
            "NOT_STARTED_INSUFFICIENT_DISK",
            self.manifest["cold_build"]["status"],
        )
        self.assertEqual(
            "6526387aaf7403408f148e22749c5b81",
            self.manifest["targeted_recipe_package_revisions"]
            ["gifcreator/2016.11@overte/stable"]["package_revision"],
        )
        for graph in self.manifest["graphs"].values():
            self.assertEqual(graph["lock_sha256"], digest(ROOT / graph["lock"]))
            self.assertEqual(
                graph["identity_sha256"], lock_identity(ROOT / graph["lock"])
            )
            self.assertEqual(
                graph["profile_sha256"], digest(ROOT / graph["profile"])
            )
            self.assertEqual(
                "NOT_GENERATED_COLD_BUILD_NOT_STARTED",
                graph["package_revision"],
            )
        for relative, expected in self.manifest["bound_files"].items():
            self.assertEqual(expected, digest(ROOT / relative), relative)
        bundle = self.manifest["recipe_export_bundle"]
        self.assertEqual(bundle["sha256"], digest(ROOT / bundle["path"]))

    def test_three_exact_lock_graphs_separate_host_and_target(self):
        locks = {
            path.name: load_json(path) for path in sorted(LOCK_DIR.glob("*.lock"))
        }
        self.assertEqual(
            {
                "android-arm64-v8a-api26-16k.lock",
                "bootstrap-linux-x86_64.lock",
                "host-tools-linux-x86_64.lock",
            },
            set(locks),
        )
        for lock in locks.values():
            self.assertEqual("0.5", lock["version"])
            self.assertFalse(lock["python_requires"])
            self.assertFalse(lock["config_requires"])

        bootstrap = refs(locks["bootstrap-linux-x86_64.lock"], "build_requires")
        host = refs(locks["host-tools-linux-x86_64.lock"], "requires")
        target = refs(locks["android-arm64-v8a-api26-16k.lock"], "requires")
        target_build = refs(
            locks["android-arm64-v8a-api26-16k.lock"], "build_requires"
        )
        cmake_rrev = "cmake/3.31.12#055c11ab0a919e8c6034a902b4025ce1"
        qt_rrev = (
            "qt/5.15.18-2026.01.04@overte/stable"
            "#c615fd9bf2e6410b92a3e6b84fa73980"
        )
        self.assertIn(cmake_rrev, bootstrap)
        self.assertIn(qt_rrev, host)
        self.assertIn(qt_rrev, target)
        self.assertIn(qt_rrev, target_build)
        self.assertIn(
            "openssl/3.5.8@overte/stable#33b2f0ee1a4417ab2c5429ae844d0ea5",
            target,
        )
        self.assertIn(
            "libnode/22.22.3@overte/stable#3fd33b0199406fa08037c90d5dd1a635",
            target,
        )
        for tool in ("glslang/", "scribe/", "spirv-cross/", "spirv-tools/"):
            self.assertTrue(any(ref.startswith(tool) for ref in host), tool)
            self.assertTrue(any(ref.startswith(tool) for ref in target_build), tool)
        all_refs = "\n".join(
            item for lock in locks.values() for key in ("requires", "build_requires")
            for item in lock[key]
        )
        self.assertNotIn("openssl/1.1", all_refs)
        for reference, revision in self.manifest[
            "exported_recipe_revisions"
        ].items():
            self.assertIn(f"{reference}#{revision}", all_refs, reference)

    def test_bundle_is_recipe_exports_only(self):
        bundle = ROOT / self.manifest["recipe_export_bundle"]["path"]
        with tarfile.open(bundle, "r:gz") as archive:
            names = [member.name for member in archive.getmembers()]
        conanfiles = [name for name in names if name.endswith("/e/conanfile.py")]
        self.assertEqual(51, len(conanfiles))
        self.assertFalse(
            [
                name
                for name in names
                if "p" in Path(name).parts or "s" in Path(name).parts
            ]
        )
        self.assertFalse(any(name.endswith((".a", ".so", ".dll", ".exe")) for name in names))

    def test_source_identities_match_the_bound_recipe_data(self):
        identities = self.manifest["source_identities"]
        cmake_data = (
            ROOT / "android/phone/fdroid/recipes/cmake/conandata.yml"
        ).read_text(encoding="utf-8")
        gif_data = (
            ROOT / "android/phone/fdroid/recipes/gifcreator/conandata.yml"
        ).read_text(encoding="utf-8")
        openssl_data = (
            ROOT / "android/common/conan/recipes/openssl/conandata.yml"
        ).read_text(encoding="utf-8")
        for reference in ("cmake/3.31.12", "cmake/4.4.0"):
            self.assertIn(identities[reference]["url"], cmake_data)
            self.assertIn(identities[reference]["sha256"], cmake_data)
        gif = identities["gifcreator/2016.11@overte/stable"]
        self.assertIn(gif["url"], gif_data)
        self.assertIn(gif["sha256"], gif_data)
        openssl = identities["openssl/3.5.8@overte/stable"]
        self.assertIn(openssl["url"], openssl_data)
        self.assertIn(openssl["sha256"], openssl_data)
        qt = identities["qt/5.15.18-2026.01.04@overte/stable"]
        self.assertEqual(
            qt["source_lock_sha256"],
            digest(ROOT / "android/phone/fdroid/manifests/qt-source.lock.json"),
        )
        self.assertEqual(
            qt["license_lock_sha256"],
            digest(ROOT / "android/phone/fdroid/manifests/qt-license.lock.tsv"),
        )

    def test_profiles_are_explicit_and_non_mutating(self):
        forbidden = re.compile(
            r"(?im)(profile\s+detect|mode\s*=\s*install|sudo\s*=\s*True|"
            r"--build[= ]missing|\bapt(?:-get)?\b)"
        )
        for graph in self.manifest["graphs"].values():
            text = (ROOT / graph["profile"]).read_text(encoding="utf-8")
            self.assertRegex(text, r"(?m)^include\(\.\./\.\./profiles/[^)]+\)$")
            self.assertIsNone(forbidden.search(text), graph["profile"])
            self.assertIn("tools.system.package_manager:mode=report", text)
            self.assertIn("tools.system.package_manager:sudo=False", text)

    def test_historical_locks_and_root_node_remain_untouched(self):
        historical = ROOT / "android/common/conan/locks"
        names = (
            "phone-arm64-16k-linux-x86_64.lock",
            "phone-emulator-x86_64-linux-x86_64.lock",
            "phone-nonqt-arm64-16k-linux-x86_64.lock",
            "pico4-arm64-linux-x86_64.lock",
        )
        for name in names:
            lock_path = historical / name
            self.assertIn("openssl/1.1.1q", lock_path.read_text(encoding="utf-8"))
        root_recipe = (ROOT / "conanfile.py").read_text(encoding="utf-8")
        self.assertIn("libnode/22.23.2@overte/stable", root_recipe)


if __name__ == "__main__":
    unittest.main()
