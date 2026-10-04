# SPDX-License-Identifier: Apache-2.0
"""Explicit pinned signed member; no general alias or runtime trust exemption."""
import hashlib
import fcntl
import io
import importlib.util
import json
import lzma
import os
from pathlib import Path
import re
import stat
import subprocess
import tarfile

PIN = json.loads(Path(__file__).with_name('reviewed-library.json').read_text())
_spec = importlib.util.spec_from_file_location('reviewed_original_alias_build', Path(__file__).with_name('build.py'))
_original = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_original)


def validate_library(record):
    if type(record) is not dict or any(type(k) is not str for k in record) or set(record) != set(PIN):
        raise ValueError('signed-library-schema-refused')
    for key, expected in PIN.items():
        if type(record[key]) is not type(expected) or record[key] != expected:
            raise ValueError('signed-library-pin-refused')
    if not 4194304 < record['memberBytes'] <= 16777216:
        raise ValueError('signed-library-resource-refused')
    return dict(record)


def validate_mixed_budget(general_aliases, library):
    validate_library(library)
    _original.validate_alias_records(general_aliases)
    if type(general_aliases) is not list or len(general_aliases) + 1 > 64:
        raise ValueError('original-combined-count-bound')
    paths = set()
    total = library['memberBytes']
    for item in general_aliases:
        if type(item) is not dict or set(item) != {'path', 'bytes', 'sha256'} or type(item['path']) is not str or type(item['bytes']) is not int or not 0 <= item['bytes'] <= 4194304:
            raise ValueError('original-general-alias-bound')
        if item['path'] in paths or item['path'] == library['canonicalPath']:
            raise ValueError('signed-library-not-also-general-alias')
        if type(item['sha256']) is not str or not re.fullmatch('[a-f0-9]{64}', item['sha256']):
            raise ValueError('original-general-hash-bound')
        paths.add(item['path'])
        total += item['bytes']
    if total > 16777216:
        raise ValueError('original-combined-byte-bound')
    # Charge the complete new typed-record metadata, not only its path, to
    # the unchanged original metadata allowance. This is stricter, not larger.
    signed_metadata = len(json.dumps(library, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii'))
    if sum(len(item['path'].encode('ascii')) for item in general_aliases) + signed_metadata > 16384:
        raise ValueError('original-combined-path-byte-bound')
    return total


def cache_bytes(cache, filename, expected, maximum):
    cache = Path(cache)
    if cache.resolve(strict=True) != cache:
        raise ValueError('cache-alias-refused')
    parent = os.open(cache, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    fd = None
    try:
        info = os.fstat(parent)
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('cache-owner-mode-refused')
        fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid not in (0, os.getuid()) or before.st_mode & 0o022 or not 0 <= before.st_size <= maximum:
            raise ValueError('cache-member-refused')
        data = bytearray()
        while len(data) <= maximum:
            part = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_uid, s.st_mode)
        if len(data) != before.st_size or len(data) > maximum or identity(before) != identity(after) or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('cache-digest-identity-refused')
        return bytes(data)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def authenticate_cache(cache, keyring):
    """Replay signed release/index/package checks; never trusts a boolean proof."""
    release = cache_bytes(cache, 'InRelease', PIN['releaseSHA256'], 1048576)
    index = cache_bytes(cache, 'Packages.xz', PIN['indexSHA256'], 16777216)
    package = cache_bytes(cache, 'package-2.private.deb', PIN['packageSHA256'], PIN['packageBytes'])
    interpreter_package = cache_bytes(cache, 'package-0.private.deb', PIN['interpreterPackageSHA256'], PIN['interpreterPackageBytes'])
    keyring = Path(keyring)
    fd = os.open(keyring, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022 or not 0 < info.st_size <= 1048576:
            raise ValueError('keyring-refused')
        data = os.read(fd, info.st_size + 1)
        after = os.fstat(fd)
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_uid, info.st_mode) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_uid, after.st_mode):
            raise ValueError('keyring-identity-refused')
        if len(data) != info.st_size or hashlib.sha256(data).hexdigest() != PIN['keyringSHA256']:
            raise ValueError('keyring-digest-refused')
    finally:
        os.close(fd)
    # Gpgv sees the SAME authenticated immutable buffers, not mutable cache
    # paths reopened after the checks. These Linux-only descriptors are sealed.
    signature_fds = []
    try:
        for name, content in (('keyring', data), ('release', release)):
            sealed = os.memfd_create('reviewed-' + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            signature_fds.append(sealed)
            offset = 0
            while offset < len(content):
                count = os.write(sealed, content[offset:offset + 65536])
                if count <= 0:
                    raise ValueError('signature-buffer-refused')
                offset += count
            os.lseek(sealed, 0, os.SEEK_SET)
            fcntl.fcntl(sealed, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        result = subprocess.run(['/usr/bin/gpgv', '--homedir', str(cache), '--status-fd', '1', '--keyring',
                                 '/proc/self/fd/' + str(signature_fds[0]), '/proc/self/fd/' + str(signature_fds[1])],
                                pass_fds=signature_fds, capture_output=True, timeout=10)
    finally:
        for sealed in signature_fds:
            os.close(sealed)
    if len(result.stdout) + len(result.stderr) > 65536 or result.returncode:
        raise ValueError('signed-library-signature-refused')
    signatures = [line.split()[2] for line in result.stdout.decode('ascii').splitlines()
                  if line.startswith('[GNUPG:] VALIDSIG ')]
    if signatures != [PIN['signingFingerprint']]:
        raise ValueError('signed-library-signature-refused')
    section = release.decode('ascii').split('SHA256:\n', 1)[1].split('\n-----BEGIN PGP SIGNATURE-----', 1)[0]
    if not re.search(r'^ ' + PIN['indexSHA256'] + r' +' + str(len(index)) + r' main/binary-amd64/Packages\.xz$', section, re.M):
        raise ValueError('signed-library-index-refused')
    decoder = lzma.LZMADecompressor()
    plain = decoder.decompress(index, max_length=32 * 1024 * 1024 + 1)
    if not decoder.eof or len(plain) > 32 * 1024 * 1024:
        raise ValueError('signed-library-index-bound')
    records = []
    interpreter_records = []
    for stanza in plain.decode('utf8').split('\n\n'):
        fields = dict(line.split(': ', 1) for line in stanza.splitlines() if ': ' in line and not line.startswith(' '))
        if fields.get('Package') == PIN['packageName'] and fields.get('Version') == PIN['packageVersion'] and fields.get('Architecture') == PIN['architecture']:
            records.append(fields)
        if fields.get('Package') == PIN['interpreterPackageName'] and fields.get('Version') == PIN['packageVersion'] and fields.get('Architecture') == PIN['architecture']:
            interpreter_records.append(fields)
    if len(records) != 1 or records[0].get('SHA256') != PIN['packageSHA256'] or records[0].get('Size') != str(len(package)):
        raise ValueError('signed-library-package-refused')
    expected = 'pool/main/p/python3.12/' + PIN['packageName'] + '_' + PIN['packageVersion'] + '_amd64.deb'
    if records[0].get('Filename') != expected:
        raise ValueError('signed-library-package-path-refused')
    expected_interpreter = 'pool/main/p/python3.12/' + PIN['interpreterPackageName'] + '_' + PIN['packageVersion'] + '_amd64.deb'
    if len(interpreter_records) != 1 or interpreter_records[0].get('SHA256') != PIN['interpreterPackageSHA256'] or interpreter_records[0].get('Size') != str(len(interpreter_package)) or interpreter_records[0].get('Filename') != expected_interpreter:
        raise ValueError('signed-library-interpreter-package-refused')
    verify_member(package)
    verify_member(interpreter_package, interpreter=True)
    return validate_library(PIN)


def verify_member(package, *, interpreter=False):
    """Exact immutable package buffer; no mutable archive path passed to ar."""
    package_size = PIN['interpreterPackageBytes'] if interpreter else PIN['packageBytes']
    package_hash = PIN['interpreterPackageSHA256'] if interpreter else PIN['packageSHA256']
    member_path = PIN['interpreterCanonicalPath'] if interpreter else PIN['canonicalPath']
    member_size = PIN['interpreterMemberBytes'] if interpreter else PIN['memberBytes']
    member_hash = PIN['interpreterMemberSHA256'] if interpreter else PIN['memberSHA256']
    member_mode = 0o755 if interpreter else PIN['memberMode']
    if type(package) is not bytes or len(package) != package_size or hashlib.sha256(package).hexdigest() != package_hash or package[:8] != b'!<arch>\n':
        raise ValueError('signed-library-package-buffer-refused')
    offset = 8
    members = []
    payload = None
    while offset < len(package):
        header = package[offset:offset+60]
        if len(header) != 60 or header[58:] != b'`\n' or len(members) >= 3:
            raise ValueError('signed-library-ar-refused')
        name = header[:16].decode('ascii').strip().removesuffix('/')
        raw_size = header[48:58].decode('ascii').strip()
        if not raw_size.isdigit():
            raise ValueError('signed-library-ar-size-refused')
        size = int(raw_size)
        start = offset + 60
        if size > 16777216 or start + size > len(package):
            raise ValueError('signed-library-ar-bound')
        members.append(name)
        if name == 'data.tar.zst':
            payload = package[start:start+size]
        offset = start + size + (size & 1)
    if offset != len(package) or members != ['debian-binary', 'control.tar.zst', 'data.tar.zst'] or payload is None:
        raise ValueError('signed-library-ar-layout-refused')
    # This development/staging decoder receives only the exact authenticated
    # immutable compressed buffer. It never runs in capability-enabled setup.
    raw = bounded_decode(payload)
    matches = []
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        count = 0
        for member in archive:
            count += 1
            if count > 8192:
                raise ValueError('signed-library-member-count')
            if member.name.removeprefix('./') == member_path.lstrip('/'):
                matches.append(member)
        if len(matches) != 1:
            raise ValueError('signed-library-member-identity')
        member = matches[0]
        if not member.isreg() or (member.uid, member.gid, member.mode, member.size) != (0, 0, member_mode, member_size):
            raise ValueError('signed-library-member-metadata')
        content = archive.extractfile(member).read(member_size + 1)
        if len(content) != member_size or hashlib.sha256(content).hexdigest() != member_hash:
            raise ValueError('signed-library-member-digest')
    return True


def installed_member(path, *, interpreter=False, budget=None):
    """Prototype full installed-FD match, original ancestry/read limits intact.

    Called only after authenticate_cache; the administrator installer recomputes
    the full signed and installed-byte checks, and C binds the interpreter hash.
    """
    expected_path = PIN['interpreterCanonicalPath'] if interpreter else PIN['canonicalPath']
    expected_size = PIN['interpreterMemberBytes'] if interpreter else PIN['memberBytes']
    expected_hash = PIN['interpreterMemberSHA256'] if interpreter else PIN['memberSHA256']
    if type(path) is not str or path != expected_path:
        raise ValueError('installed-library-path-refused')
    # Every lexical hop and root-owned immutable ancestor keeps original checks.
    if _original.rooted_alias(path) != expected_path:
        raise ValueError('installed-library-canonical-refused')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_mode & 0o022 or before.st_size != expected_size or expected_size > 16777216:
            raise ValueError('installed-library-metadata-refused')
        if not interpreter:
            if type(budget) is not dict or set(budget) != {'reads', 'bytes'} or any(type(value) is not int or value < 0 for value in budget.values()):
                raise ValueError('installed-library-budget-refused')
            if budget['reads'] >= 128 or budget['bytes'] + expected_size > 33554432:
                raise ValueError('original-installed-read-budget')
            budget['reads'] += 1
            budget['bytes'] += expected_size
        digest = hashlib.sha256()
        total = 0
        while total < expected_size:
            part = os.read(fd, min(65536, expected_size - total))
            if not part:
                raise ValueError('installed-library-short-read')
            total += len(part)
            digest.update(part)
        if os.read(fd, 1):
            raise ValueError('installed-library-tail-refused')
        after = os.fstat(fd)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_uid, value.st_mode)
        if identity(before) != identity(after) or digest.hexdigest() != expected_hash:
            raise ValueError('installed-library-content-identity-refused')
        return expected_hash
    finally:
        os.close(fd)


def installed_record_from_cache(cache, keyring, *, budget):
    authenticated = authenticate_cache(cache, keyring)
    installed_member(PIN['interpreterCanonicalPath'], interpreter=True)
    installed_member(PIN['canonicalPath'], budget=budget)
    return authenticated


def bounded_decode(payload):
    # Input is one authenticated immutable package member. Simultaneously feed
    # and drain pipes so no >32MiB allocation or pipe deadlock precedes refusal.
    import selectors,time
    process=subprocess.Popen(['/usr/bin/zstd','-dc'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    poller=selectors.DefaultSelector();result=bytearray();offset=0;deadline=time.monotonic()+5
    try:
        os.set_blocking(process.stdin.fileno(),False);os.set_blocking(process.stdout.fileno(),False)
        poller.register(process.stdin,selectors.EVENT_WRITE);poller.register(process.stdout,selectors.EVENT_READ)
        while poller.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise ValueError('signed-library-data-timeout')
            for key,_mask in poller.select(remaining):
                if key.fileobj is process.stdin:
                    try:count=os.write(process.stdin.fileno(),payload[offset:offset+65536])
                    except BlockingIOError:continue
                    if count<=0:raise ValueError('signed-library-decoder-input')
                    offset+=count
                    if offset==len(payload):poller.unregister(process.stdin);process.stdin.close()
                else:
                    try:part=os.read(process.stdout.fileno(),min(65536,33554433-len(result)))
                    except BlockingIOError:continue
                    if not part:poller.unregister(process.stdout);process.stdout.close()
                    else:
                        result.extend(part)
                        if len(result)>33554432:raise ValueError('signed-library-data-bound')
        if offset!=len(payload)or process.wait(timeout=max(.001,deadline-time.monotonic()))!=0:raise ValueError('signed-library-decoder-refused')
        return bytes(result)
    finally:
        poller.close()
        if process.poll()is None:process.kill()
        process.wait()
        for stream in (process.stdin,process.stdout):
            if not stream.closed:stream.close()


def context(cache,keyring,python):
    value=authenticate_cache(cache,keyring)
    if python!=PIN['interpreterCanonicalPath']:raise ValueError('signed-library-interpreter-context')
    installed_member(python,interpreter=True)
    return value


def header(record):
    if record is None:return '#define PYTHON_SIGNED_LIBRARY_COUNT 0\n'
    validate_library(record)
    array=lambda value:'{'+','.join(str(v)for v in bytes.fromhex(value))+'}'
    return ('#define PYTHON_SIGNED_LIBRARY_COUNT 1\n'
        +'#define SIGNED_LIBRARY_PATH '+json.dumps(record['canonicalPath'])+'\n'
        +'#define SIGNED_LIBRARY_BYTES '+str(record['memberBytes'])+'\n'
        +'static const unsigned char SIGNED_LIBRARY_HASH[32]='+array(record['memberSHA256'])+';\n'
        +'#define SIGNED_LIBRARY_PYTHON_PATH '+json.dumps(record['interpreterCanonicalPath'])+'\n'
        +'static const unsigned char SIGNED_LIBRARY_PYTHON_HASH[32]='+array(record['interpreterMemberSHA256'])+';\n')
