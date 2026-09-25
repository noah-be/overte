#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Share byte-identical Qt 5 resource payloads without changing any lookup entry.

Only format version 3 is accepted. Compression, aliases, locale, timestamps,
registration code and names are preserved; no assets or shader variants vanish.
"""
import argparse
import re
import struct
from pathlib import Path


def payload(data, offset):
    if offset < 0 or offset + 4 > len(data):
        raise ValueError('resource data offset outside payload')
    size = struct.unpack_from('>I', data, offset)[0]
    if offset + 4 + size > len(data):
        raise ValueError('truncated resource payload')
    return data[offset:offset + 4 + size]


def compact(tree, data):
    if not tree or len(tree) % 22:
        raise ValueError('invalid version 3 resource tree')
    result = bytearray(tree)
    packed = bytearray()
    seen = {}
    for pos in range(0, len(tree), 22):
        flags = struct.unpack_from('>H', tree, pos + 4)[0]
        if flags & ~7:
            raise ValueError('unsupported resource flags')
        if flags & 2:
            count, first = struct.unpack_from('>II', tree, pos + 6)
            if first + count > len(tree) // 22:
                raise ValueError('directory outside resource tree')
            continue
        old = struct.unpack_from('>I', tree, pos + 10)[0]
        block = payload(data, old)
        key = (flags, block)  # equality compares all bytes, not just a hash
        if key not in seen:
            seen[key] = len(packed)
            packed.extend(block)
        struct.pack_into('>I', result, pos + 10, seen[key])
    # Fail closed if any lookup metadata or payload changed during compaction.
    for pos in range(0, len(tree), 22):
        if struct.unpack_from('>H', tree, pos + 4)[0] & 2:
            if result[pos:pos + 22] != tree[pos:pos + 22]:
                raise ValueError('resource directory metadata changed')
        else:
            if (result[pos:pos + 10] != tree[pos:pos + 10]
                    or result[pos + 14:pos + 22] != tree[pos + 14:pos + 22]):
                raise ValueError('resource lookup metadata changed')
            old = struct.unpack_from('>I', tree, pos + 10)[0]
            new = struct.unpack_from('>I', result, pos + 10)[0]
            if payload(data, old) != payload(packed, new):
                raise ValueError('resource content changed')
    if len(packed) > len(data):
        raise ValueError('compaction increased data size')
    return bytes(result), bytes(packed)


def binary(source):
    if len(source) < 24 or source[:4] != b'qres':
        raise ValueError('not a Qt resource binary')
    version, tree_at, data_at, names_at = struct.unpack_from('>4I', source, 4)
    if version != 3 or not 24 == data_at <= names_at <= tree_at <= len(source):
        raise ValueError('unsupported Qt binary format/layout')
    names = source[names_at:tree_at]
    tree, data = compact(source[tree_at:], source[data_at:names_at])
    header = bytearray(source[:24])
    struct.pack_into('>III', header, 8, 24 + len(data) + len(names), 24, 24 + len(data))
    return bytes(header) + data + names + tree


def array(text, name):
    pattern = re.compile(r'(static const unsigned char ' + name + r'\[\] = \{)(.*?)(\n\};)', re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError('expected exactly one ' + name)
    match = matches[0]
    body = re.sub(r'//[^\n]*', '', match[2])
    if re.sub(r'0x[0-9a-fA-F]{1,2}|[,\s]', '', body):
        raise ValueError('unexpected resource initializer')
    data = bytes(int(m[0], 16) for m in re.finditer(r'0x[0-9a-fA-F]{1,2}', body))
    return match, data


def cpp(source):
    text = source.decode('utf-8')
    if re.findall(r'int version = (\d+);', text) != ['3', '3']:
        raise ValueError('expected Qt format 3 registration and cleanup')
    data_match, data = array(text, 'qt_resource_data')
    tree_match, tree = array(text, 'qt_resource_struct')
    tree, data = compact(tree, data)
    replacements = [(data_match, data), (tree_match, tree)]
    for match, value in sorted(replacements, key=lambda item: item[0].start(), reverse=True):
        formatted = '\n' + '\n'.join(','.join(f'0x{b:02x}' for b in value[i:i+32]) + ','
                                     for i in range(0, len(value), 32))
        text = text[:match.start(2)] + formatted + text[match.end(2):]
    return text.encode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('format', choices=['binary', 'cpp'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    source = args.input.read_bytes()
    output = (binary if args.format == 'binary' else cpp)(source)
    temporary = args.output.with_suffix(args.output.suffix + '.tmp')
    temporary.write_bytes(output)
    temporary.replace(args.output)
    print(f'Qt resource compaction: {args.format}, input={len(source)}, output={len(output)} bytes')


if __name__ == '__main__':
    main()
