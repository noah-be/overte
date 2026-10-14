"""Production LOD startup/setters and real typed handles across process restarts.

The asynchronous Setting::Manager and display rate endpoints are explicit host
boundaries. This does not establish an SDK build or physical rendering evidence.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_login_dialog_domain_receiver import block

ROOT = Path(__file__).resolve().parents[4]


class LodPreferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="overte-lod-preferences-")
        cls.scratch = Path(cls.temp.name)
        relative = "interface/src/LODManager.cpp"
        baseline = os.environ.get("OVERTE_LOD_PREFERENCES_BASELINE")
        source = subprocess.check_output(["git", "show", baseline + ":" + relative], cwd=ROOT, text=True) if baseline else (ROOT / relative).read_text()
        header = (ROOT / "interface/src/LODManager.h").read_text()
        constants = (ROOT / "libraries/octree/src/OctreeConstants.h").read_text()
        utils = (ROOT / "libraries/octree/src/OctreeUtils.cpp").read_text()
        declarations = header[header.index("enum WorldDetailQuality {"):header.index("const float LOD_OFFSET_FPS")]
        for name in ("DEFAULT_VISIBILITY_DISTANCE_FOR_UNIT_ELEMENT", "UNIT_ELEMENT_MAX_EXTENT"):
            declarations += next(line for line in constants.splitlines() if line.startswith("const float " + name + " ")) + "\n"
        declarations += block(utils, "float getHalfAngleFromVisibilityDistance(") + "\n"
        start = source.index("const QString LOD_SETTINGS_PREFIX")
        declarations += source[start:source.index("LODManager::LODManager()", start)]
        (cls.scratch / "lod-declarations.inc").write_text(declarations)
        (cls.scratch / "lod-methods.inc").write_text("\n".join(block(source, signature) for signature in (
            "void LODManager::loadSettings(", "void LODManager::saveSettings(",
            "void LODManager::setAutomaticLODAdjust(", "void LODManager::setLODAngleDeg(",
            "void LODManager::setWorldDetailQuality(WorldDetailQuality quality, bool")))
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        glm_include = os.environ.get("OVERTE_TEST_GLM_INCLUDE")
        if glm_include:
            if not (Path(glm_include) / "glm/glm.hpp").is_file():
                raise RuntimeError("The explicit GLM include directory is incomplete")
            flags.append("-I" + glm_include)
        cls.binaries = {}
        for platform in ("IOS", "PHONE", "PICO", "DESKTOP"):
            binary = cls.scratch / ("lod-" + platform.lower() + "-test")
            compiled = subprocess.run(["c++", "-std=c++17", "-fPIC", "-pthread", "-DTEST_" + platform,
                "-I" + str(ROOT), "-I" + str(cls.scratch),
                str(Path(__file__).with_name("lod-preferences-test.cpp")), "-o", str(binary), *flags], capture_output=True, text=True, timeout=45)
            if compiled.returncode:
                raise RuntimeError("LOD host compilation failed:\n" + compiled.stderr[:6000])
            cls.binaries[platform] = binary

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def fresh(self):
        temp = tempfile.TemporaryDirectory(prefix="overte-lod-store-")
        self.addCleanup(temp.cleanup)
        return Path(temp.name) / "settings.ini"

    def invoke(self, platform, file, action="startup", *args):
        result = subprocess.run([str(self.binaries[platform]), str(file), action, *args],
            check=True, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)

    def test_only_touch_platforms_get_conservative_unset_defaults(self):
        for platform in self.binaries:
            with self.subTest(platform=platform):
                result = self.invoke(platform, self.fresh())
                self.assertEqual(result["automatic"], platform not in ("IOS", "PHONE"))
                expected = 0.248 if platform in ("IOS", "PHONE") else result["nativeDefaultAngle"]
                self.assertAlmostEqual(result["angle"], expected, places=5)
                self.assertFalse(result["storedAutomatic"])
                self.assertFalse(result["storedAngle"])
                self.assertEqual(result["desktopQuality"], 0 if platform in ("PHONE", "PICO") else 1)
                self.assertEqual(result["hmdQuality"], result["desktopQuality"])

    def test_user_changes_and_changes_back_survive_separate_processes(self):
        for platform in self.binaries:
            file = self.fresh()
            self.invoke(platform, file, "save")
            for automatic, angle in (("true", "0.9"), ("false", "0.16"), ("true", "0.248")):
                with self.subTest(platform=platform, automatic=automatic, angle=angle):
                    selected = self.invoke(platform, file, "user", automatic, angle)
                    self.assertEqual(selected["notifications"], 1)
                    for _ in range(2):
                        restarted = self.invoke(platform, file)
                        self.assertEqual(restarted["automatic"], automatic == "true")
                        self.assertAlmostEqual(restarted["angle"], float(angle), places=5)
                        self.assertTrue(restarted["storedAutomatic"])
                        self.assertTrue(restarted["storedAngle"])

    def test_partial_preferences_default_only_the_missing_key(self):
        for platform in ("IOS", "PHONE"):
            automatic = self.fresh()
            automatic.write_text("[lodManager]\nautomaticLODAdjust=true\n")
            result = self.invoke(platform, automatic)
            self.assertTrue(result["automatic"])
            self.assertAlmostEqual(result["angle"], 0.248, places=5)
            angle = self.fresh()
            angle.write_text("[lodManager]\nlodHalfAngle=0.009\n")
            result = self.invoke(platform, angle)
            self.assertFalse(result["automatic"])
            self.assertAlmostEqual(result["angle"], 1.031324, places=5)

    def test_legacy_mobile_profile_is_preserved(self):
        for platform in ("IOS", "PHONE"):
            file = self.fresh()
            self.invoke(platform, file, "user", "false", "0.248")
            result = self.invoke(platform, file)
            self.assertFalse(result["automatic"])
            self.assertAlmostEqual(result["angle"], 0.248, places=5)


if __name__ == "__main__":
    unittest.main()
