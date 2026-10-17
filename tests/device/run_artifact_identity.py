#!/usr/bin/env python3
"""Run only the ArtifactIdentity unittest directory in a closed Linux view.

This is a test execution boundary, not an evidence issuer or a general launcher.
The source view has no checkout metadata, iOS files or outer-workspace alias.
All Python entries, including the tests' existing CLI subprocesses, skip site
startup and use the same explicit interpreter/package roots.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import stat
import subprocess
import sys
import sysconfig
import tempfile


ROOT = (Path('/work') if Path(__file__) == Path('/overte-artifact-runner.py')
        else Path(__file__).resolve().parents[2])
VIEW = Path('/work')
SELF = Path('/overte-artifact-runner.py')
CONTEXT = Path('/overte-artifact-context.json')
PYTHON_ALIAS = '/overte-artifact-python'
DIRECTORY = 'tests/device/schema/artifact-identity'
RUNNER = 'tests/run-unittest-suite.py'
LAUNCHER = 'tests/device/run_artifact_identity.py'
DIRECTORIES = (DIRECTORY, 'provenance', 'tools/sbom')
CLI = frozenset(('tools/sbom/verify-artifact-identity.py',
                 'tools/sbom/verify-sbom-pair.py',
                 'tools/sbom/verify-conan-phase.py',
                 'tools/sbom/join-conan-sources.py'))
LIMIT_FILES, LIMIT_BYTES = 512, 8 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'),
                       allow_nan=False) + '\n').encode()


def stable_identity(value):
    # Reading an ordinary file may legitimately update only access time.
    # Every source identity/content-relevant stat field remains checked.
    return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_uid, value.st_gid, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def ordinary(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode) and value.st_nlink == 1
            and stat.S_IMODE(value.st_mode) in (0o444, 0o555, 0o644, 0o755),
            'ArtifactIdentity source must be an ordinary non-aliased file')
    return value


def source_files(root):
    """Enumerate real inputs; no directory bind can smuggle an extra alias."""
    entries = [RUNNER, LAUNCHER]
    for relative in DIRECTORIES:
        directory = root / relative
        require(stat.S_ISDIR(directory.lstat().st_mode),
                'ArtifactIdentity source directory is absent or aliased')
        for parent, directories, names in os.walk(directory, followlinks=False):
            directories.sort()
            for name in tuple(directories):
                path = Path(parent) / name
                require(stat.S_ISDIR(path.lstat().st_mode) and name != '.git',
                        'ArtifactIdentity source directory is aliased')
                if name == '__pycache__':
                    directories.remove(name)
            for name in sorted(names):
                # Existing untracked bytecode must never shadow the actual .py
                # inputs, including on an ordinary writable developer checkout.
                if name.endswith(('.pyc', '.pyo')):
                    continue
                entries.append(str((Path(parent) / name).relative_to(root)))
    require(len(entries) <= LIMIT_FILES and len(set(entries)) == len(entries),
            'ArtifactIdentity source membership exceeds its fixed bound')
    result, total = [], 0
    for relative in sorted(entries):
        path = root / relative
        metadata = ordinary(path)
        total += metadata.st_size
        require(total <= LIMIT_BYTES, 'ArtifactIdentity source exceeds its byte bound')
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(descriptor, 'rb') as stream:
            require(stable_identity(os.fstat(stream.fileno())) == stable_identity(metadata),
                    'ArtifactIdentity source changed before reading')
            body = stream.read(metadata.st_size + 1)
            require(len(body) == metadata.st_size
                    and stable_identity(os.fstat(stream.fileno())) == stable_identity(metadata)
                    and stable_identity(path.lstat()) == stable_identity(metadata),
                    'ArtifactIdentity source changed while reading')
        result.append({'path': relative, 'mode': stat.S_IMODE(metadata.st_mode),
                       'size': len(body), 'sha256': hashlib.sha256(body).hexdigest()})
    return result


def runtime_context(root):
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            'ArtifactIdentity requires isolated Python without site startup')
    executable = Path(sys.executable).absolute()
    require(executable.name in ('python', 'python3',
                               f'python{sys.version_info.major}.{sys.version_info.minor}'),
            'ArtifactIdentity interpreter alias is unsupported')
    base = Path(sys.base_prefix).resolve(strict=True)
    environment = executable.parent.parent
    if not (environment / 'pyvenv.cfg').is_file():
        environment = base
    else:
        values = {}
        for line in (environment / 'pyvenv.cfg').read_text().splitlines():
            if '=' in line:
                key, value = line.split('=', 1)
                require(key.strip() not in values, 'ArtifactIdentity venv configuration is duplicated')
                values[key.strip()] = value.strip()
        require(values.get('include-system-site-packages') == 'false',
                'ArtifactIdentity venv must exclude system packages')
    environment = environment.resolve(strict=True)
    roots = sorted(set((base, environment)), key=str)
    require(all(path != Path('/') and not path.is_relative_to(root)
                and not root.is_relative_to(path) for path in roots),
            'ArtifactIdentity runtime must be disjoint from repository inputs')
    paths = list(sys.path)
    require(paths and all(type(value) is str and Path(value).is_absolute()
                         and '..' not in Path(value).parts
                         and any(Path(value).is_relative_to(prefix) for prefix in roots)
                         for value in paths),
            'ArtifactIdentity initial Python lookup escapes its runtime roots')
    # Do not call site.addsitedir: it executes .pth files. Packages and their
    # resource directories remain available through normal explicit lookup.
    for scheme in ('purelib', 'platlib'):
        package = Path(sysconfig.get_path(scheme, vars={'base': str(environment),
                                                       'platbase': str(environment)}))
        require(package.is_dir() and package.is_relative_to(environment),
                'ArtifactIdentity package root is unavailable')
        paths.append(str(package))
    return {'schema': 1, 'python': str(executable), 'paths': list(dict.fromkeys(paths)),
            'roots': [str(path) for path in roots], 'library': str(base / 'lib')}


def launch(root):
    require(sys.platform == 'linux', 'ArtifactIdentity confinement requires Linux')
    root = root.resolve(strict=True)
    before = source_files(root)
    context = runtime_context(root)
    with tempfile.TemporaryDirectory(prefix='overte-artifact-identity-') as temporary:
        directory = Path(temporary)
        context_path = directory / 'context.json'
        context_path.write_bytes(canonical(context))
        context_path.chmod(0o444)
        alias = directory / 'python'
        # This fixed alias is also sys.executable inside the test process. Every
        # existing Python CLI subprocess consequently repeats -I/-S/-B.
        alias.write_text('#!/bin/sh\nexec ' + shlex.quote(context['python']) +
                         ' -I -S -B /overte-artifact-runner.py --python "$@"\n')
        alias.chmod(0o555)
        argv = ['/usr/bin/bwrap', '--unshare-user', '--unshare-pid', '--unshare-net',
                '--unshare-ipc', '--unshare-uts', '--new-session', '--die-with-parent',
                '--cap-drop', 'ALL', '--clearenv', '--ro-bind', '/usr', '/usr']
        for name in ('bin', 'sbin', 'lib', 'lib64'):
            argv += ['--symlink', 'usr/' + name, '/' + name]
        argv += ['--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
                 '--tmpfs', '/home', '--dir', '/home/artifact-identity']
        if Path('/etc/ld.so.cache').is_file():
            argv += ['--ro-bind', '/etc/ld.so.cache', '/etc/ld.so.cache']
        for value in context['roots']:
            if not Path(value).is_relative_to('/usr'):
                argv += ['--ro-bind', value, value]
        parents = {Path('/work')}
        for relative in DIRECTORIES:
            target = VIEW / relative
            parents.add(target)
            parents.update(parent for parent in target.parents if parent.is_relative_to(VIEW))
        for item in before:
            parents.update(parent for parent in (VIEW / item['path']).parents
                           if parent.is_relative_to(VIEW))
        for path in sorted(parents, key=lambda value: (len(value.parts), str(value))):
            argv += ['--dir', str(path)]
        for item in before:
            argv += ['--ro-bind', str(root / item['path']), str(VIEW / item['path'])]
        argv += ['--ro-bind', str(Path(__file__).resolve()), str(SELF),
                 '--ro-bind', str(context_path), str(CONTEXT),
                 '--ro-bind', str(alias), PYTHON_ALIAS]
        environment = {'HOME': '/home/artifact-identity', 'TMPDIR': '/tmp',
                       'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                       'LD_LIBRARY_PATH': context['library']}
        for key, value in sorted(environment.items()):
            argv += ['--setenv', key, value]
        argv += ['--chdir', '/work', '--', context['python'], '-I', '-S', '-B',
                 str(SELF), '--suite']
        print('ArtifactIdentity confined-v1 source=' + hashlib.sha256(canonical(before)).hexdigest()
              + ' runtime=' + hashlib.sha256(canonical(context)).hexdigest(), flush=True)
        completed = subprocess.run(argv, stdin=subprocess.DEVNULL, close_fds=True, check=False)
    require(source_files(root) == before, 'ArtifactIdentity source changed during execution')
    return completed.returncode


def inside(arguments):
    require(Path(__file__) == SELF and Path.cwd() == VIEW,
            'ArtifactIdentity internal entry requires its fixed namespace paths')
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode,
            'ArtifactIdentity child Python startup is unsupported')
    context = json.loads(CONTEXT.read_bytes())
    require(set(context) == {'schema', 'python', 'paths', 'roots', 'library'}
            and context['schema'] == 1 and type(context['paths']) is list
            and context['paths'] and all(type(value) is str and Path(value).is_absolute()
                                        and any(Path(value).is_relative_to(root)
                                                for root in context['roots'])
                                        for value in context['paths']),
            'ArtifactIdentity child context is malformed')
    sys.path[:] = context['paths']
    sys.executable = PYTHON_ALIAS
    if arguments == ['--suite']:
        sys.argv = [str(VIEW / RUNNER), str(VIEW / DIRECTORY)]
        runpy.run_path(sys.argv[0], run_name='__main__')
    else:
        require(len(arguments) >= 2 and arguments[0] == '--python',
                'ArtifactIdentity internal command is unsupported')
        script = Path(arguments[1])
        require(script.is_absolute() and str(script.relative_to(VIEW)) in CLI
                and script == script.resolve(strict=True),
                'ArtifactIdentity Python child is outside its fixed CLI list')
        sys.argv = [str(script), *arguments[2:]]
        runpy.run_path(sys.argv[0], run_name='__main__')
    return 0


def main():
    if Path(__file__) == SELF:
        return inside(sys.argv[1:])
    require(not sys.argv[1:], 'ArtifactIdentity launcher accepts no caller options')
    return launch(ROOT)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        # Fixed reason only; never echo candidate source text or arbitrary paths.
        print('ArtifactIdentity confined execution unavailable: ' + type(error).__name__,
              file=sys.stderr)
        raise SystemExit(1)
