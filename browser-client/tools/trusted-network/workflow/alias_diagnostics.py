# SPDX-License-Identifier: Apache-2.0
"""Failure-only fixed provenance observations. No admission or byte exemption."""
import os
from pathlib import Path
import re
import stat
import struct
import subprocess

PACKAGES = frozenset(('python3.12-minimal', 'libpython3.12-dev', 'libpython3.12t64', 'libpython3.12-stdlib'))
NAMES = {'libpython3.12.so': 'python312-shared-link-name',
         'libpython3.12.so.1': 'python312-shared-soname-name',
         'libpython3.12.so.1.0': 'python312-shared-library-name',
         'libpython3.12.a': 'python312-static-library-name'}


def path_class(path):
    path = Path(path)
    parent = str(path.parent)
    directory = 'python312-config-directory' if re.fullmatch(r'/usr/lib/python3\.12/config-3\.12-[a-z0-9_-]{1,64}', parent) else 'usr-library-directory' if re.fullmatch(r'/usr/lib(?:64)?(?:/[a-z0-9_-]{1,64})?', parent) else 'other-directory'
    return {'nameClass': NAMES.get(path.name, 'unknown-name'), 'directoryClass': directory}


def package_owner(path):
    result = {'status': 'not-observed', 'name': None, 'version': None}
    found = subprocess.run(['/usr/bin/dpkg-query', '--search', path], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=2)
    if found.returncode or len(found.stdout) > 8192:
        return result
    owners = []
    for line in found.stdout.decode('ascii').splitlines():
        if ': ' not in line:
            return result
        package, claimed_path = line.split(': ', 1)
        if claimed_path != path:
            return result
        package = package.removesuffix(':amd64')
        if package not in PACKAGES:
            return result
        owners.append(package)
    if len(owners) != 1:
        return result
    name = owners[0]
    query = subprocess.run(['/usr/bin/dpkg-query', '--show', '--showformat=${Version}', name],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2)
    if query.returncode or len(query.stdout) > 96:
        return result
    version = query.stdout.decode('ascii')
    if not re.fullmatch(r'[A-Za-z0-9.+~:-]{1,96}', version):
        return result
    return {'status': 'installed-metadata-only', 'name': name, 'version': version}


def elf_direct_needed(fd, name):
    """Bounded ELF64-LE dynamic-table read; no member execution or ldd."""
    read_bytes = 0
    def read(offset, length):
        nonlocal read_bytes
        if type(offset) is not int or offset < 0 or not 0 <= length <= 65536:
            raise ValueError('elf-range-refused')
        read_bytes += length
        if read_bytes > 262144:
            raise ValueError('elf-read-bound')
        data = os.pread(fd, length, offset)
        if len(data) != length:
            raise ValueError('elf-short-read')
        return data
    header = read(0, 64)
    if header[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError('elf-format-refused')
    phoff = struct.unpack_from('<Q', header, 32)[0]
    phsize, count = struct.unpack_from('<HH', header, 54)
    if phsize != 56 or not 1 <= count <= 128:
        raise ValueError('elf-header-bound')
    table = read(phoff, phsize * count)
    segments = [struct.unpack_from('<IIQQQQQQ', table, i * 56) for i in range(count)]
    dynamic = [s for s in segments if s[0] == 2]
    if len(dynamic) != 1 or not 16 <= dynamic[0][5] <= 65536 or dynamic[0][5] % 16:
        raise ValueError('elf-dynamic-bound')
    data = read(dynamic[0][2], dynamic[0][5])
    entries = []
    for i in range(0, len(data), 16):
        tag, value = struct.unpack_from('<QQ', data, i)
        if tag == 0:
            break
        entries.append((tag, value))
    else:
        raise ValueError('elf-dynamic-termination')
    pointers = [v for t, v in entries if t == 5]
    sizes = [v for t, v in entries if t == 10]
    needed = [v for t, v in entries if t == 1]
    if len(pointers) != 1 or len(sizes) != 1 or not 1 <= sizes[0] <= 65536 or len(needed) > 64:
        raise ValueError('elf-string-bound')
    loads = [s for s in segments if s[0] == 1 and s[3] <= pointers[0] and pointers[0] + sizes[0] <= s[3] + s[5]]
    if len(loads) != 1:
        raise ValueError('elf-string-map-refused')
    strings = read(loads[0][2] + pointers[0] - loads[0][3], sizes[0])
    names = []
    for offset in needed:
        if offset >= len(strings):
            raise ValueError('elf-string-offset')
        end = strings.find(b'\0', offset, min(len(strings), offset + 257))
        if end < 0:
            raise ValueError('elf-string-termination')
        names.append(strings[offset:end])
    return {'status': 'elf-direct-dependency-only', 'neededCount': len(names),
            'canonicalLibraryNameNeeded': name.encode('ascii') in names,
            'rpathPresent': any(t == 15 for t, _ in entries),
            'runpathPresent': any(t == 29 for t, _ in entries), 'readBytes': read_bytes}


def trusted_regular(path, maximum):
    if type(path) is not str or not re.fullmatch(r'/usr/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*', path):
        raise ValueError('path-shape-refused')
    canonical = Path(path).resolve(strict=True)
    if str(canonical) != path:
        raise ValueError('canonical-path-required')
    for node in (canonical, *canonical.parents):
        info = node.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError('ancestry-refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or not 0 <= info.st_size <= maximum:
        os.close(fd)
        raise ValueError('regular-refused')
    return fd, info


def observe_alias(python, lexical, canonical):
    result = {'schema': 1, 'scope': 'failure-only-installed-alias-provenance', 'status': 'not-observed',
              'lexicalClass': path_class(lexical), 'canonicalClass': path_class(canonical),
              'canonicalPackage': {'status': 'not-observed', 'name': None, 'version': None},
              'lexicalPackage': {'status': 'not-observed', 'name': None, 'version': None},
              'target': {'status': 'not-observed', 'regular': None, 'rootOwned': None,
                         'groupOtherWritable': None, 'generalAliasSizeWithinBound': None},
              'interpreterElf': {'status': 'not-observed'}, 'packageSignatureVerified': False,
              'actualMappedDependencyObserved': False, 'admissionChanged': False}
    try:
        if any(type(p) is not str or not re.fullmatch(r'/usr/[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*', p) for p in (python, lexical, canonical)):
            raise ValueError('path-shape-refused')
        if result['canonicalClass']['nameClass'] == 'unknown-name':
            return result
        fd, before = trusted_regular(canonical, 32 * 1024 * 1024)
        try:
            result['target'] = {'status': 'immutable-metadata-only', 'regular': True,
                                'rootOwned': True, 'groupOtherWritable': False,
                                'generalAliasSizeWithinBound': before.st_size <= 4194304}
            result['canonicalPackage'] = package_owner(canonical)
            result['lexicalPackage'] = package_owner(lexical)
            after = os.fstat(fd)
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(before) != fields(after):
                raise ValueError('target-changed')
        finally:
            os.close(fd)
        fd, before = trusted_regular(python, 32 * 1024 * 1024)
        try:
            result['interpreterElf'] = elf_direct_needed(fd, Path(canonical).name)
            after = os.fstat(fd)
            fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            if fields(before) != fields(after):
                raise ValueError('interpreter-changed')
        finally:
            os.close(fd)
        result['status'] = 'observed-metadata-only'
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        result['status'] = 'observation-refused'
        result['target']['status'] = 'observation-refused'
        result['interpreterElf'] = {'status': 'observation-refused'}
    return result
