"""Exercise the production rate query without Android or a live device."""
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
class LoadingFrameCapTest(unittest.TestCase):
    def test_cap_preserves_lower_rates_vr_and_saved_profile(self):
        source = (ROOT / 'interface/src/RefreshRateManager.cpp').read_text()
        begin = source.index('int RefreshRateManager::queryRefreshRateTarget(')
        end = source.index('\nvoid RefreshRateManager::updateRefreshRateController', begin)
        driver = r'''
#include <algorithm>
#include <cassert>
#include <cstring>
#define ANDROID_APP_PHONE_INTERFACE
#define PROP_VALUE_MAX 92
bool enabled = false;
const char* property = "30";
bool phoneLoadingDiagnosticsEnabled() { return enabled; }
int __system_property_get(const char*, char* out) { strcpy(out, property); return strlen(property); }
class RefreshRateManager {
public:
    using RefreshRateProfile = int;
    using RefreshRateRegime = int;
    enum class UXMode { DESKTOP, VR };
    int queryRefreshRateTarget(RefreshRateProfile, RefreshRateRegime, UXMode) const;
};
int REFRESH_RATE_PROFILES[1][3] = {{60, 30, 20}};
const int VR_TARGET_RATE = 90;
''' + source[begin:end] + r'''
int main() {
    RefreshRateManager manager;
    using UX = RefreshRateManager::UXMode;
    assert(manager.queryRefreshRateTarget(0,0,UX::DESKTOP) == 60);
    enabled = true;
    for (const char* value : {"0", "invalid", "300"}) {
        property = value;
        assert(manager.queryRefreshRateTarget(0,0,UX::DESKTOP) == 60);
    }
    property = "30";
    assert(manager.queryRefreshRateTarget(0,0,UX::DESKTOP) == 30);
    assert(manager.queryRefreshRateTarget(0,1,UX::DESKTOP) == 30);
    assert(manager.queryRefreshRateTarget(0,2,UX::DESKTOP) == 20);
    assert(manager.queryRefreshRateTarget(0,0,UX::VR) == 90);
    assert(REFRESH_RATE_PROFILES[0][0] == 60);
}
'''
        with tempfile.TemporaryDirectory(prefix='phone-frame-cap-') as directory:
            path = Path(directory)
            (path/'test.cpp').write_text(driver)
            subprocess.run(['c++','-std=c++17',str(path/'test.cpp'),'-o',str(path/'test')], check=True)
            subprocess.run([str(path/'test')], check=True)
if __name__ == '__main__':
    unittest.main()
