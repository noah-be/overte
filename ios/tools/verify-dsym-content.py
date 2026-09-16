#!/usr/bin/env python3
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
"""Reject UUID-only dSYM images without compilation units and source line tables.

The package caller separately verifies the UUID against the exact app executable.
"""
import argparse
import json
from pathlib import Path
import struct


def verify(path):
    with path.open('rb') as stream:
        header = stream.read(32)
        if len(header) != 32:
            raise ValueError('Missing dSYM Mach-O header')
        magic, cpu, _, kind, count, size, _, _ = struct.unpack('<8I', header)
        if (magic, cpu, kind) != (0xfeedfacf, 0x100000c, 10):
            raise ValueError('Expected a thin arm64 MH_DSYM image')
        if count > 4096 or size > 4 * 1024 * 1024:
            raise ValueError('Unreasonable dSYM load commands')
        commands = stream.read(size)
        if len(commands) != size:
            raise ValueError('Truncated dSYM load commands')
        sections = {}; cursor = 0; file_size = path.stat().st_size
        for _ in range(count):
            if cursor + 8 > size:
                raise ValueError('Truncated dSYM command')
            command, length = struct.unpack_from('<II', commands, cursor)
            if length < 8 or cursor + length > size:
                raise ValueError('Invalid dSYM command length')
            if command == 0x19:
                if length < 72:
                    raise ValueError('Truncated dSYM segment')
                nsects = struct.unpack_from('<I', commands, cursor + 64)[0]
                if 72 + nsects * 80 > length:
                    raise ValueError('Truncated dSYM sections')
                for index in range(nsects):
                    offset = cursor + 72 + index * 80
                    name = commands[offset:offset + 16].split(b'\0')[0]
                    segment = commands[offset + 16:offset + 32].split(b'\0')[0]
                    section_size, file_offset = struct.unpack_from('<QI', commands, offset + 40)
                    if segment == b'__DWARF' and name in (b'__debug_info', b'__debug_line'):
                        if name in sections or section_size < 6 or file_offset < 32 + size or file_offset + section_size > file_size:
                            raise ValueError('Invalid/empty dSYM debug section')
                        stream.seek(file_offset)
                        unit_length, version = struct.unpack('<IH', stream.read(6))
                        if unit_length < 2 or unit_length + 4 > section_size or not 2 <= version <= 5:
                            raise ValueError('Invalid dSYM DWARF unit')
                        sections[name] = section_size
            cursor += length
        if cursor != size or set(sections) != {b'__debug_info', b'__debug_line'}:
            raise ValueError('dSYM lacks compilation units or source line tables')
        return {key.decode(): value for key, value in sections.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    print(json.dumps(verify(parser.parse_args().image), sort_keys=True))
