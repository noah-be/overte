# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Fixed, explicit diagnostic alternative; never select through inherited env."""
import fcntl
import json
import os
from pathlib import Path
import platform
import stat
import struct
import sys

CAPS = ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')
PROFILE = 'bwrap//&unpriv_bwrap (enforce)'


def tmpfile_filter():
    """Additional x86-64 denial, never a relaxation of an inherited policy."""
    if platform.machine() != 'x86_64' or os.O_TMPFILE != 0x410000:
        raise ValueError('confined-filter-ABI-unreviewed')
    # seccomp_data nr@0, arch@4, args[1]@24, args[2]@32. Unknown/x32 ABIs
    # are killed. openat2 has pointer flags, so fixed ENOSYS requests fallback.
    instructions = (
        (0x20, 0, 0, 4),
        (0x15, 1, 0, 0xc000003e),
        (0x06, 0, 0, 0x80000000),
        (0x20, 0, 0, 0),
        (0x45, 0, 1, 0x40000000),
        (0x06, 0, 0, 0x80000000),
        (0x15, 0, 1, 437),
        (0x06, 0, 0, 0x00050026),
        (0x15, 2, 0, 2),
        (0x15, 3, 0, 257),
        (0x06, 0, 0, 0x7fff0000),
        (0x20, 0, 0, 24),
        (0x05, 0, 0, 1),
        (0x20, 0, 0, 32),
        (0x54, 0, 0, 0x410000),
        (0x15, 0, 1, 0x410000),
        (0x06, 0, 0, 0x0005005f),
        (0x06, 0, 0, 0x7fff0000),
    )
    return b''.join(struct.pack('HBBI', *instruction) for instruction in instructions)


