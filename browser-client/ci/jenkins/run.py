#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Own an entire non-root CI network/IPC/PID/mount namespace, never host ports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time

REMOTE = 'https://github.com/noah-be/overte'
SOURCE_FILES = ('run.py', 'namespace-owner.py', 'gates.py', 'prepare.py', 'probe.py', 'owned-exec.py', 'owned-xvfb.py', 'chrome-payload.py')


def safe_environment():
    # Keep the actual HOME unchanged; never copy Jenkins/remoting tokens,
    # credential bindings, desktop bus/display/audio or arbitrary build env.
    result = {name: os.environ[name] for name in ('PATH','HOME','LANG','LC_ALL','TZ')
              if name in os.environ}
    result.setdefault('PATH','/usr/local/bin:/usr/bin:/bin')
    result.update(GIT_TERMINAL_PROMPT='0', GIT_CONFIG_GLOBAL='/dev/null',
                  GIT_CONFIG_NOSYSTEM='1', CI='true')
    return result


def empty_npm_environment(runtime, *, create=False):
    """Keep npm's user/global scopes distinct without reading operator config."""
    files = (runtime/'empty-user-npmrc', runtime/'empty-global-npmrc')
    identities = []
    for path in files:
        flags = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK | (os.O_RDWR | os.O_CREAT if create else os.O_RDONLY)
        descriptor = os.open(path, flags, 0o600)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
                raise RuntimeError('CI-npm-config-is-not-owned-private-regular-file')
            if create:
                os.fchmod(descriptor, 0o600)
                os.ftruncate(descriptor, 0)
            elif info.st_size != 0 or stat.S_IMODE(info.st_mode) != 0o600:
                raise RuntimeError('CI-npm-config-is-not-empty-private-file')
            identities.append((info.st_dev, info.st_ino))
        finally:
            os.close(descriptor)
    if identities[0] == identities[1]:
        raise RuntimeError('CI-npm-config-scopes-share-file-identity')
    return {'NPM_CONFIG_USERCONFIG': str(files[0]), 'NPM_CONFIG_GLOBALCONFIG': str(files[1])}


def checked_executable(name):
    candidate = shutil.which(name)
    if not candidate:
        raise RuntimeError('required-host-tool-unavailable:' + name)
    path = Path(candidate).resolve(strict=True)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK):
        raise RuntimeError('required-host-tool-invalid:' + name)
    return str(path)


def checked_source(repo, expected):
    if not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise RuntimeError('source-sha-must-be-exact-lowercase-40hex')
    result = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'],
                            text=True, capture_output=True, check=True, timeout=15,env=safe_environment())
    if result.stdout.strip() != expected:
        raise RuntimeError('checked-out-source-does-not-match-requested-sha')
    origin = subprocess.run(['git', '-C', str(repo), 'remote', 'get-url', 'origin'],
                            text=True, capture_output=True, check=True, timeout=15,env=safe_environment()).stdout.strip()
    if origin.removesuffix('.git') != REMOTE:
        raise RuntimeError('source-remote-is-not-authorized-fork')
    return expected


def checkout_clean(repo):
    return not subprocess.check_output(['git','-C',str(repo),'status','--porcelain',
        '--untracked-files=all'],timeout=15,env=safe_environment()).strip()


