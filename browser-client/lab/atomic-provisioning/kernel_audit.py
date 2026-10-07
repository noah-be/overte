# SPDX-License-Identifier: Apache-2.0
"""Inactive test-only passive collector, with no caller-supplied PID or journal."""
from contextlib import contextmanager
import json
import importlib.util
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import time
from unittest.mock import patch
import weakref

_projection_spec = importlib.util.spec_from_file_location(
    '_atomic_kernel_audit_projection', Path(__file__).with_name('audit_projection.py'))
audit_projection = importlib.util.module_from_spec(_projection_spec)
_projection_spec.loader.exec_module(audit_projection)

MAX_BYTES = 65536
MAX_ROWS = 128
MAX_JSON_LINE = 8192
AUDIT_SECONDS = 4
_runs = weakref.WeakKeyDictionary()
_observing = False
_active_record = None
_ORIGINAL_PREFIX = ['/usr/bin/unshare', '--user', '--map-current-user', '--keep-caps',
                    '--ipc', '--', '/usr/bin/setpriv', '--bounding-set=-all',
                    '--inh-caps=-all', '--ambient-caps=-all', '--']


class RunReceipt:
    """Opaque in-process source-owned receipt, never serialize or accept from CLI."""
    pass


def _child_birth(pid):
    fd = os.open('/proc/' + str(pid) + '/stat', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        data = os.read(fd, 4097)
        if len(data) > 4096:
            raise ValueError('proc-bound')
        prefix, fields = data.rsplit(b') ', 1)
        if not prefix.startswith(str(pid).encode() + b' ('):
            raise ValueError('proc-identity')
        born = fields.split()[19]
        if not born.isdigit() or len(born) > 20:
            raise ValueError('proc-birth')
        return int(born)
    finally:
        os.close(fd)


@contextmanager
def observe_original_run():
    """Around only the unchanged serial subprocess.run expression.

    No argv/stdin/environment/deadline/result change; does not execute the child
    itself. A concurrent/nested/multiple launch cannot produce qualified receipt.
    Additional proc metadata is observational and must not be a performance claim.
    """
    global _observing, _active_record
    receipt = RunReceipt()
    record = {'qualified': False, 'calls': 0}
    _runs[receipt] = record
    if _observing:
        if _active_record is not None:
            _active_record['nested'] = True
        yield receipt
        return
    _observing = True
    _active_record = record
    original = subprocess.Popen

    def watched(*args, **kwargs):
        record['calls'] += 1
        if record['calls'] == 1:
            record['startNs'] = time.time_ns()
            record['startMono'] = time.monotonic_ns()
            argv = args[0] if args else kwargs.get('args')
            record['argvQualified'] = (type(argv) is list and len(argv) == 13
                and argv[:11] == _ORIGINAL_PREFIX and argv[11] == sys.executable
                and type(argv[12]) is str and os.path.isabs(argv[12])
                and kwargs.get('stdout') == subprocess.PIPE
                and kwargs.get('stderr') == subprocess.PIPE)
        child = original(*args, **kwargs)
        if record['calls'] == 1:
            record['pid'] = child.pid
            try:
                record['birthTicks'] = _child_birth(child.pid)
            except (OSError, ValueError, IndexError):
                record['birthTicks'] = None
        return child

    try:
        with patch.object(subprocess, 'Popen', watched):
            yield receipt
    finally:
        _observing = False
        _active_record = None
        record['endNs'] = time.time_ns()
        record['endMono'] = time.monotonic_ns()
        duration = record.get('endMono', 0) - record.get('startMono', 0)
        wall = record['endNs'] - record.get('startNs', 0)
        record['qualified'] = (record['calls'] == 1 and not record.get('nested')
            and record.get('argvQualified') is True and record.get('birthTicks') is not None
            and type(record.get('pid')) is int and 0 < record['pid'] < 2**31
            and 0 <= duration <= 8_000_000_000 and 0 <= wall <= 8_000_000_000
            and abs(duration - wall) <= 1_000_000)


def _checked_executable(value):
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('binary-alias')
    for parent in (path.parent, *path.parents):
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('binary-ancestry')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or not info.st_mode & 0o111:
            raise ValueError('binary-metadata')
        if os.read(fd, 4) != b'\x7fELF':
            raise ValueError('binary-type')
    finally:
        os.close(fd)


def _boot_id():
    fd = os.open('/proc/sys/kernel/random/boot_id', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        value = os.read(fd, 65).decode('ascii').strip()
        if not re.fullmatch('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', value):
            raise ValueError('boot-id')
        return value.replace('-', '')
    finally:
        os.close(fd)


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate-journal-field')
        result[key] = value
    return result


def _number(value, maximum=2**63-1):
    if type(value) is not str or not re.fullmatch('[0-9]{1,19}', value) or int(value) > maximum:
        raise ValueError('journal-number')
    return int(value)


def project_journal(raw, record, boot):
    """Internal projection; runtime caller receives no original data/identities."""
    result = {'status': 'no-matching-owned-audit-record', 'censored': False,
              'kernelAuditRows': 0, 'ownedSetpcapDenials': 0,
              'authentication': 'owned-run-time-boot-trusted-journal'}
    if type(raw) is not bytes or len(raw) > MAX_BYTES or len(raw.splitlines()) > MAX_ROWS:
        result.update(status='journal-bound-refused', censored=True)
        return result
    seen_events = set()
    for raw_line in raw.splitlines():
        if len(raw_line) > MAX_JSON_LINE:
            result.update(status='journal-bound-refused', censored=True)
            return result
        try:
            row = json.loads(raw_line, object_pairs_hook=_unique_pairs)
            if type(row) is not dict or row.get('_BOOT_ID') != boot:
                continue
            transport = row.get('_TRANSPORT')
            if transport not in ('kernel', 'audit'):
                continue
            message = row.get('MESSAGE')
            if type(message) is not str or len(message.encode('utf8')) > 2048:
                continue
            receipt_us = _number(row.get('__REALTIME_TIMESTAMP'))
            if not record['startNs']//1_000_000_000*1_000_000 <= receipt_us <= (record['endNs']//1_000_000_000+2)*1_000_000:
                continue
            if transport == 'audit':
                if row.get('_AUDIT_TYPE') != '1400' or row.get('_AUDIT_TYPE_NAME') != 'AVC' or not message.startswith('AVC '):
                    continue
                event_us = _number(row.get('_SOURCE_REALTIME_TIMESTAMP'))
                audit_id = _number(row.get('_AUDIT_ID'))
                message = 'type=1400 audit(%d.%03d:%d): %s' % (
                    event_us//1_000_000, event_us//1000%1000, audit_id, message[4:])
            else:
                prefix = re.match(r'^(?:audit:\s*)?type=1400 audit\(([0-9]{1,12})\.([0-9]{3}):([0-9]{1,19})\):', message)
                if not prefix:
                    continue
                event_us = int(prefix[1])*1_000_000 + int(prefix[2])*1000
                audit_id = int(prefix[3])
            # Linux audit timestamps are millisecond buckets. Require that
            # the original run's precise window overlaps that bucket.
            if not event_us*1000 <= record['endNs'] or not (event_us+1000)*1000 > record['startNs']:
                continue
            result['kernelAuditRows'] += 1
            observed = audit_projection.project(message.encode('ascii'), record['pid'])
            event = (event_us, audit_id)
            if observed['sameOwnedPidDenials'] and event not in seen_events:
                seen_events.add(event)
                result['ownedSetpcapDenials'] += 1
        except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
            continue
    if result['ownedSetpcapDenials']:
        result['status'] = 'owned-setpcap-audit-denial'
    return result


def _bounded_journal(argv, env):
    """Drain both pipes within hard memory/time bounds; no raw writes/prints."""
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=env)
    reader = selectors.DefaultSelector()
    buffers = [bytearray(), bytearray()]
    terminal = 'complete'
    deadline = time.monotonic() + AUDIT_SECONDS
    try:
        for index, stream in enumerate((process.stdout, process.stderr)):
            os.set_blocking(stream.fileno(), False)
            reader.register(stream, selectors.EVENT_READ, index)
        while reader.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                terminal = 'journal-read-deadline'
                break
            for key, _ in reader.select(remaining):
                part = os.read(key.fileobj.fileno(), min(4096, MAX_BYTES+1-sum(map(len, buffers))))
                if not part:
                    reader.unregister(key.fileobj)
                else:
                    buffers[key.data].extend(part)
                    if sum(map(len, buffers)) > MAX_BYTES:
                        terminal = 'journal-bound-refused'
                        break
            if terminal != 'complete':
                break
        if terminal == 'complete':
            try:
                code = process.wait(timeout=max(.001, deadline-time.monotonic()))
                if code or buffers[1]:
                    terminal = 'journal-access-or-command-refused'
            except subprocess.TimeoutExpired:
                terminal = 'journal-read-deadline'
        return terminal, bytes(buffers[0]) if terminal == 'complete' else b''
    finally:
        reader.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
        process.stderr.close()


def collect(receipt, *, allow_sudo=False):
    """After original result only; default no privilege acquisition.

    Root must explicitly review allow_sudo=True for read-only exact journalctl.
    Ordinary access is always first; only an access/command refusal or empty view permits the
    separately reviewed noninteractive sudo read. No command or gate is retried.
    The result never changes the original test outcome and cannot prove absence
    of a denial. No string/PID/time/file supplied by a native session is accepted.
    """
    unknown = {'status': 'ownership-unqualified', 'censored': False,
               'kernelAuditRows': 0, 'ownedSetpcapDenials': 0,
               'authentication': 'unqualified'}
    if type(allow_sudo) is not bool or type(receipt) is not RunReceipt or receipt not in _runs or not _runs[receipt]['qualified']:
        return unknown
    record = _runs[receipt]
    if record.get('consumed'):
        return unknown
    record['consumed'] = True
    try:
        _checked_executable('/usr/bin/journalctl')
        boot = _boot_id()
        start = record['startNs']//1_000_000_000
        stop = record['endNs']//1_000_000_000 + 2
        argv = ['/usr/bin/journalctl', '--boot', '--no-pager', '--quiet', '--output=json',
                '--since=@'+str(start), '--until=@'+str(stop),
                '_TRANSPORT=kernel', '_TRANSPORT=audit']
        env = {'PATH': '/usr/bin:/usr/sbin', 'LANG': 'C', 'LC_ALL': 'C'}
        if 'HOME' in os.environ:
            env['HOME'] = os.environ['HOME']
        terminal, raw = _bounded_journal(argv, env)
        if allow_sudo and (terminal == 'journal-access-or-command-refused'
                           or terminal == 'complete' and not raw):
            _checked_executable('/usr/bin/sudo')
            _checked_executable('/usr/bin/timeout')
            # Explicit reviewed noninteractive authority only. First retain
            # ordinary access; root timeout owns its own root journal child.
            argv = ['/usr/bin/sudo', '-n', '--', '/usr/bin/timeout',
                    '--kill-after=1s', '2s', *argv]
            terminal, raw = _bounded_journal(argv, env)
        if terminal != 'complete':
            return {**unknown, 'status': terminal, 'censored': terminal == 'journal-bound-refused'}
        return project_journal(raw, record, boot)
    except (OSError, ValueError, TypeError, RecursionError):
        return {**unknown, 'status': 'journal-source-or-access-refused'}
