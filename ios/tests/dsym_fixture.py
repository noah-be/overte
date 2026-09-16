"""Minimal Mach-O/DWARF envelope for content-validation tests; not native evidence."""
import struct


def arm64_dsym():
    units = [struct.pack('<IH', 8, 4) + b'\0' * 6] * 2
    length = 72 + 2 * 80
    offset = 32 + length
    segment = struct.pack('<II16sQQQQIIII', 0x19, length, b'__DWARF', 0, 24,
                          offset, 24, 7, 3, 2, 0)
    sections = b''
    for name, unit in zip([b'__debug_info', b'__debug_line'], units):
        sections += struct.pack('<16s16sQQIIIIIIII', name, b'__DWARF', 0, len(unit),
                                offset, 0, 0, 0, 0, 0, 0, 0)
        offset += len(unit)
    return struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 10, 1, length, 0, 0) + segment + sections + b''.join(units)