def sealed_filter():
    fd = os.memfd_create('owned-fixed-deny-filter', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        data = tmpfile_filter()
        if os.write(fd, data) != len(data):
            raise ValueError('confined-filter-write-refused')
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        return fd
    except BaseException:
        os.close(fd)
        raise


def private_directory(value):
    path = Path(value)
    if not path.is_absolute() or str(path.resolve(strict=True)) != os.fspath(value):
        raise ValueError('confined-private-directory-refused')
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() \
            or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('confined-private-directory-refused')
    return path


def base_command(writable, cwd):
    bwrap = Path('/usr/bin/bwrap')
    if bwrap.resolve(strict=True) != bwrap:
        raise ValueError('confined-system-launcher-refused')
    for path in (bwrap, *bwrap.parents):
        info = path.stat()
        if info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('confined-system-launcher-refused')
    if not bwrap.is_file() or not bwrap.stat().st_mode & stat.S_IXUSR:
        raise ValueError('confined-system-launcher-refused')
    command = [str(bwrap), '--unshare-user', '--uid', str(os.getuid()), '--gid', str(os.getgid()),
               '--unshare-ipc', '--disable-userns', '--cap-drop', 'ALL', '--ro-bind', '/', '/',
               '--dev', '/dev', '--tmpfs', '/tmp']
    for path in writable:
        path = private_directory(path)
        if path in (Path('/'), Path('/tmp'), Path.home()):
            raise ValueError('confined-private-directory-refused')
        command += ['--bind', str(path), str(path)]
    return [*command, '--chdir', str(cwd), '--die-with-parent', '--new-session']


def confinement(pid, parent_user, parent_ipc):
    """Fixed readback; no PID, namespace identity, path or raw label exported."""
    row = {'zeroCapabilities': False, 'noNewPrivileges': False, 'userIsolated': False,
           'ipcIsolated': False, 'profile': 'unqualified', 'identityStable': False,
           'seccompFiltered': False, 'allThreadsConfined': False}
    try:
        proc = Path('/proc') / str(pid)
        before = (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
        status = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
        row['zeroCapabilities'] = all(int(status[name], 16) == 0 for name in CAPS)
        row['noNewPrivileges'] = status['NoNewPrivs'].strip() == '1'
        row['seccompFiltered'] = status['Seccomp'].strip() == '2'
        row['userIsolated'] = os.readlink(proc / 'ns/user') != parent_user
        row['ipcIsolated'] = os.readlink(proc / 'ns/ipc') != parent_ipc
        if (proc / 'attr/current').read_text().strip() == PROFILE:
            row['profile'] = 'signed-bwrap-child-enforce'
        threads = list((proc / 'task').iterdir())
        if 0 < len(threads) <= 256:
            row['allThreadsConfined'] = True
            for thread in threads:
                status = dict(line.split(':', 1) for line in (thread / 'status').read_text().splitlines() if ':' in line)
                if not all(int(status[name], 16) == 0 for name in CAPS) \
                        or status['NoNewPrivs'].strip() != '1' or status['Seccomp'].strip() != '2':
                    row['allThreadsConfined'] = False
                    break
        row['identityStable'] = before == (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
    except (OSError, ValueError, KeyError, IndexError):
        row['allThreadsConfined'] = False
    return row


def require_confinement(row):
    if set(row) != {'zeroCapabilities', 'noNewPrivileges', 'userIsolated', 'ipcIsolated',
                    'profile', 'identityStable', 'seccompFiltered', 'allThreadsConfined'} or row['profile'] != 'signed-bwrap-child-enforce' \
            or any(type(value) is not bool or not value for key, value in row.items() if key != 'profile'):
        raise ValueError('confined-native-guard-refused')


def exec_confined(document, configuration):
    """Already validated record, fixed launcher/policy, host-only bootstrap env."""
    lab = private_directory(document['environment']['OVERTE_LAB_ROOT'])
    output = private_directory(document['output'])
    if lab.parent != output.parent or Path(document['native']) != lab / 'server/opt/overte/domain-server' \
            or Path(document['settings']) != lab / 'config/domain.json' \
            or Path(configuration) != output / 'launch.private.json':
        raise ValueError('confined-owned-layout-refused')
    parents = (os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/ipc'))
    fd = sealed_filter()
    try:
        command = [*base_command((lab, output), document['cwd']), '--seccomp', str(fd), '--',
                   sys.executable, str(Path(__file__).with_name('observer.py')), '--configuration',
                   configuration, '--confined-final-native', '--parent-user', parents[0], '--parent-ipc', parents[1]]
        host = {key: os.environ[key] for key in ('HOME', 'PATH', 'LANG', 'LC_ALL', 'TMPDIR') if key in os.environ}
        host['PYTHONDONTWRITEBYTECODE'] = '1'
        os.set_inheritable(fd, True)
        os.execvpe(command[0], command, host)
    finally:
        os.close(fd)


def exec_final(document, command, parent_user, parent_ipc):
    row = confinement(os.getpid(), parent_user, parent_ipc)
    require_confinement(row)
    # Exactly the previously validated native executable and final argv. No
    # loader/native environment reaches bwrap or the trusted Python bootstrap.
    os.execvpe(command[5], command[5:], document['environment'])


def owned_native_confinement(wrapper, native):
    """Inspect only the one executable descendant of this new owned wrapper."""
    descendants = {wrapper}
    processes = []
    for index, path in enumerate(Path('/proc').iterdir()):
        if index >= 32768:
            raise ValueError('confined-owned-process-limit')
        if not path.name.isdecimal():
            continue
        try:
            fields = (path / 'stat').read_text().split(') ', 1)[1].split()
            processes.append((int(path.name), int(fields[1])))
        except (OSError, ValueError, IndexError):
            continue
    for _ in range(8):
        before = len(descendants)
        for pid, parent in processes:
            if parent in descendants:
                descendants.add(pid)
        if len(descendants) > 128:
            raise ValueError('confined-owned-process-limit')
        if len(descendants) == before:
            break
    matches = []
    for pid in descendants:
        try:
            if os.path.samefile(Path('/proc') / str(pid) / 'exe', native):
                matches.append(pid)
        except OSError:
            continue
    if len(matches) != 1:
        raise ValueError('confined-owned-native-unqualified')
    return confinement(matches[0], os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/ipc'))
