#!/usr/bin/env python3
"""Expose the colocated Wayland/libei protocol tests to device discovery."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


ADAPTER_DIRECTORY = Path(__file__).resolve().parents[1] / "adapters/desktop_oculix"
if str(ADAPTER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIRECTORY))

TEST_PATH = ADAPTER_DIRECTORY / "test_wayland_libei_client.py"
SPEC = importlib.util.spec_from_file_location("wayland_libei_colocated_tests", TEST_PATH)
TEST_MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TEST_MODULE)

WaylandInputClientTests = TEST_MODULE.WaylandInputClientTests
