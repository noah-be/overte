# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Owned DomainServer launch with fixed inherited denial and no loader crossover."""
import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import platform
import signal
import stat
import struct
import subprocess
import sys

CAPS = ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')
PROFILE = 'bwrap//&unpriv_bwrap (enforce)'
NATIVE_SHA256 = '19b63b081b014114558376050a383ce787d0e3a1d159a74026a02aac6932e25b'
MANAGED_RECORD = '/run/overte-owned-domain/launch.json'


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
        threads = list(islice((proc / 'task').iterdir(), 257))
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
        entry = Path(__file__).with_name('observer.py')
        if not entry.is_file():entry = Path(__file__).parent / 'atomic-provisioning/observer.py'
        command = [*base_command((lab, output), document['cwd']), '--seccomp', str(fd), '--',
                   sys.executable, str(entry), '--configuration',
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


def owned_native_pid(wrapper, native):
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
    return matches[0]


def owned_native_confinement(wrapper, native):
    pid = owned_native_pid(wrapper, native)
    return confinement(pid, os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/ipc'))


def host_environment():
    result = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    if 'HOME' in os.environ:result['HOME'] = os.environ['HOME']
    return result


def host_policy():
    """Recognize enforcing AppArmor or preserve the actual enforcing SELinux context."""
    apparmor = Path('/sys/module/apparmor/parameters/enabled')
    if apparmor.exists() and apparmor.read_text().strip() == 'Y':
        return {'kind': 'apparmor', 'context': ''}
    selinux = Path('/sys/fs/selinux/enforce')
    if selinux.exists() and selinux.read_text().strip() == '1':
        context = Path('/proc/self/attr/current').read_text().rstrip('\x00\n')
        if context and len(context) <= 256 and ':' in context:
            return {'kind': 'selinux', 'context': context}
    raise ValueError('managed-host-policy-unqualified')


def require_managed_confinement(row, policy):
    if type(policy) is not dict or set(policy) != {'kind', 'context'} or policy['kind'] not in ('apparmor','selinux'):
        raise ValueError('managed-native-policy-refused')
    expected = 'signed-bwrap-child-enforce' if policy['kind'] == 'apparmor' else 'preserved-enforcing-selinux-context'
    if row.get('profile') != expected:
        raise ValueError('managed-native-policy-refused')
    require_confinement({**row, 'profile': 'signed-bwrap-child-enforce'})


def managed_confinement(wrapper, native, policy):
    pid = owned_native_pid(wrapper, native)
    if not native_endpoint_owned(pid):raise ValueError('managed-native-endpoint-refused')
    row = confinement(pid, os.readlink('/proc/self/ns/user'), os.readlink('/proc/self/ns/ipc'))
    if policy['kind'] == 'selinux' and host_policy() == policy:
        proc = Path('/proc') / str(pid)
        before = (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
        if (proc / 'attr/current').read_text().rstrip('\x00\n') == policy['context'] \
                and before == (proc / 'stat').read_text().split(') ', 1)[1].split()[19]:
            row['profile'] = 'preserved-enforcing-selinux-context'
    require_managed_confinement(row, policy)
    return row


def native_endpoint_owned(pid):
    """Exact fixed listener and this already qualified native PID, no attach."""
    try:
        raw = Path('/proc/net/tcp').read_bytes()
        if len(raw) > 4 * 1024 * 1024:return False
        listeners = {row.split()[9] for row in raw.decode('ascii').splitlines()[1:]
                     if row.split()[1].split(':')[1] == 'B02C' and row.split()[3] == '0A'}
        if len(listeners) != 1:return False
        proc = Path('/proc') / str(pid)
        before = (proc / 'stat').read_text().split(') ', 1)[1].split()[19]
        links = set()
        for index, path in enumerate((proc / 'fd').iterdir()):
            if index >= 1024:return False
            links.add(os.readlink(path))
        return before == (proc / 'stat').read_text().split(') ', 1)[1].split()[19] \
            and any('socket:[' + value + ']' in links for value in listeners)
    except (OSError, ValueError, IndexError, UnicodeError):return False


def sealed_record(data):
    if not isinstance(data, bytes) or not 0 < len(data) <= 65536:
        raise ValueError('managed-launch-record-size-refused')
    fd = os.memfd_create('owned-native-launch-record', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    try:
        if os.write(fd, data) != len(data):raise ValueError('managed-launch-record-write-refused')
        os.lseek(fd, 0, os.SEEK_SET)
        fcntl.fcntl(fd, fcntl.F_ADD_SEALS, fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        return fd
    except BaseException:
        os.close(fd)
        raise


def managed_document(lab, repo, environment):
    lab = private_directory(lab)
    repo = Path(repo)
    native = lab / 'server/opt/overte/domain-server'
    settings = lab / 'config/domain.json'
    if repo.resolve(strict=True) != repo or native.resolve(strict=True) != native \
            or settings.resolve(strict=True) != settings:
        raise ValueError('managed-launch-layout-refused')
    settings_fd = os.open(settings, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(settings_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 1024 * 1024:
            raise ValueError('managed-settings-input-refused')
    finally:os.close(settings_fd)
    if type(environment) is not dict or len(environment) > 256 or any(type(key) is not str or type(value) is not str
            or not key or '=' in key or len(key) > 128 or len(value) > 8192 or '\0' in key + value
            for key, value in environment.items()):
        raise ValueError('managed-launch-environment-refused')
    if any(key in environment for key in ('LD_PRELOAD', 'LD_AUDIT', 'PYTHONPATH', 'PYTHONHOME')) \
            or environment.get('HOME') != os.environ.get('HOME') \
            or environment.get('OVERTE_LAB_ROOT') != str(lab) \
            or environment.get('LD_LIBRARY_PATH') != f'{lab}/server/opt/overte/lib:{lab}/appimage/squashfs-root/usr/lib':
        raise ValueError('managed-launch-environment-refused')
    for key, value in (('HIFI_DOMAIN_SERVER_HTTP_PORT','45100'),('HIFI_DOMAIN_SERVER_HTTPS_PORT','45101'),
                       ('HIFI_DOMAIN_SERVER_PORT','45102'),('HIFI_DOMAIN_SERVER_DTLS_PORT','45103')):
        if environment.get(key) != value:raise ValueError('managed-launch-fixed-port-refused')
    descriptor = os.open(native, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o022 \
                or not info.st_mode & stat.S_IXUSR or info.st_size > 64 * 1024 * 1024:
            raise ValueError('managed-native-executable-refused')
        with os.fdopen(descriptor, 'rb', closefd=False) as source:
            data = source.read(64 * 1024 * 1024 + 1)
        if hashlib.sha256(data).hexdigest() != NATIVE_SHA256:
            raise ValueError('managed-native-executable-refused')
    finally:
        os.close(descriptor)
    return {'version': 1, 'lab': str(lab), 'repo': str(repo), 'environment': environment,
            'policy': host_policy(), 'parentUser': os.readlink('/proc/self/ns/user'),
            'parentIPC': os.readlink('/proc/self/ns/ipc')}


@contextmanager
def managed_command(lab, repo, environment):
    document = managed_document(lab, repo, environment)
    fd = sealed_record((json.dumps(document, separators=(',', ':')) + '\n').encode())
    try:
        yield [sys.executable, str(Path(__file__).resolve()), '--managed-record-fd', str(fd)], host_environment(), fd, document['policy']
    finally:
        os.close(fd)


def checked_managed_record(raw):
    if not isinstance(raw, bytes) or len(raw) > 65536:
        raise ValueError('managed-launch-record-size-refused')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:raise ValueError('managed-record-duplicate-key')
            result[key] = value
        return result
    document = json.loads(raw, object_pairs_hook=unique)
    if type(document) is not dict or set(document) != {'version', 'lab', 'repo', 'environment', 'policy', 'parentUser', 'parentIPC'} \
            or type(document['version']) is not int or document['version'] != 1:
        raise ValueError('managed-launch-record-schema-refused')
    validated = managed_document(document['lab'], document['repo'], document['environment'])
    if type(document['policy']) is not dict or document['policy'] != validated['policy']:
        raise ValueError('managed-launch-record-policy-refused')
    for key, prefix in (('parentUser', 'user:['), ('parentIPC', 'ipc:[')):
        value = document[key]
        if type(value) is not str or not value.startswith(prefix) or not value.endswith(']') \
                or not value[len(prefix):-1].isdecimal() or len(value) > 64:
            raise ValueError('managed-launch-record-namespace-refused')
    return document


def exec_managed(fd):
    required = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
    if fcntl.fcntl(fd, fcntl.F_GET_SEALS) != required:
        raise ValueError('managed-launch-record-unsealed')
    document = checked_managed_record(os.pread(fd, 65537, 0))
    filter_fd = sealed_filter()
    try:
        command = [*base_command((document['lab'],), document['repo']), '--tmpfs', '/run',
                   '--perms', '0700', '--dir', '/run/overte-owned-domain', '--perms', '0600',
                   '--ro-bind-data', str(fd), MANAGED_RECORD, '--seccomp', str(filter_fd), '--',
                   sys.executable, str(Path(__file__).resolve()), '--managed-final-record', MANAGED_RECORD]
        return supervise(command, (fd, filter_fd))
    finally:
        os.close(filter_fd)


def launch_managed_document(document):
    managed = managed_document(document['environment']['OVERTE_LAB_ROOT'], document['cwd'], document['environment'])
    descriptor = sealed_record((json.dumps(managed, separators=(',', ':')) + '\n').encode())
    try:
        return exec_managed(descriptor)
    finally:
        os.close(descriptor)


def supervise(command, descriptors):
    """Tracked group leader survives the short-lived managed start command.

    Bubblewrap and its final payload stay bound to this owned supervisor.
    Killing the registered group kills the supervisor/monitor; PDEATHSIG then
    kills the payload even after Bubblewrap starts its own session.
    """
    expected = os.getpid()
    def parent_guard():
        library = ctypes.CDLL(None, use_errno=True)
        if library.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != expected:
            os._exit(125)
    process = subprocess.Popen(command, env=host_environment(), stdin=subprocess.DEVNULL,
                               pass_fds=descriptors, preexec_fn=parent_guard)
    return process.wait()


def exec_managed_final(path):
    if path != MANAGED_RECORD:
        raise ValueError('managed-final-record-path-refused')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() \
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 65536:
            raise ValueError('managed-final-record-refused')
        document = checked_managed_record(os.read(descriptor, 65537))
    finally:
        os.close(descriptor)
    row = confinement(os.getpid(), document['parentUser'], document['parentIPC'])
    if document['policy']['kind'] == 'selinux' and host_policy() == document['policy']:
        row['profile'] = 'preserved-enforcing-selinux-context'
    require_managed_confinement(row, document['policy'])
    native = Path(document['lab']) / 'server/opt/overte/domain-server'
    command = [str(native), '--user-config', str(Path(document['lab']) / 'config/domain.json'), '--logOptions', 'nocolor,nojournald']
    os.execvpe(command[0], command, document['environment'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--managed-record-fd', type=int)
    choice.add_argument('--managed-final-record')
    args = parser.parse_args()
    try:
        if args.managed_record_fd is not None:return exec_managed(args.managed_record_fd)
        else:exec_managed_final(args.managed_final_record)
    except (OSError, ValueError, KeyError, TypeError):
        print('owned-native-launch-refused', file=sys.stderr)
        return 1
    return 1


if __name__ == '__main__':raise SystemExit(main())
