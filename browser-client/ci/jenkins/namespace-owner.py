#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Trusted setup only; execute all gates non-root with zero inherited caps."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def reap_adopted_children(excluded_pid):
    """Reap already-dead adopted children without stealing Popen's gate status.

    A private PID1 is also responsible for orphans created by nested workers.
    Never signal children here, and never use waitpid(-1) while Popen owns its
    direct gate. The kernel validates each candidate is still our own child.
    """
    with Path(f'/proc/{os.getpid()}/task/{os.getpid()}/children').open('rb') as children_file:
        data = children_file.read(65537)
    if len(data) > 65536:
        raise RuntimeError('CI-adopted-child-inventory-limit')
    words = data.split()
    if len(words) > 4096 or any(not word.isdigit() or len(word) > 10 for word in words):
        raise RuntimeError('CI-adopted-child-inventory-invalid')
    count = 0
    for word in words:
        pid = int(word)
        if pid <= 0 or pid == excluded_pid:
            continue
        try:
            reaped, _status = os.waitpid(pid, os.WNOHANG)
            count += bool(reaped)
        except ChildProcessError:
            # Another normal owner may already have waited during this scan.
            continue
    return count


def main():
    if os.getpid() != 1 or os.getuid() == 0:
        raise RuntimeError('CI-owner-requires-private-PID-init-and-nonroot-UID')
    config = json.loads(Path(sys.argv[1]).read_text())
    if os.getuid() != config['user'] or os.getgid() != config['group']:
        raise RuntimeError('CI-namespace-user-mapping-changed')
    cancelled = False
    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    # Keep an FD to the dedicated checkout before a private tmpfs can cover its
    # original pathname. No host directory or mount point is created or changed.
    descriptor = os.open(config['repo'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        subprocess.run(['mount', '-t', 'tmpfs', '-o', 'mode=1777,size=4096m,nosuid,nodev',
                        'overte-ci-tmp', '/tmp'], check=True, timeout=10)
        workspace = Path(config['repo'])
        if workspace.is_relative_to('/tmp'):
            workspace.mkdir(parents=True, mode=0o700)
        subprocess.run(['mount', '--bind', f'/proc/self/fd/{descriptor}', str(workspace)],
                        pass_fds=(descriptor,), check=True, timeout=10)
    finally:
        os.close(descriptor)
    subprocess.run(['ip', 'link', 'set', 'lo', 'up'], check=True, timeout=10)
    resolver = workspace / 'build/jenkins-browser-ci/resolv.conf'
    resolver.write_text('nameserver 10.0.2.3\noptions timeout:2 attempts:2\n')
    subprocess.run(['mount', '--bind', str(resolver), '/etc/resolv.conf'], check=True, timeout=10)
    subprocess.run(['mount', '-o', 'remount,bind,ro', '/etc/resolv.conf'], check=True, timeout=10)
    print('OVERTE_CI_NAMESPACE_READY', flush=True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if cancelled:
            return 1
        result = subprocess.run(['ip', '-j', 'address', 'show', 'dev', 'tap0'],
                                capture_output=True, timeout=3)
        if result.returncode == 0 and b'10.0.2.100' in result.stdout:
            break
        time.sleep(.1)
    else:
        raise RuntimeError('CI-private-network-configuration-deadline')
    runtime = workspace / 'build/jenkins-browser-ci'
    namespace_config = runtime / 'gate-config.json'
    config['repo'] = str(workspace)
    namespace_config.write_text(json.dumps(config) + '\n')
    namespace_config.chmod(0o600)
    script = workspace / config['scripts'] / ('probe.py' if config['probeOnly'] else 'gates.py')
    with (runtime / 'gates-private.log').open('wb') as log:
        process = subprocess.Popen(['setpriv', '--bounding-set=-all', '--inh-caps=-all',
            '--ambient-caps=-all', '--', sys.executable, str(script), str(namespace_config)],
            stdout=log, stderr=log, start_new_session=True)
        try:
            while process.poll() is None:
                reap_adopted_children(process.pid)
                if cancelled:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL)
                    return 1
                time.sleep(.1)
            reap_adopted_children(process.pid)
            return process.returncode
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait(timeout=5)


if __name__ == '__main__':
    try:raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        # This private log is never a published artifact.
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
