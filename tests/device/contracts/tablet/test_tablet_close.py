"""Execute the production close handler for each tablet platform variant."""
from pathlib import Path
import subprocess
import shlex
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
# The shared/Android layer retains its Android presenter member; the iOS
# product extends that API. Bind the fixture to the actual declared member.
HEADER = (ROOT / "libraries/ui/src/ui/TabletScriptingInterface.h").read_text()
SCREEN_SPACE_MEMBER = "_screenSpaceMode" if "bool _screenSpaceMode" in HEADER else "_androidScreenSpaceMode"


def platforms(method):
    result = ["ANDROID_APP_PHONE_INTERFACE"]
    if "defined(Q_OS_IOS)" in method:
        result.append("Q_OS_IOS")
    return result


class TabletClose(unittest.TestCase):
    def test_home_cleanup_keeps_closed_tablet_hidden(self):
        source = (ROOT / "libraries/ui/src/ui/TabletScriptingInterface.cpp").read_text()
        start = source.index("void TabletProxy::loadHomeScreen(bool forceOntoHomeScreen) {")
        end = source.index("\n}\n", start) + 2
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        fixture = Path(__file__).with_name("tablet-home-visibility-test.cpp")
        qt_libexec = subprocess.check_output(
            ["pkg-config", "--variable=libexecdir", "Qt6Core"], text=True).strip()
        with tempfile.TemporaryDirectory(prefix="overte-tablet-home-") as directory:
            directory = Path(directory)
            (directory / "production.inc").write_text(source[start:end])
            subprocess.run([str(Path(qt_libexec) / "moc"), str(fixture),
                            "-o", str(directory / "tablet-home-visibility-test.moc")],
                           check=True, timeout=10)
            for platform in platforms(source[start:end]):
                with self.subTest(platform=platform):
                    binary = directory / platform
                    subprocess.run(["c++", "-std=c++17", "-fPIC", f"-D{platform}",
                                    f"-DOVERTE_TABLET_SCREEN_SPACE_MEMBER={SCREEN_SPACE_MEMBER}",
                                    "-I", str(directory), str(fixture), "-o", str(binary),
                                    *flags], check=True, timeout=30)
                    subprocess.run([str(binary)], check=True, timeout=5)

    def test_native_close_route(self):
        source = (ROOT / "libraries/ui/src/ui/TabletScriptingInterface.cpp").read_text()
        start = source.index("void TabletProxy::desktopWindowClosed() {")
        end = source.index("\n}\n", start) + 2
        method = source[start:end]
        # Service boundaries record which route the unchanged production
        # handler selects. Full WindowRoot behavior is covered by Qt Quick.
        fixture = """
class TabletProxy {
public:
    bool OVERTE_TABLET_SCREEN_SPACE_MEMBER = false;
    int homes = 0, closes = 0;
    void gotoHomeScreen() { ++homes; }
    void hideAndroidTablet() { ++closes; }
    void desktopWindowClosed();
};
""" + method + """
int main() {
    TabletProxy desktop;
    desktop.desktopWindowClosed();
    if (desktop.homes != 1 || desktop.closes != 0) return 1;
#if defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)
    TabletProxy touch;
    touch.OVERTE_TABLET_SCREEN_SPACE_MEMBER = true;
    touch.desktopWindowClosed();
    if (touch.homes != 0 || touch.closes != 1) return 2;
#endif
}
"""
        with tempfile.TemporaryDirectory(prefix="overte-tablet-close-") as directory:
            cpp = Path(directory) / "close.cpp"
            cpp.write_text(fixture)
            for platform in ["DESKTOP_TEST", *platforms(method)]:
                with self.subTest(platform=platform):
                    binary = Path(directory) / platform
                    subprocess.run(["c++", "-std=c++17", f"-D{platform}",
                                    f"-DOVERTE_TABLET_SCREEN_SPACE_MEMBER={SCREEN_SPACE_MEMBER}", str(cpp),
                                    "-o", str(binary)], check=True, timeout=30)
                    subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
