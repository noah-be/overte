#!/usr/bin/env python3
"""Original Shared HTTP test with only its iOS QUuid owner boundary adapted."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests/device/contracts/lifecycle/test_request_cancellation.py"
DRIVER = TEST.with_name("request-cancellation-test.cpp")
spec = importlib.util.spec_from_file_location("ios_original_http_contract", TEST)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
header = (ROOT / "libraries/networking/src/AccountManager.h").read_text()
assert "QUuid _sessionID" in header, "Reconcile test boundary if production session type changes"
source = DRIVER.read_text()
assert source.count('QByteArray _sessionID { "initial" };') == 1
assert source.count('manager._sessionID == "initial"') == 2
initial = 'QUuid(QStringLiteral("{11111111-2222-3333-4444-555555555555}"))'
source = source.replace('QByteArray _sessionID { "initial" };', 'QUuid _sessionID { ' + initial + ' };')
source = source.replace('manager._sessionID == "initial"', 'manager._sessionID == ' + initial)
source = '#include <QtCore/QUuid>\n' + source
with tempfile.TemporaryDirectory(prefix="ios-http-fixture-") as scratch:
    scratch = Path(scratch)
    (scratch / DRIVER.name).write_text(source)
    # Original test resolves only its fixture driver through __file__; ROOT and
    # all production inputs still point to this actual integration worktree.
    module.__file__ = str(scratch / TEST.name)
    result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(module))
    if not result.wasSuccessful():
        raise SystemExit(1)
print("PASS original HTTP methods/Qt abort with iOS QUuid test owner; no native transport proof")
