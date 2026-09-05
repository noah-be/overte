#!/usr/bin/env python3
"""Execute production geometry math; source-check native lifecycle wiring only."""
import subprocess
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="overte-ios-keyboard-") as scratch:
    binary = str(Path(scratch) / "test")
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    str(Path(__file__).with_suffix(".cpp")), "-o", binary],
                   check=True, timeout=60)
    subprocess.run([binary], check=True, timeout=10)
native = (root / "ios/ui/IOSTouchUiMetrics.mm").read_text()
refresh = native[native.index("void IOSTouchUiMetrics::refresh("):
                 native.index("void registerIOSTouchUiMetricsQmlType()")]
for required in ("overte::ios::keyboardOcclusion(", "occlusion.available",
                 "occlusion.bottomInset", "occlusion.visible", "@encode(CGRect)",
                 "fromCoordinateSpace:window.screen.coordinateSpace",
                 "state.window != window", "state.bounds, bounds",
                 "state.screenFrame, screenFrame", "state.orientation",
                 "UIKeyboardWillHideNotification", "UIKeyboardDidHideNotification",
                 "_keyboardVisible = false", "_surfaceWidth = _surfaceHeight = _imeInsetBottom = 0.0"):
    assert required in refresh, required
for required in ("safeAreaInsetsDidChange", "layoutSubviews", "QPointer<IOSTouchUiMetrics>",
                 "state.layoutObserver.geometryChanged = nil", "removeObserver:token",
                 "UISceneWillDeactivateNotification", "UIApplicationWillResignActiveNotification",
                 "UISceneActivationStateForegroundActive"):
    assert required in native, required
assert "imeInset = CGRectIsNull(overlap)" not in refresh
print("PASS production keyboard geometry math; native lifecycle source wiring only (UIKit unexecuted)")
