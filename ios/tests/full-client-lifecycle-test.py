#!/usr/bin/env python3
"""Guard SH-005 v002 migration and execute original Shared production-body checks."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import os
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
setup = (root / "interface/src/Application_Setup.cpp").read_text()
connection = "connect(this, &Application::applicationStateChanged, this, &Application::activeChanged);"
assert "activeChanged(applicationState());" in setup.split(connection, 1)[1].split("connect(", 1)[0]
assert "FullClientLifecycle.cpp" not in (root / "ios/integration/CMakeLists.txt").read_text()
assert not (root / "ios/lifecycle/FullClientLifecycle.cpp").exists()
subprocess.run([sys.executable, str(root / "tests/device/contracts/lifecycle/test_contract.py")],
               check=True, timeout=90, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
print("PASS iOS uses original SH-005 v002 initial observer, no duplicate native seed; native execution pending")
