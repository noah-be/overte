#!/usr/bin/env python3
"""Pico production offline result entry point; separate from hardware invocation."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import runpy
import sys

if __name__ == '__main__':
    try:
        runpy.run_path(str(Path(__file__).resolve().parents[4] /
            'tests/device/adapters/pico4/verify_result.py'), run_name='__main__')
    except (ImportError, OSError, ValueError):
        print('PICO_RESULT_REJECTED', file=sys.stderr)
        raise SystemExit(1)