def stop_owned(process):
    """Only this Popen child's still-live private process group is signalled."""
    if process is None or process.poll() is not None:
        return
    if os.getpgid(process.pid) != process.pid:
        raise RuntimeError('owned-process-group-changed')
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def ready_line(process, deadline):
    buffer = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('namespace-owner-exited-before-ready')
            for key, _mask in selector.select(.1):
                data = os.read(key.fd, 4096)
                if not data:
                    raise RuntimeError('namespace-owner-output-closed-before-ready')
                buffer.extend(data)
                if len(buffer) > 8192:
                    raise RuntimeError('namespace-owner-startup-output-limit')
                if b'OVERTE_CI_NAMESPACE_READY\n' in buffer:
                    return
    raise RuntimeError('namespace-owner-startup-deadline')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--timeout-seconds', type=int, default=3600)
    parser.add_argument('--probe-only', action='store_true', help='Only qualify namespace/ports; never reports complete CI')
    parser.add_argument('--slirp', type=Path, help='Reviewed slirp executable for namespace-only qualification')
    args = parser.parse_args()
    if os.getuid() == 0:
        raise RuntimeError('CI-must-run-under-nonroot-agent-account')
    if not 60 <= args.timeout_seconds <= 7200:
        raise RuntimeError('CI-deadline-outside-reviewed-range')
    repo = args.repo.resolve(strict=True)
    checked_source(repo, args.source_sha)
    clean = checkout_clean(repo)
    if not args.probe_only and not clean:
        raise RuntimeError('full-CI-requires-clean-exact-source-checkout')
    source = Path(__file__).resolve().parent
    # Always bind the complete dedicated checkout, not its HOME or a broad
    # ancestor. The owner opens this directory before creating private /tmp.
    if repo in (Path('/'), Path.home(), Path('/tmp')) or not (repo / 'browser-client/package.json').is_file():
        raise RuntimeError('CI-requires-a-dedicated-complete-checkout')
    runtime = repo / 'build/jenkins-browser-ci'
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    runtime.chmod(0o700)
    if not args.probe_only and (runtime/'preparation-complete').read_text().strip()!=args.source_sha:
        raise RuntimeError('full-CI-requires-its-owned-complete-dependency-preparation')
    if args.probe_only:
        staged = runtime / 'probe-scripts'
        staged.mkdir(exist_ok=True, mode=0o700)
        for name in SOURCE_FILES:
            if source / name != staged / name:
                shutil.copyfile(source / name, staged / name)
        source = staged
    elif args.slirp:
        raise RuntimeError('explicit-slirp-path-is-only-for-namespace-qualification')
    relative = source.relative_to(repo)
    if not args.probe_only:
        # Runtime/policy helpers must belong to the attested commit, not merely
        # be untracked files next to an unrelated checkout.
        for name in SOURCE_FILES:
            committed = subprocess.check_output(['git','-C',str(repo),'show',
                args.source_sha+':'+str(relative/name)],timeout=15,env=safe_environment())
            if committed != (source/name).read_bytes():
                raise RuntimeError('CI-helper-differs-from-attested-source')
    config = runtime / 'namespace-config.json'
    browser_identity=None
    if not args.probe_only:
        from importlib import import_module
        browser_identity=import_module('chrome-payload').admission_identity(runtime)
    identity = {'browserPayloadManifestSHA256':browser_identity,'sourceSHA': args.source_sha, 'user': os.getuid(), 'group': os.getgid(),
                'repo': str(repo), 'scripts': str(relative),
                'timeoutSeconds': args.timeout_seconds,
                'probeOnly': args.probe_only,
                'sourceCheckoutClean':clean,
                'hostNamespaces': {name: os.stat('/proc/self/ns/'+name).st_ino for name in ('net','ipc','mnt','pid')},
                'sourceFiles': {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in SOURCE_FILES}}
    config.write_text(json.dumps(identity) + '\n')
    config.chmod(0o600)
    unshare = checked_executable('unshare')
    if args.slirp:
        slirp = str(args.slirp.resolve(strict=True))
        if not Path(slirp).is_file() or not os.access(slirp,os.X_OK):
            raise RuntimeError('qualification-slirp-is-not-an-executable-file')
    else:
        sys.path.insert(0,str(repo/'browser-client/lab'))
        from host_tools import load_tools
        slirp = load_tools(repo/'build/browser-lab')['slirp']
    owner = helper = None
    cancelled = False
    def cancel(_signum, _frame):
        nonlocal cancelled
        cancelled = True
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    try:
        with (runtime / 'namespace-private.log').open('wb') as log, \
             (runtime / 'slirp-private.log').open('wb') as slirp_log:
            owner = subprocess.Popen([sys.executable, str(source/'owned-exec.py'), str(os.getpid()),
                unshare, '--user', '--map-current-user', '--keep-caps',
                '--net', '--ipc', '--mount', '--propagation', 'private', '--pid', '--fork',
                '--mount-proc', '--kill-child=KILL', '--', sys.executable,
                str(source / 'namespace-owner.py'), str(config)],
                stdout=subprocess.PIPE, stderr=log, start_new_session=True,env=safe_environment())
            ready_line(owner, time.monotonic() + 20)
            helper = subprocess.Popen([sys.executable, str(source/'owned-exec.py'), str(os.getpid()),
                slirp, '--configure', '--disable-host-loopback',
                '--mtu=65520', '--exit-fd=0', str(owner.pid), 'tap0'],
                stdin=subprocess.PIPE, stdout=slirp_log, stderr=slirp_log,
                start_new_session=True,env=safe_environment())
            deadline = time.monotonic() + args.timeout_seconds
            while owner.poll() is None:
                if cancelled:
                    raise RuntimeError('CI-cancelled')
                if helper.poll() is not None:
                    # Helper and owner pipes can report normal completion in
                    # either order. Do not mislabel that bounded exit race.
                    try:
                        owner.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError('CI-private-network-helper-exited')
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('CI-whole-job-deadline')
                time.sleep(.1)
            return owner.returncode
    finally:
        # PID namespace init death removes descendants, including children that
        # intentionally created their own session/process group.
        stop_owned(owner)
        if helper is not None and helper.stdin is not None:
            helper.stdin.close()
        stop_owned(helper)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print(json.dumps({'passed': False, 'stage': 'isolated-ci-owner',
                          'category': str(error) if isinstance(error, RuntimeError) else type(error).__name__}), file=sys.stderr)
        raise SystemExit(1)
