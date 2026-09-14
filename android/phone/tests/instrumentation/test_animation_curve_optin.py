#!/usr/bin/env python3
"""Exercise the production Phone animation experiment gate after property reset."""
from pathlib import Path
import subprocess
import tempfile
source = (Path(__file__).resolve().parents[4] / "libraries/animation/src/AnimationCache.cpp").read_text()
start = source.index("                // Keep the unaccepted parser experiment opt-in")
end = source.index('                animationMapping.insert(', start)
block = source[start:end]
fixture = r'''#include <cassert>
#include <cstring>
#include <string>
#define PROP_VALUE_MAX 92
bool diagnostics;
std::string property;
bool phoneLoadingDiagnosticsEnabled() { return diagnostics; }
int __system_property_get(const char*, char* out) {
    std::strcpy(out, property.c_str()); return property.size();
}
struct Url { std::string value; std::string scheme() const { return value; } };
bool run(const Url& _url) {
''' + block + r'''
    return skipUnusedCurveData;
}
int main() {
    for (bool enabled : {false, true}) {
        diagnostics = enabled;
        for (const char* value : {"", "1", "00", "false", "2"}) {
            property = value; assert(!run({"qrc"}));
        }
        property = "0";
        assert(run({"qrc"}) == enabled);
        assert(!run({"https"}));
    }
}
'''
with tempfile.TemporaryDirectory(prefix="phone-animation-optin-") as temporary:
    root = Path(temporary)
    (root / "test.cpp").write_text(fixture)
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(root / "test.cpp"), "-o", str(root / "test")], check=True)
    subprocess.run([str(root / "test")], check=True)
print("PASS: missing/reset/invalid properties and diagnostics-off retain full parsing; explicit0 enables QRC experiment only.")
