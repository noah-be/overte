import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
LOADER = ROOT / "android/common/libraries/qt/src/main/java/org/qtproject/qt5/android/bindings/QtActivityLoader.java"
PHONE_GRADLE = ROOT / "android/phone/apps/phoneInterface/build.gradle"
QT_GRADLE = ROOT / "android/common/libraries/qt/build.gradle"


class QtBundledLoaderPolicyTest(unittest.TestCase):
    def test_loader_uses_only_the_application_class_loader(self):
        source = LOADER.read_text(encoding="utf-8")
        self.assertIn("ClassLoader classLoader = m_context.getClassLoader();", source)
        self.assertIn("classLoader.loadClass(loaderClassName())", source)
        self.assertNotRegex(source, r"(?i)\bdex\.path\b|\bDexClassLoader\b|\boutdex\b")
        self.assertNotIn("getStringExtra(\"dex", source)

    def test_external_or_writable_executable_path_api_is_absent(self):
        source = LOADER.read_text(encoding="utf-8")
        implementation = source.split("*/", 1)[1]
        forbidden = (
            "PathClassLoader", "InMemoryDexClassLoader", "BaseDexClassLoader",
            "loadDex", "getExternalFilesDir", "getExternalStorageDirectory",
            "http://", "https://", "file://",
        )
        for token in forbidden:
            self.assertNotIn(token, implementation, token)
        # The only reflective loader target is the fixed bundled Qt delegate.
        self.assertEqual(1, len(re.findall(r"classLoader\.loadClass\(", source)))
        self.assertIn('return "org.qtproject.qt5.android.QtActivityDelegate";', source)

    def test_qt_java_and_jar_inputs_are_packaged_by_gradle(self):
        phone = PHONE_GRADLE.read_text(encoding="utf-8")
        qt = QT_GRADLE.read_text(encoding="utf-8")
        self.assertIn("java.srcDir '../../../common/libraries/qt/src/main/java'", phone)
        self.assertIn("implementation fileTree", phone)
        self.assertIn("include: ['*.jar']", phone)
        self.assertNotRegex(qt, r"(?i)https?://|maven\s*\{")


if __name__ == "__main__":
    unittest.main()
