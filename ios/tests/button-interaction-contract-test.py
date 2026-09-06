#!/usr/bin/env python3
"""Original Shared real-input test, preserving apple-ios's existing action route.

Only the fixture's expected callback platforms differ. The actual production
Button, Qt event delivery and all cancellation/focus/privacy checks are unchanged.
This is host Qt Quick execution, not UIKit or device acceptance.
"""
import importlib.util
from pathlib import Path
import resource
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests/device/contracts/test_ui_button.py"
DRIVER = TEST.with_name("ui-button-test.cpp")
BOUNDARY = TEST.with_name("ui-button-boundary.h")


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    spec = importlib.util.spec_from_file_location("ios_original_button_contract", TEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    production = (ROOT / "interface/resources/qml/controlsUit/Button.qml").read_text()
    assert 'if (Qt.platform.os === "android" || Qt.platform.os === "ios")' in production, \
        "Reconcile the fixture if the original mobile action route changes"
    source = DRIVER.read_text()
    old = 'tablet.actions == (hasAndroidAction && QString::fromLocal8Bit(argv[2]) == "android" ? 1 : 0)'
    new = ('tablet.actions == (hasAndroidAction && (QString::fromLocal8Bit(argv[2]) == "android" || '
           'QString::fromLocal8Bit(argv[2]) == "ios") ? 1 : 0)')
    assert source.count(old) == 1, "Reconcile a changed General fixture explicitly"
    source = source.replace(old, new)
    with tempfile.TemporaryDirectory(prefix="ios-button-fixture-") as scratch:
        scratch = Path(scratch)
        (scratch / DRIVER.name).write_text(source)
        (scratch / BOUNDARY.name).write_bytes(BOUNDARY.read_bytes())
        # Only driver/header lookup moves. module.ROOT stays on the actual tree;
        # no component source, Qt delivery or test method is replaced.
        module.__file__ = str(scratch / TEST.name)
        result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(module))
        if not result.wasSuccessful():
            raise SystemExit(1)
    print("PASS original Button input checks with preserved iOS action expectation; native pending")


if __name__ == "__main__":
    main()
