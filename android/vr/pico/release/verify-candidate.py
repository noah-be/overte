#!/usr/bin/env python3
"""Offline internal-candidate verification; mandatory SH-009, no build/sign/upload."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import runpy
import sys
if __name__ == '__main__':
    sys.argv.append('--require-identity')
    try:
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'ci/verify-pico-apk.py'), run_name='__main__')
    except (ImportError, OSError, ValueError):
        print('error: candidate verification failed', file=sys.stderr)
        raise SystemExit(2)
