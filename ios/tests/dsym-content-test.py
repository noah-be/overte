#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
from dsym_fixture import arm64_dsym

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dsym', ROOT / 'tools/verify-dsym-content.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    image = Path(directory) / 'Overte'
    valid = arm64_dsym(); image.write_bytes(valid)
    assert module.verify(image) == {'__debug_info': 12, '__debug_line': 12}
    for malformed in [valid[:n] for n in range(len(valid))] + [
        valid.replace(b'__debug_info', b'__wrong_info'),
        valid.replace(b'__debug_line', b'__wrong_line'),
        valid[:12] + b'\x02\0\0\0' + valid[16:],
        valid[:-2], b'fixture DWARF']:
        image.write_bytes(malformed)
        try:
            module.verify(image)
        except ValueError:
            pass
        else:
            raise AssertionError('Missing/truncated/non-dSYM debug data accepted')
print('PASS dSYM content: units/line tables; missing, stripped, wrong kind and truncation rejected')
