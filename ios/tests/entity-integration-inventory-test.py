#!/usr/bin/env python3
"""Host test entry point for the entity integration inventory contract."""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
validator = ROOT / "ios/tools/validate-entity-integration.py"
raise SystemExit(subprocess.run([sys.executable, str(validator)], cwd=ROOT).returncode)
