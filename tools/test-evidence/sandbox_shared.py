#!/usr/bin/env python3
"""Manual protected-main shared-host compatibility diagnostic; never PR proof.

Only the existing trusted registry inventory executes. Production execution,
post-capture and evidence publication remain unconditionally unavailable.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr, contextmanager, ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import time
from types import SimpleNamespace

import execution
import inputs
import runtime
import sandbox
import sandbox_host as host
import ci_profile

ROOT = Path(__file__).resolve().parents[2]
VENV = Path('/opt/overte-ci/venv')
PROFILE = 'manual-shared-host-compatibility-v1'
FULL_ENVIRONMENT = 'ubuntu24-host-qt5-qt6-v1'
_TEMURIN17_HOME = Path('/usr/lib/jvm/temurin-17-jdk-amd64')
_TEMURIN17_CACERTS = Path('/etc/ssl/certs/adoptium/cacerts')
_CACERTS_MAX_BYTES = 4 * 1024 ** 2


def sources():
    _, requirements = runtime._requirement_inventory(ROOT)
    names={*sandbox.contract(ROOT)['sources'], *runtime._TRUSTED_EXECUTION_FILES,
                   *requirements, '.github/test-suites.json', 'tests/platform-profile.json',
                   'tools/test-evidence/sandbox_shared.py', 'tools/test-evidence/sandbox_host.py',
                   'tools/test-evidence/sandbox_host_fixture.py', 'tools/test-evidence/sandbox_probe.py',
                   'tools/test-evidence/ci_profile.py','tools/test-evidence/runtime_ci.py',ci_profile.POLICY,
                   ci_profile.PINNED_SOURCE,
                   'tools/repository-checks/workflows/shared-sandbox-host-diagnostic.yml',
                   '.github/workflows/shared-sandbox-host-diagnostic.yml'}
    if ci_profile.controller_policy(ci_profile.load_policy(ROOT)):
        names.update(ci_profile.controller_paths())
    return sorted(names)


def verify_source(revision):
    """Authenticate every actually loaded control/probe/requirement to main."""
    host.verify_qualification_source(sandbox, revision, root=ROOT)
    names = sources()
    rows = sandbox._git(ROOT, 'ls-tree', '-rz', '--full-tree', revision, '--', *names)
    found = set()
    for row in rows.split(b'\0'):
        if not row:
            continue
        header, name = row.split(b'\t', 1)
        mode, kind, oid = header.split()
        relative = name.decode('utf-8')
        expected_mode = b'100755' if relative == 'tests/run-project-tests.py' else b'100644'
        host.require(relative in names and relative not in found and mode == expected_mode and kind == b'blob',
                     'shared-host control inventory is missing or nonregular')
        found.add(relative)
        body = sandbox._git(ROOT, 'cat-file', 'blob', oid.decode(), limit=1_000_000)
        host.require(body == sandbox._source(ROOT, relative), 'loaded shared-host controls differ from protected source')
    host.require(found == set(names), 'shared-host source closure is incomplete')
    profile = json.loads(sandbox._source(ROOT, 'tests/platform-profile.json'))
    host.require(profile == {'schema': 1, 'platform': 'shared', 'suites': []},
                 'manual shared-host qualification cannot activate platform suites')
    return names


def materialize_source(revision, destination, *, repository=None):
    """Match the canonical depth-2 checkout without fabricating more history."""
    repository = ROOT if repository is None else repository
    parents = sandbox._raw_commit_identity(repository, revision)['parents']
    host.require(len(parents) <= 7, 'shared-host source has too many immediate parents for its bounded Git context')
    return sandbox.materialize_candidate_snapshot(repository, revision, destination, context_revisions=tuple(parents))


def project_policy(destination, names, *, trusted_source=None):
    """Project protected controller sources, never copies chosen by candidate."""
    host.require(not any(destination.iterdir()), 'shared-host policy destination is not empty')
    controller=ci_profile.controller_policy(ci_profile.load_policy(ROOT))
    if controller:
        host.require(type(trusted_source) is str and re.fullmatch('[0-9a-f]{40}',trusted_source)
            and trusted_source!='0'*40 and set(ci_profile.controller_paths())<=set(names),
            'controller projection requires complete admitted native D source')
        manifest=ci_profile.capture_controller_manifest(ROOT,trusted_source)
        sandbox._write_source(destination,ci_profile.CONTROLLER_MANIFEST,sandbox._canonical(manifest))
    for relative in names:
        sandbox._write_source(destination, relative, sandbox._source(ROOT, relative),
                              executable=relative == 'tests/run-project-tests.py')
    return sandbox._files(destination)


def prepared_tools(environment, *, profile=FULL_ENVIRONMENT):
    """Identify the fixed venv plus only actual versioned hosted tool roots."""
    host.require(VENV.is_dir() and not VENV.is_symlink(), 'fixed prepared shared-host virtualenv is missing')
    config = {}
    for line in (VENV / 'pyvenv.cfg').read_text(encoding='utf-8').splitlines():
        key, separator, value = line.partition('=')
        if separator:
            config[key.strip()] = value.strip()
    host.require(config.get('include-system-site-packages') == 'false'
                 and re.fullmatch(r'3\.12\.[0-9]+', config.get('version', '')),
                 'prepared venv must use Python3.12 without unbound base packages')
    python = Path(config.get('home', '')).resolve(strict=True).parent
    node = Path(environment.get('QUALIFY_NODE_ROOT', '')).resolve(strict=True)
    host.require(profile in {FULL_ENVIRONMENT,ci_profile.PROFILE}, 'unsupported selected runtime profile')
    java = None if profile == ci_profile.PROFILE else Path(environment.get('QUALIFY_JAVA_HOME', '')).resolve(strict=True)
    toolchains = []
    for path in (python, node, *(() if java is None else (java,))):
        host.require(path.is_absolute() and path.is_dir() and not path.is_symlink(), 'prepared tool installation is unavailable')
        if path.is_relative_to('/opt/hostedtoolcache'):
            host.require(len(path.parts) >= 5, 'hosted tool root is not version-specific')
            if path not in toolchains:
                toolchains.append(path)
        else:
            host.require(path == java and path.is_relative_to('/usr/lib/jvm'), 'prepared tool root is outside readonly system inputs')
    host.require((VENV / 'bin/python').resolve(strict=True) == (python / 'bin/python3').resolve(strict=True),
                 'prepared venv does not use the identified Python installation')
    freeze_prepared_java_parent(java)
    queries=[(node/'bin/node',['--version'],r'v22\.[0-9]+\.[0-9]+')]
    if java is not None:queries.append((java/'bin/java',['--version'],r'(?:openjdk|java) 17[. ].*'))
    for executable, arguments, version in queries:
        result = host.command([str(executable), *arguments])
        host.require(result.returncode == 0 and re.fullmatch(version, result.stdout.decode().splitlines()[0]),
                     'prepared shared-host tool version is unsupported')
    return tuple(toolchains), python, node, java


def freeze_prepared_java_parent(java):
    """Protect the one packaged JDK parent before querying or binding Java.

    The reviewed hosted image makes /usr/lib/jvm world-writable. Its selected
    JDK is already frozen by trusted provisioning; protect its parent as well.
    Other directories, owners, aliases and prepared profiles are never repaired.
    """
    if java != _TEMURIN17_HOME:
        return
    host.require(os.geteuid() == 0, 'prepared Java parent requires the root supervisor')
    original_java = java.lstat()
    host.require(java.resolve(strict=True) == java and stat.S_ISDIR(original_java.st_mode)
                 and original_java.st_uid == 0 and not original_java.st_mode & 0o022,
                 'selected prepared Java root is aliased or mutable')
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptors = []
    try:
        current = os.open('/', flags)
        descriptors.append(current)
        parts = java.parent.parts[1:]
        for index, name in enumerate(parts):
            ancestor = os.fstat(current)
            host.require(stat.S_ISDIR(ancestor.st_mode) and ancestor.st_uid == 0
                         and not ancestor.st_mode & 0o022,
                         'prepared Java parent ancestor is aliased or mutable')
            child = os.open(name, flags, dir_fd=current)
            descriptors.append(child)
            before = os.fstat(child)
            host.require(stat.S_ISDIR(before.st_mode) and before.st_uid == 0,
                         'prepared Java parent is not a root-owned directory')
            if index == len(parts) - 1:
                entry = os.stat(name, dir_fd=current, follow_symlinks=False)
                host.require((entry.st_dev, entry.st_ino) == (before.st_dev, before.st_ino),
                             'prepared Java parent changed before freezing')
                mode = stat.S_IMODE(before.st_mode) & ~0o022
                if stat.S_IMODE(before.st_mode) != mode:
                    os.fchmod(child, mode)
                after = os.fstat(child)
                entry = os.stat(name, dir_fd=current, follow_symlinks=False)
                host.require((after.st_dev, after.st_ino, after.st_uid, after.st_gid)
                             == (before.st_dev, before.st_ino, before.st_uid, before.st_gid)
                             and stat.S_ISDIR(after.st_mode) and stat.S_IMODE(after.st_mode) == mode
                             and (entry.st_dev, entry.st_ino) == (after.st_dev, after.st_ino),
                             'prepared Java parent changed while freezing')
            current = child
        after_java = java.lstat()
        host.require((after_java.st_dev, after_java.st_ino, after_java.st_mode, after_java.st_uid, after_java.st_gid)
                     == (original_java.st_dev, original_java.st_ino, original_java.st_mode,
                         original_java.st_uid, original_java.st_gid),
                     'selected prepared Java root changed while freezing its parent')
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def identity_roots(prepared):
    # Java may live under readonly /usr rather than hostedtoolcache; its full
    # prepared JDK still belongs to the protected before/after input identity.
    return tuple(dict.fromkeys((*prepared[0], *(() if prepared[3] is None else (prepared[3],)))))


def _prepared_external_input(roots, external_inputs):
    """One reviewed Debian Temurin17 data leaf, never a general alias escape."""
    host.require(type(external_inputs) is tuple and external_inputs in ((), (_TEMURIN17_CACERTS,)),
                 'unsupported prepared external inputs')
    if not external_inputs:
        return None
    host.require(_TEMURIN17_HOME in roots, 'prepared external input lacks its bound Temurin17 root')
    alias = _TEMURIN17_HOME / 'lib/security/cacerts'
    alias_info = alias.lstat()
    host.require(stat.S_ISLNK(alias_info.st_mode) and alias_info.st_uid == 0
                 and os.readlink(alias) == str(_TEMURIN17_CACERTS),
                 'prepared external input has an unsupported Java alias')
    parents = []
    for path in sorted({*alias.parents, *_TEMURIN17_CACERTS.parents}, key=str):
        info = path.lstat()
        host.require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                     'prepared external input parent is aliased or mutable')
        parents.append([str(path), {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid, 'gid': info.st_gid}])
    info = _TEMURIN17_CACERTS.lstat()
    host.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                 and stat.S_IMODE(info.st_mode) in {0o444, 0o644}
                 and 0 < info.st_size <= _CACERTS_MAX_BYTES,
                 'prepared external input is not a protected bounded certificate store')
    host.require(alias.resolve(strict=True) == _TEMURIN17_CACERTS,
                 'prepared external input resolution differs')
    return {'alias': {'path': str(alias), 'target': os.readlink(alias),
                      'mode': stat.S_IMODE(alias_info.st_mode), 'uid': alias_info.st_uid, 'gid': alias_info.st_gid},
            'parents': parents, 'leaf': {'mode': stat.S_IMODE(info.st_mode), 'uid': info.st_uid,
                                       'gid': info.st_gid, 'size': info.st_size}}


def prepared_external_inputs(prepared):
    """Select the fixed leaf only when the actual prepared Java references it."""
    java = prepared[3]
    if java != _TEMURIN17_HOME:
        return ()
    alias = java / 'lib/security/cacerts'
    if not alias.is_symlink() or os.readlink(alias) != str(_TEMURIN17_CACERTS):
        return ()
    selected = (_TEMURIN17_CACERTS,)
    _prepared_external_input(identity_roots(prepared), selected)
    return selected


def prepared_identity(toolchains, *, external_inputs=()):
    """Bind all mounted prepared files, modes and aliases once per batch side."""
    roots = (VENV, *toolchains)
    external = _prepared_external_input(roots, external_inputs)
    result, entries, size = {}, 0, 0
    for root in roots:
        root_info = root.lstat()
        host.require(stat.S_ISDIR(root_info.st_mode) and root_info.st_uid == 0 and not root_info.st_mode & 0o022,
                     "prepared shared-host root is not protected")
        digest = hashlib.sha256()
        for directory, children, names in os.walk(root, followlinks=False):
            children.sort()
            for name in sorted([*children, *names]):
                path = Path(directory) / name
                info = path.lstat()
                entries += 1
                host.require(entries <= 150_000 and info.st_uid == 0
                             and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022),
                             'prepared shared-host inputs are mutable or exceed inventory bounds')
                relative = path.relative_to(root).as_posix()
                if stat.S_ISLNK(info.st_mode):
                    target = path.resolve(strict=True)
                    fixed_external = (external is not None and path == _TEMURIN17_HOME / 'lib/security/cacerts'
                                      and target == _TEMURIN17_CACERTS)
                    host.require(fixed_external or any(target.is_relative_to(allowed) for allowed in (*roots, Path('/usr'))),
                                 'prepared tool alias escapes readonly mounts')
                    value = {'alias': os.readlink(path)}
                elif stat.S_ISDIR(info.st_mode):
                    value = {'directory': True, 'mode': stat.S_IMODE(info.st_mode)}
                else:
                    host.require(stat.S_ISREG(info.st_mode) and info.st_size <= 256 * 1024 ** 2,
                                 'prepared tool contains an unsupported input')
                    size += info.st_size
                    host.require(size <= 4 * 1024 ** 3, 'prepared tool inventory exceeds byte bound')
                    value = {'mode': stat.S_IMODE(info.st_mode), 'size': info.st_size,
                             'sha256': sandbox._file_hash(path)}
                digest.update(sandbox._canonical([relative, value]))
        result[str(root)] = 'sha256:' + digest.hexdigest()
    if external is not None:
        content = sandbox._file_hash(_TEMURIN17_CACERTS)
        host.require(_prepared_external_input(roots, external_inputs) == external,
                     'prepared external input changed during identification')
        external['leaf']['sha256'] = content
        result[str(_TEMURIN17_CACERTS)] = 'sha256:' + hashlib.sha256(sandbox._canonical(external)).hexdigest()
    return result


def shared_plan(layout, command, prepared, environment):
    toolchains, python, node, java = prepared
    allowed = {'python': str(VENV / 'bin/python'), 'node': str(node / 'bin/node'), 'bash': '/usr/bin/bash'}
    host.require(command and command[0] in allowed, 'shared-host command uses an unsupported executable')
    quick = java is None
    plan = sandbox.build_plan(layout, [allowed[command[0]], *command[1:]], environment=environment,
                              runtime_profile=ci_profile.PROFILE if quick else FULL_ENVIRONMENT)
    # These exact additions are internal to this fixed diagnostic profile.
    # runtime._flags binds the third Git override distinctly; no wildcard and
    # no inherited candidate environment enter the namespace.
    effective = {'PATH': ':'.join([str(VENV / 'bin'), str(node / 'bin'),
                                 *([] if quick else [str(java/'bin')]), '/usr/bin', '/bin']),
                 'LD_LIBRARY_PATH': str(python / 'lib'),
                 'PKG_CONFIG_PATH': str(python / 'lib/pkgconfig'), 'GIT_CONFIG_COUNT': '3',
                 'GIT_CONFIG_KEY_2': 'safe.directory', 'GIT_CONFIG_VALUE_2': '/work'}
    if not quick:effective['JAVA_HOME']=str(java)
    # Locate the command separator rather than relying on caller argument count.
    split = plan['argv'].index('--')
    argv = plan['argv'][:split]
    for path in prepared_external_inputs(prepared):
        argv += ['--ro-bind', str(path), str(path)]
    for name, value in sorted(effective.items()):
        argv += ['--setenv', name, value]
    plan['argv'] = [*argv, '--', *plan['argv'][split + 1:]]
    return plan


def validate_probe(result, binding, uid, gid):
    if not (result['exit_code'] == 0 and result['reason'] is None
            and result['cleanup'] == {'kernel_populated': 0, 'subtree_kill': True}):
        detail = {'exit_code': result['exit_code'], 'reason': result['reason'], 'cleanup': result['cleanup'],
                  'protected_probe_tail': sandbox.safe_diagnostic(result.get('diagnostic', b'')[-8192:])}
        raise host.Unavailable('full shared-host probe failed: ' + json.dumps(detail, sort_keys=True))
    observed = result['observation']
    host.require(type(observed) is dict and set(observed) == {'schema', 'authority', 'measurement', 'binding',
                 'environment', 'process', 'mounts', 'namespaces', 'reusable'} and observed['schema'] == 1
                 and observed['authority'] == 'none' and observed['measurement'] == PROFILE
                 and observed['binding'] == binding and observed['reusable'] is False,
                 'protected full shared-host probe binding is invalid')
    mounts = observed['mounts']
    readonly = {'/usr', '/work', '/overte-policy', str(VENV)}
    readonly.update(path for path in binding['prepared'] if not Path(path).is_relative_to('/usr'))
    host.require(type(mounts) is dict and all('ro' in mounts.get(path, ()) for path in readonly)
                 and 'rw' in mounts.get('/work/build', ()), 'full shared-host mount protection is incomplete')
    namespaces = observed['namespaces']
    outside = binding['outside_namespaces']
    host.require(type(namespaces) is dict and set(namespaces) == set(outside)
                 and all(type(value) is int and value > 0 and value != outside[name] for name, value in namespaces.items()),
                 'full shared-host namespaces are not independent of the host')
    identity = inputs._environment(observed['environment'])
    quick = binding.get('runtime_profile',FULL_ENVIRONMENT) == ci_profile.PROFILE
    host.require(binding.get('runtime_profile',FULL_ENVIRONMENT) in {FULL_ENVIRONMENT,ci_profile.PROFILE},
                 'unknown protected selected runtime profile')
    common = (re.fullmatch(r'3\.12\.[0-9]+', identity.get('python', {}).get('version', ''))
              and identity.get('tools', {}).get('node', {}).get('version', '').startswith('v22.')
              and identity.get('system_packages') and identity.get('trusted_execution'))
    complete = (identity.get('schema') == 2 and identity.get('profile') == ci_profile.PROFILE
                and identity.get('selection') == binding.get('profile_binding')
                and not {'qt','glm','java'} & identity.keys()) if quick else (
                identity.get('schema') == inputs.ISOLATED_FULL_SCHEMA
                 and identity.get('profile') == inputs.ISOLATED_FULL_PROFILE
                 and identity.get('prepared', {}).get('roots') == binding['prepared']
                 and set(identity.get('qt', {}).get('modules', {})) == set(runtime._QT_MODULES)
                 and set(identity.get('glm', {})) == {'header_digest', 'configuration_digest'})
    host.require(common and complete,
                 'full protected shared-host environment is incomplete')
    status = observed['process']['status']
    host.require(status.get('NoNewPrivs') == '1' and status.get('Uid', '').split() == [str(uid)] * 4
                 and status.get('Gid', '').split() == [str(gid)] * 4
                 and all(status.get(key) == '0000000000000000' for key in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')),
                 'full shared-host probe retained privileges')
    host.require(observed['environment']['flags']['git_process_overrides'] == 'maintenance-disabled-safe-work',
                 'full shared-host probe lacks its exact immutable Git exception')
    return observed['environment']


class Batch:
    """Root-owned launch adapter: only selected trusted commands, fresh scratch."""
    def __init__(self, base, candidate, policy, snapshot, projection, binding, prepared, delegated, uid, gid, environment):
        self.base, self.candidate, self.policy = base, candidate, policy
        self.snapshot, self.projection, self.binding = snapshot, projection, binding
        self.prepared, self.delegated, self.uid, self.gid, self.environment = prepared, delegated, uid, gid, environment
        self.protected = base / 'protected'
        self.protected.mkdir(mode=0o700)
        self.scopes, self.proofs = [], []

    def empty(self):
        host.require(all(scope.populated() == 0 for scope in self.scopes), 'shared-host post-probe attempted with a live prior scope')

    def launch(self, command, timeout, cancelled, *, probe=False):
        self.empty()
        with tempfile.TemporaryDirectory(prefix='suite-', dir=self.base) as temporary:
            directory = Path(temporary)
            directory.chmod(0o755)
            scratch = directory / 'scratch'
            scratch.mkdir(mode=0o700)
            os.chown(scratch, self.uid, self.gid)
            layout = sandbox.Layout(self.candidate, scratch, self.policy, VENV, self.protected, self.prepared[0])
            plan = shared_plan(layout, command, self.prepared, self.environment)
            path = directory / 'plan.json'
            path.write_bytes(sandbox._canonical(plan['argv']))
            scope = host.OwnedScope(self.uid, self.gid, self.delegated)
            self.scopes.append(scope)
            guardian = None
            try:
                guardian = host.Guardian(scope, self.protected, self.binding, lifetime=timeout + 10)
                result = host.supervise(scope, path, self.uid, self.gid, timeout=timeout,
                                        case='shared-probe' if probe else 'suite', cancelled=cancelled)
                proof = guardian.finish()
                self.proofs.append(proof)
                return result
            finally:
                if guardian is not None:
                    guardian.close()
                scope.kill_and_wait()
                scope.close()
                self.scopes.remove(scope)

    def run_command(self, command, timeout, cancelled):
        result = self.launch(command, timeout, cancelled)
        output = sandbox.safe_diagnostic(result['diagnostic'])
        return result['exit_code'] if result['reason'] is None else 1, output, result['reason'] or ''

    @contextmanager
    def _pair_scope(self, command, timeout):
        temporary = tempfile.TemporaryDirectory(prefix='suite-', dir=self.base)
        scope = guardian = None
        registered = False
        primary = None
        try:
            directory = Path(temporary.name)
            directory.chmod(0o755)
            scratch = directory / 'scratch'
            scratch.mkdir(mode=0o700)
            os.chown(scratch, self.uid, self.gid)
            layout = sandbox.Layout(self.candidate, scratch, self.policy, VENV, self.protected, self.prepared[0])
            plan = shared_plan(layout, command, self.prepared, self.environment)
            path = directory / 'plan.json'
            path.write_bytes(sandbox._canonical(plan['argv']))
            scope = host.OwnedScope(self.uid, self.gid, self.delegated)
            self.scopes.append(scope)
            registered = True
            guardian = host.Guardian(scope, self.protected, self.binding, lifetime=timeout + 10)
            yield scope, path, guardian
        except BaseException as error:
            primary = error
            raise
        finally:
            # Attempt every owned cleanup, even when an earlier one fails.
            # An existing setup/body failure remains the primary exception.
            # A successful body still fails on its first cleanup exception.
            callbacks = []
            if guardian is not None:
                callbacks.append(guardian.close)
            if scope is not None:
                callbacks.extend((scope.kill_and_wait, scope.close))
            if registered:
                callbacks.append(lambda: self.scopes.remove(scope))
            callbacks.append(temporary.cleanup)
            first_cleanup = None
            for cleanup in callbacks:
                try:
                    cleanup()
                except BaseException as error:
                    if first_cleanup is None:
                        first_cleanup = error
            if primary is None and first_cleanup is not None:
                raise first_cleanup

    def run_pair(self, commands, timeout, cancelled):
        """The parent retains both kernel scopes/guardians until both finish."""
        self.empty()
        host.require(type(commands) is list and len(commands) == 2 and timeout == 240,
                     'only the fixed two-suite 240s pair is supported')
        with ExitStack() as stack:
            launches = [stack.enter_context(self._pair_scope(command, timeout)) for command in commands]
            results = host.supervise_pair([(scope, path) for scope, path, _ in launches],
                                         self.uid, self.gid, timeout=timeout, cancelled=cancelled)
            host.require(len(results) == 2 and all(value['cleanup'] ==
                {'kernel_populated': 0, 'subtree_kill': True} for value in results),
                'parallel suite kernel cleanup is incomplete')
            for _, _, guardian in launches:
                self.proofs.append(guardian.finish())
        self.empty()
        return results


    def probe(self, cancelled):
        self.empty()
        # A normal absolute protected script preserves the same interpreter
        # flags as canonical Python suite children. Its script-directory import
        # root is protected policy, never /work; PYTHONPATH is absent.
        result = self.launch(['python', '/overte-policy/tools/test-evidence/sandbox_probe.py', '--shared-host'],
                             120, cancelled, probe=True)
        return validate_probe(result, self.binding, self.uid, self.gid)


class BoundedLog:
    """Root-only diagnostic log; truncate storage without changing test status."""
    def __init__(self, output):
        self.output, self.remaining = output, 4_000_000
    def write(self, text):
        body = text.encode('utf-8', errors='replace')
        self.output.write(body[:self.remaining])
        self.remaining = max(0, self.remaining - len(body))
        return len(text)
    def flush(self):
        self.output.flush()


# Production opts into this fixed pair. No CLI, environment, manifest or
# candidate declaration can add owners or change the concurrency.
_SUITE_PAIR = ('test-evidence', 'host-selection')
_PAIR_COMMANDS = (('python', 'tools/test-evidence/test.py'),
                  ('python', 'tests/host-selection-test.py'))


def _run_pair_suites(controller, batch, suites, cancelled, report):
    """Preserve selected order/results while only the fixed pair overlaps."""
    by_name = {suite.name: suite for suite in suites}
    host.require(len(by_name) == len(suites)
                 and all(name in by_name for name in _SUITE_PAIR)
                 and tuple(by_name[name].command for name in _SUITE_PAIR) == _PAIR_COMMANDS,
                 'parallel pair is not the exact trusted CI fixture command set')
    results = {}
    started = time.monotonic()
    for suite in suites:
        if cancelled:
            break
        if suite.name in results:
            continue
        if suite.name in _SUITE_PAIR:
            commands = [list(by_name[name].command) for name in _SUITE_PAIR]
            for name in _SUITE_PAIR:
                print(f'RUNNING {name}', flush=True)
            observed = batch.run_pair(commands, 240, cancelled)
            host.require(len(observed) == 2, 'parallel suite observation is incomplete')
            for name, value in zip(_SUITE_PAIR, observed):
                status = 'passed' if value['exit_code'] == 0 and value['reason'] is None else 'failed'
                output = sandbox.safe_diagnostic(value['diagnostic'])
                message = value['reason'] or ('' if status == 'passed' else f"exit code {value['exit_code']}")
                results[name] = dict(name=name, status=status, message=message,
                                     output=output, time=value['duration'])
                print(f"{status.upper():7} {name:<24} {value['duration']:7.3f}s", flush=True)
                if status == 'failed':
                    print(output.rstrip(), file=sys.stderr)
        else:
            observed = []
            controller.run_suites(SimpleNamespace(timeout=240, host_timeout=900, native_build_dir=None,
                junit=None, fail_fast=False), [suite], cancelled, result_callback=observed.append)
            host.require(len(observed) == 1 and observed[0]['name'] == suite.name,
                         'serial suite observation is incomplete')
            results[suite.name] = observed[0]
    ordered = [results[suite.name] for suite in suites if suite.name in results]
    elapsed = time.monotonic() - started
    controller.write_junit(report, ordered, elapsed)
    failed = sum(entry['status'] != 'passed' for entry in ordered)
    print(f'Overte project suite: {len(ordered)-failed} passed, {failed} failed ({elapsed:.2f}s)', flush=True)
    return (128 + cancelled[0] if cancelled else 1 if failed or len(ordered) != len(suites) else 0), ordered


def run_suites(batch, registry, cancelled, *, report, names=None, suite_workers=1):
    """Use the existing controller and its actual 900s device timeout rule."""
    controller = execution._runner()
    names = execution.select_common(registry, names)
    host.require(bool(names), 'shared-host batch requires a nonempty trusted selection')
    host.require(type(suite_workers) is int and suite_workers in (1, 2), 'unsupported protected suite workers')
    paired = suite_workers == 2 and set(_SUITE_PAIR) <= set(names)
    suites = [controller.Suite(name, registry['suites'][name]['layer'], tuple(registry['suites'][name]['command']))
              for name in names]
    previous = controller.run_command
    controller.run_command = batch.run_command
    observations = []
    try:
        with report.with_suffix('.log').open('xb') as output:
            log = BoundedLog(output)
            with redirect_stdout(log), redirect_stderr(log):
                if paired:
                    code, observed = _run_pair_suites(controller, batch, suites, cancelled, report)
                    observations.extend(observed)
                else:
                    code = controller.run_suites(SimpleNamespace(timeout=240, host_timeout=900, native_build_dir=None,
                                                junit=report, fail_fast=False), suites, cancelled,
                                                result_callback=observations.append)
    except host.Unavailable as error:
        current = suites[min(len(observations), len(suites) - 1)].name
        raise host.Unavailable('shared-host launch unavailable: ' + json.dumps(
            {'suite': current[:80], 'reason': str(error)[:2048]}, ensure_ascii=True)) from error
    finally:
        controller.run_command = previous
    if not (code == 0 and not cancelled and len(observations) == len(suites)
            and [entry['name'] for entry in observations] == names
            and all(entry['status'] == 'passed' for entry in observations)):
        failed = [entry for entry in observations if entry['status'] != 'passed']
        detail = {'exit_code': code, 'cancelled': bool(cancelled), 'selected': len(suites), 'observed': len(observations),
                  'failed': [{'name': entry['name'][:80], 'status': entry['status'],
                              'reason': entry['message'][:120]} for entry in failed[:64]],
                  'encoded_output_tails': [entry['output'][-512:] for entry in failed[:8]]}
        raise host.Unavailable('shared-host suite failure: ' + json.dumps(detail, sort_keys=True, ensure_ascii=True))
    return [{'name': entry['name'], 'status': entry['status']} for entry in observations]


def check_batch(batch, registry, cancelled, installed, *, names=None, admit=None, preexecution_unavailable=None,
                suite_workers=1):
    sandbox.verify_snapshot(batch.candidate, batch.snapshot)
    host.require(sandbox._files(batch.policy) == batch.projection, 'protected shared-host projection changed')
    try:
        before = batch.probe(cancelled)
    except (host.Unavailable, sandbox.SandboxUnavailable) as error:
        if preexecution_unavailable is None or cancelled:
            raise
        # This first probe ran no candidate suite. Descendants still must be
        # empty before the caller can select its existing actual fallback.
        batch.empty()
        raise preexecution_unavailable('selected original environment capture is unavailable') from error
    # Runtime admission happens before any candidate suite. An unsupported E
    # can select nonreusable execution; a started suite failure never can.
    if admit is not None:
        admit(before)
    options = {'suite_workers': suite_workers} if suite_workers != 1 else {}
    statuses = run_suites(batch, registry, cancelled, report=batch.protected / 'suites.xml', names=names, **options)
    batch.empty()
    after = batch.probe(cancelled)
    host.require(before == after, 'full protected shared-host environment changed after kernel cleanup')
    sandbox.verify_snapshot(batch.candidate, batch.snapshot)
    host.require(sandbox._files(batch.policy) == batch.projection
                 and prepared_identity(identity_roots(batch.prepared),
                                       external_inputs=prepared_external_inputs(batch.prepared)) == installed,
                 'readonly prepared inputs changed across shared-host batch')
    return statuses, before, after


def run_host(*, profile=FULL_ENVIRONMENT):
    host.require(type(profile) is str and profile in {FULL_ENVIRONMENT, ci_profile.PROFILE},
                 'unsupported manual shared-host profile')
    quick = profile == ci_profile.PROFILE
    runner = host.host_context(os.environ)
    release = Path('/etc/os-release').read_text(encoding='ascii')
    host.require('ID=ubuntu' in release and 'VERSION_ID="24.04"' in release,
                 'actual shared-host OS is outside its supported profile')
    for executable in ('/usr/bin/bwrap', '/usr/bin/unshare', '/usr/bin/python3', '/usr/bin/sudo'):
        info = Path(executable).stat()
        host.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
                     'required fixed shared-host tool is missing or mutable')
        if executable == '/usr/bin/bwrap':
            host.require(not info.st_mode & 0o6000, 'privileged bubblewrap is outside the shared-host profile')
    uid, gid = host.verify_account(runner)
    names = verify_source(os.environ['GITHUB_SHA'])
    prepared = prepared_tools(os.environ, profile=profile) if quick else prepared_tools(os.environ)
    installed = prepared_identity(identity_roots(prepared), external_inputs=prepared_external_inputs(prepared))
    delegated = host.prepare_delegation()
    registry = inputs.load_registry(ROOT / '.github/test-suites.json')
    host.require(all(entry['environment'] == 'host-qt5-qt6' and entry['command'][0] in {'python', 'node'}
                     for entry in registry['suites'].values()), 'shared-host registry has an unsupported profile')
    selected = profile_binding = None
    if quick:
        # A manual fixed inventory has no PR impact claim. Its complete source
        # and definitions still bind the exact actual immutable source. This
        # diagnostic-only path cannot enable the production runtime profile.
        selected = {'suites': list(ci_profile.SUITES), 'reason': 'reviewed-ci-only-inputs',
                    'full_host': False, 'include_platform': False}
        tree = inputs.full_tree(ROOT, os.environ['GITHUB_SHA'])
        profile_binding = ci_profile.diagnostic_selection(selected, tree, tree, registry,
            source=os.environ['GITHUB_SHA'],source_root=ROOT,root=ROOT,
            read_blob=lambda oid:sandbox._git(ROOT,'cat-file','blob',oid,limit=64_000))
    # This fixed profile runs mandatory shared contracts, never npm Browser,
    # standalone browser journeys, platform profiles, native-ctest or app builds.
    cancelled, handlers = [], {}
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            handlers[signum] = signal.signal(signum, lambda number, _frame: cancelled.append(number))
        with tempfile.TemporaryDirectory(prefix='overte-shared-host-') as temporary:
            base = Path(temporary)
            base.chmod(0o755)
            candidate, policy = base / 'candidate', base / 'policy'
            candidate.mkdir(mode=0o755)
            policy.mkdir(mode=0o755)
            snapshot = materialize_source(os.environ['GITHUB_SHA'], candidate)
            projection = project_policy(policy, names, trusted_source=os.environ['GITHUB_SHA'])
            binding = {'source': os.environ['GITHUB_SHA'], 'run_id': int(os.environ['GITHUB_RUN_ID']),
                       'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']), 'profile': PROFILE,
                       'snapshot': snapshot['digest'], 'git_context': snapshot['git_context'],
                       'registry': execution.digest(registry), 'prepared': installed,
                       'projection': execution.digest(projection),
                       'outside_namespaces': {name: os.stat('/proc/self/ns/' + name).st_ino
                                              for name in ('user', 'mnt', 'pid', 'net', 'ipc', 'uts')}}
            if quick:
                binding.update(runtime_profile=ci_profile.PROFILE, selection=selected,
                               profile_binding=profile_binding, diagnostic_only=True)
            sandbox._write_source(policy, 'context.json', sandbox._canonical({'shared_host': binding}))
            projection = sandbox._files(policy)
            environment = {name: os.environ[name] for name in ('ImageOS', 'ImageVersion', 'RUNNER_ENVIRONMENT')}
            batch = Batch(base, candidate, policy, snapshot, projection, binding, prepared, delegated, uid, gid, environment)
            # The parent retains one immutable snapshot/projection inventory.
            # Each namespace mounts those same root-owned paths readonly and
            # only its own fresh scratch writable. No per-suite 600MB rehash.
            if quick:
                statuses, before, after = check_batch(batch, registry, cancelled, installed,
                                                       names=list(ci_profile.SUITES))
            else:
                statuses, before, after = check_batch(batch, registry, cancelled, installed)
            host.require(not cancelled, 'shared-host diagnostic was cancelled')
            result = {'schema': 1, 'status': 'shared-host-diagnostic-passed', 'authority': 'none',
                      'production_qualified': False, 'reusable': False, 'profile': PROFILE, 'binding': binding,
                      'suites': statuses, 'environment_before': execution.digest(before),
                      'environment_after': execution.digest(after), 'kernel_scope_proofs': len(batch.proofs)}
            execution._write_receipt(batch.protected / 'diagnostic.json', result)
            return result
    finally:
        for signum, handler in handlers.items():
            signal.signal(signum, handler)


def run_host_ci37():
    """Fixed manual CI37 diagnostic; no producer or activation authority."""
    return run_host(profile=ci_profile.PROFILE)
