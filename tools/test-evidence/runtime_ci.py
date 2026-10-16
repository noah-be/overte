#!/usr/bin/env python3
"""Actual CI37 environment identity; never an execution receipt.

This separate profile does not project, relabel or weaken the full Qt profile.
Only fixed read-only identity queries run here. Unsupported discovery fails
before a caller may start the quick owner. No consumer VM needs this capture.
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import os
from pathlib import Path
import platform
import re
import resource
import stat
import subprocess
import sys
import sysconfig
import time

import ci_profile
import attested
import inputs
import runtime

ROOT = Path(__file__).resolve().parents[2]
VENV = Path('/opt/overte-ci/venv')
_HASH = re.compile(r'sha256:[0-9a-f]{64}\Z')
_TOOLS = {'bash': ('bash', '--version'), 'git': ('git', '--version'),
    'node': ('node', '--version'), 'cmake': ('cmake', '--version'),
    'ctest': ('ctest', '--version'), 'ninja': ('ninja', '--version'),
    'make': ('make', '--version'), 'gmake': ('gmake', '--version'), 'cxx': ('c++', '--version'),
    'cc': ('cc', '--version'), 'assembler': ('as', '--version'),
    'linker': ('ld', '--version'), 'ar': ('ar', '--version'),
    'ranlib': ('ranlib', '--version'), 'sha256sum': ('sha256sum', '--version'),
    'env': ('env', '--version'), 'ldd': ('ldd', '--version'),
    'dpkg-query': ('dpkg-query', '--version')}
_CRT = ('crt1.o', 'Scrt1.o', 'rcrt1.o', 'gcrt1.o', 'crti.o', 'crtn.o',
        'crtbegin.o', 'crtbeginS.o', 'crtbeginT.o', 'crtend.o', 'crtendS.o',
        'libstdc++.so', 'libgcc_s.so', 'libgcc.a', 'libc.so', 'libm.so', 'libc_nonshared.a')
_DRIVERS = {'cc': ('c', ('cc1', 'collect2', 'as', 'ld')),
            'cxx': ('c++', ('cc1plus', 'collect2', 'as', 'ld'))}
_HEADER_ROOTS = (Path('/usr/include'), Path('/usr/local/include'))
_LIMITS = ('RLIMIT_AS', 'RLIMIT_CORE', 'RLIMIT_CPU', 'RLIMIT_DATA',
           'RLIMIT_FSIZE', 'RLIMIT_NOFILE', 'RLIMIT_NPROC', 'RLIMIT_STACK')
_FILES = ('tools/test-evidence/ci_profile.py', 'tools/test-evidence/runtime_ci.py',
          '.github/ci37-runtime.json', ci_profile.PINNED_SOURCE)


class CIEnvironmentError(ValueError):
    """Existing nonreusable/full execution must own this unsupported profile."""


def require(value, message):
    if not value:
        raise CIEnvironmentError(message)


def digest(value):
    return 'sha256:' + hashlib.sha256(inputs._canonical(value)).hexdigest()


def _fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), 'unsupported CI37 identity fields')


def _file(path):
    try:
        path = Path(path).resolve(strict=True)
        info = path.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and info.st_size <= 256 * 1024 ** 2, 'CI37 runtime input is not protected')
        return {'mode': stat.S_IMODE(info.st_mode), 'size': info.st_size,
                'sha256': runtime._file_digest(path)}
    except OSError as error:
        raise CIEnvironmentError('CI37 runtime input is unavailable') from error


def _path(value, roots=(Path('/usr'), Path('/opt/hostedtoolcache'))):
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts, 'unsupported CI37 runtime path')
    try:
        path = path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise CIEnvironmentError('unresolved CI37 runtime path') from error
    require(any(path.is_relative_to(root) for root in roots), 'CI37 runtime path escapes readonly roots')
    return path


def _inventory(root, allowed, *, deadline=None, directory_roots=None):
    """Bound complete content, directory membership, modes and resolved aliases."""
    deadline = time.monotonic() + 120 if deadline is None else deadline
    root = Path(root)
    directory_roots = allowed if directory_roots is None else directory_roots
    info = root.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022,
            'CI37 inventory root is mutable or aliased')
    rows, size = [], 0
    def failed(_error):
        raise CIEnvironmentError('CI37 runtime inventory cannot enumerate every input')
    for directory, children, names in os.walk(root, followlinks=False, onerror=failed):
        children.sort()
        for name in sorted([*children, *names]):
            require(time.monotonic() < deadline and len(rows) < 150_000,
                    'CI37 runtime inventory exceeds its bound')
            path = Path(directory)/name
            info = path.lstat()
            require(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or not info.st_mode & 0o022),
                    'CI37 runtime inventory contains mutable files')
            if stat.S_ISLNK(info.st_mode):
                target = _path(path, allowed)
                value = {'alias': os.readlink(path), 'target': str(target)}
                # An alias to a file also binds its actual bytes. Directory
                # targets must have their complete inventory in this union.
                if target.is_file():
                    value['referent'] = _file(target)
                else:
                    require(target.is_dir() and any(target.is_relative_to(bound) for bound in directory_roots),
                            'CI37 directory alias escapes the complete inventory union')
            elif stat.S_ISDIR(info.st_mode):
                value = {'directory': True, 'mode': stat.S_IMODE(info.st_mode)}
            else:
                value = _file(path)
                size += value['size']
                require(size <= 4 * 1024 ** 3, 'CI37 inventory exceeds its byte bound')
            rows.append([path.relative_to(root).as_posix(), value])
    return {'entries': len(rows), 'bytes': size, 'digest': digest(rows)}


def _query(path, *arguments, empty=False, search=False):
    """Query fixed protected tools with no candidate configuration or output path."""
    environment = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'HOME': '/nonexistent'}
    if os.environ.get('LD_LIBRARY_PATH'):
        environment['LD_LIBRARY_PATH'] = os.environ['LD_LIBRARY_PATH']
    try:
        result = subprocess.run([str(path), *arguments], input='', cwd='/', env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise CIEnvironmentError('fixed CI37 identity query failed') from error
    require(len(result.stdout.encode()) + len(result.stderr.encode()) <= 2_000_000,
            'CI37 identity query exceeds its byte bound')
    value = result.stderr if search else result.stdout
    require(empty or bool(value.strip()), 'CI37 identity query returned no identity')
    return value.strip()


def _flags():
    allowed = {'PATH', 'HOME', 'TMPDIR', 'PWD', 'VIRTUAL_ENV', 'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ',
        'LD_LIBRARY_PATH', 'PKG_CONFIG_PATH', *runtime._FIXED_GIT_OVERRIDES,
        'GIT_CONFIG_KEY_2', 'GIT_CONFIG_VALUE_2', 'ImageOS', 'ImageVersion', 'RUNNER_ENVIRONMENT'}
    # A fixed clearenv namespace has no reason to inherit arbitrary variables,
    # including unknown future compiler/Make/Node/Git startup configuration.
    require(set(os.environ) <= allowed, 'unsupported CI37 lookup or process override')
    require(not sys._xoptions, 'unsupported CI37 Python options')
    expected = {**runtime._FIXED_GIT_OVERRIDES, 'GIT_CONFIG_COUNT': '3',
        'GIT_CONFIG_KEY_2': 'safe.directory', 'GIT_CONFIG_VALUE_2': '/work'}
    require({key: value for key, value in os.environ.items() if key.startswith('GIT_CONFIG')} == expected,
            'CI37 requires its exact protected Git process profile')
    python = _path(sys.base_prefix)
    for name, suffix in (('LD_LIBRARY_PATH', 'lib'), ('PKG_CONFIG_PATH', 'lib/pkgconfig')):
        require(os.environ.get(name) == str(python/suffix), 'unsupported CI37 library or package lookup')
    require(os.environ.get('PWD') == os.getcwd() == '/work'
            and os.environ.get('HOME') == '/home/candidate' and os.environ.get('TMPDIR') == '/tmp'
            and os.environ.get('VIRTUAL_ENV') == str(VENV), 'CI37 process roots differ from protected profile')
    node = _path(runtime._checked_executable('node')).parent.parent
    require(os.environ.get('PATH') == ':'.join((str(VENV/'bin'), str(node/'bin'), '/usr/bin', '/bin')),
            'CI37 executable lookup is not its fixed prepared profile')
    require(os.environ.get('LANG') == 'C.UTF-8' and os.environ.get('LC_ALL') == 'C.UTF-8'
            and not os.environ.get('LC_CTYPE') and not os.environ.get('TZ'), 'unsupported CI37 locale')
    return {'git_process_overrides': 'maintenance-disabled-safe-work', 'locale': 'C.UTF-8',
            'path': 'prepared-python-node-system', 'library_lookup': 'prepared-python-base',
            'home': '/home/candidate', 'cwd': '/work', 'tmpdir': '/tmp',
            'compiler_overrides': 'absent', 'qt_overrides': 'absent', 'java_overrides': 'absent'}


def _system_packages():
    source = _query(runtime._checked_executable('dpkg-query'), '--show',
                    '--showformat=${binary:Package}\t${Version}\t${Status}\n')
    result = {}
    for line in source.splitlines():
        fields = line.split('\t')
        require(len(fields) == 3, 'unsupported CI37 system package record')
        name, version, status = fields
        if status != 'install ok installed':
            continue
        require(re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?', name)
            and re.fullmatch(r'[A-Za-z0-9.+:~_-]+', version) and name not in result,
            'ambiguous CI37 system package inventory')
        result[name] = version
    require(0 < len(result) <= 10_000, 'incomplete CI37 system package inventory')
    return dict(sorted(result.items()))


def _tools():
    paths, identities = {}, {}
    for name, (command, *arguments) in _TOOLS.items():
        path = _path(runtime._checked_executable(command))
        if name != 'node':
            require(path.is_relative_to('/usr'), 'unsupported non-system CI37 tool')
        if name == 'gmake':
            # CMake's Unix Makefiles discovery prefers gmake. Resolve the
            # actual alias independently before querying any different driver.
            require(path == paths.get('make'), 'CI37 CMake gmake lookup differs from the bound Make executable')
        version = _query(path, *arguments).splitlines()[0]
        require(0 < len(version) <= 500 and not re.search(r'[\x00-\x1f\x7f]', version),
                'unsupported CI37 tool version')
        paths[name], identities[name] = path, {'version': version, 'file': _file(path)}
    for name, path in (('sh', '/usr/bin/sh'), ('system-python', '/usr/bin/python3')):
        paths[name] = _path(path)
        identities[name] = {'file': _file(paths[name])}
    require(re.fullmatch(r'v22\.[0-9]+\.[0-9]+', identities['node']['version']), 'unsupported CI37 Node version')
    return paths, identities


def _loader(paths):
    libraries = {}
    for path in sorted(set(paths)):
        with path.open('rb') as source:
            header = source.read(20)
            if header[:4] != b'\x7fELF':
                continue  # Known scripts/archives are content-bound separately.
        require(len(header) == 20 and header[4:6] == b'\x02\x01', 'unsupported CI37 ELF class or byte order')
        kind = int.from_bytes(header[16:18], 'little')
        if kind == 1:
            continue  # ET_REL CRT objects have content identity, no runtime ldd.
        require(kind in {2,3}, 'unsupported CI37 ELF object type')
        for line in _query(runtime._checked_executable('ldd'), str(path)).splitlines():
            line = line.strip()
            if re.fullmatch(r'linux-vdso\.so\.1 \(0x[0-9a-f]+\)', line):
                continue  # Actual kernel is independently identified.
            match = re.fullmatch(r'(?:[^\s/]+ => )?(/\S+) \(0x[0-9a-f]+\)', line)
            require(match is not None, 'unresolved or unsupported CI37 ELF loader dependency')
            resolved = _path(match[1])
            libraries[str(resolved)] = _file(resolved)
    require(bool(libraries), 'CI37 native loader closure is unavailable')
    return {'cache': _file('/etc/ld.so.cache'), 'libraries': dict(sorted(libraries.items()))}


def _linker_scripts(files, compiler):
    """Resolve the finite GNU GROUP/INPUT wrappers, never execute linker input."""
    result, readers = {}, []
    for item in files.values():
        path = Path(item['path'])
        with path.open('rb') as source:
            prefix = source.read(8)
            if prefix.startswith(b'\x7fELF') or prefix == b'!<arch>\n':
                continue
            raw = prefix + source.read(1_000_001)
        require(len(raw) <= 1_000_000, 'CI37 linker input exceeds its byte bound')
        try:
            text = raw.decode('ascii')
        except UnicodeError as error:
            raise CIEnvironmentError('unsupported CI37 native linker input') from error
        text = re.sub(r'/\*.*?\*/','',text,flags=re.S)
        output = r'\bOUTPUT_FORMAT\s*\(\s*elf64-x86-64\s*\)'
        require(len(re.findall(output,text)) <= 1, 'ambiguous CI37 linker output format')
        text = re.sub(output,'',text)
        require(re.fullmatch(r'[A-Za-z0-9_./+\-()\s]+',text) and '(' in text,
                'unsupported CI37 linker script grammar')
        names = re.findall(r'[^\s()]+',text)
        references = {}
        for name in names:
            if name in {'GROUP','INPUT','AS_NEEDED'}:
                continue
            if name.startswith('/'):
                resolved = _path(name)
            else:
                require(name == 'libgcc_s.so.1' or name == '-lgcc', 'unknown CI37 linker script lookup')
                resolved = _path(Path(_query(compiler,'-print-file-name='+('libgcc.a' if name=='-lgcc' else name))).resolve(strict=True))
            require(resolved.is_file(), 'unresolved CI37 linker script referent')
            with resolved.open('rb') as source:
                magic = source.read(8)
            require(magic.startswith(b'\x7fELF') or magic == b'!<arch>\n', 'nested or unknown CI37 linker script')
            references[str(resolved)] = _file(resolved)
            readers.append(resolved)
        require(bool(references), 'empty CI37 linker script referent inventory')
        result[str(path)] = references
    return result, readers


def _include_search(compiler, language, gcc):
    search = _query(compiler, '-E', '-x', language, '-v', '-', search=True)
    begin, end = '#include <...> search starts here:', 'End of search list.'
    require(search.count(begin) == search.count(end) == 1, 'CI37 include discovery is incomplete')
    headers = [_path(line.strip()) for line in search.split(begin)[1].split(end)[0].strip().splitlines()]
    require(bool(headers) and all(any(path.is_relative_to(root) for root in (*_HEADER_ROOTS, gcc)) for path in headers),
            'unsupported CI37 compiler include lookup')
    return [str(path) for path in headers]


def _search_directories(compiler):
    directories = {}
    for line in _query(compiler, '-print-search-dirs').splitlines():
        key, separator, values = line.partition(': ')
        require(separator and key in {'install', 'programs', 'libraries'} and key not in directories,
                'unsupported CI37 compiler search directory record')
        entries = []
        for value in values.removeprefix('=').split(':'):
            require(value and Path(value).is_absolute(), 'unknown CI37 compiler search directory')
            path = Path(value).resolve(strict=False)
            require(path.is_relative_to('/usr'), 'CI37 compiler search escapes readonly system inputs')
            require(not path.exists() or path.is_dir(), 'CI37 compiler search contains a non-directory')
            entries.append({'path': str(path), 'present': path.exists()})
        directories[key] = entries
    require(set(directories) == {'install', 'programs', 'libraries'}, 'incomplete CI37 compiler search identity')
    return directories


def _drivers(paths, target, version, gcc, pipeline, directories, files):
    """Identify both actual drivers; alternate unbound native closures fail."""
    result = {}
    for name, (language, programs) in _DRIVERS.items():
        compiler = paths[name]
        require(compiler == _path(compiler) and compiler.parent == Path('/usr/bin'),
                'CI37 compiler driver is outside the supported system installation')
        require(_query(compiler, '-dumpmachine') == target
            and _query(compiler, '-dumpfullversion') == version
            and _query(compiler, '-print-sysroot', empty=True) in ('', '/'),
            'CI37 C/C++ drivers do not share the supported native toolchain')
        specs = _query(compiler, '-dumpspecs').encode('utf-8')
        require(0 < len(specs) <= 1_000_000 and b'\0' not in specs,
                'CI37 compiler specifications are unavailable or oversized')
        resolved = {}
        for program in programs:
            found = _query(compiler, '-print-prog-name='+program)
            path = _path(found if Path(found).is_absolute() else runtime._checked_executable(found))
            require(path == pipeline[program], 'CI37 driver uses an unbound native executable')
            resolved[program] = {'path': str(path), 'file': _file(path)}
        search = _search_directories(compiler)
        require(search == directories, 'CI37 driver uses another native search closure')
        crt = {}
        for item in _CRT:
            found = _query(compiler, '-print-file-name='+item)
            path = _path(Path(found).resolve(strict=True))
            require(str(path) == files[item]['path'], 'CI37 driver uses an unbound CRT or standard library')
            crt[item] = str(path)
        result[name] = {'path': str(compiler), 'file': _file(compiler), 'language': language,
            'specs': {'bytes': len(specs), 'digest': 'sha256:'+hashlib.sha256(specs).hexdigest()},
            'pipeline': resolved, 'include_search': _include_search(compiler, language, gcc),
            'search_directories': search, 'crt_stdlib': crt}
    return result


def _native(paths):
    compiler = paths['cxx']
    target = _query(compiler, '-dumpmachine')
    version = _query(compiler, '-dumpfullversion')
    require(target == 'x86_64-linux-gnu' and re.fullmatch(r'[0-9]+(?:\.[0-9]+)+', version)
        and _query(paths['cc'], '-dumpmachine') == target and _query(paths['cc'], '-dumpfullversion') == version,
        'CI37 requires one supported system GCC C/C++ toolchain')
    require(_query(compiler, '-print-sysroot', empty=True) in ('', '/'), 'unsupported CI37 compiler sysroot')
    pipeline = {}
    for name in ('cc1', 'cc1plus', 'collect2', 'as', 'ld'):
        found = _query(compiler, '-print-prog-name='+name)
        path = _path(found if Path(found).is_absolute() else runtime._checked_executable(found))
        require(path.is_relative_to('/usr'), 'CI37 compiler pipeline escapes system inputs')
        pipeline[name] = path
    require(pipeline['as'] == paths['assembler'] and pipeline['ld'] == paths['linker'],
            'CI37 compiler uses another assembler or linker')
    gcc = pipeline['cc1plus'].parent
    require(gcc == Path('/usr/lib/gcc')/target/version.split('.')[0], 'unsupported CI37 GCC internal root')
    require(all(pipeline[name] == gcc/name for name in ('cc1', 'cc1plus', 'collect2')),
            'CI37 compiler internals escape their complete content inventory')
    # Broad content supersets intentionally avoid an unproven per-suite native
    # package projection. All headers and GCC internals remain conservative.
    cmake_version = re.fullmatch(r'cmake version ([0-9]+\.[0-9]+)\.[0-9]+', _query(paths['cmake'], '--version').splitlines()[0])
    require(cmake_version is not None and paths['cmake'] == Path('/usr/bin/cmake'), 'unsupported CI37 CMake installation')
    modules = Path('/usr/share/cmake-'+cmake_version[1])
    roots = [*_HEADER_ROOTS, gcc, _path(modules)]
    directories = _search_directories(compiler)
    files = {}
    for name in _CRT:
        found = _query(compiler, '-print-file-name='+name)
        path = _path(Path(found).resolve(strict=True))
        require(path.is_relative_to('/usr') and path.is_file(), 'CI37 CRT or standard library is unresolved')
        files[name] = {'path': str(path), 'file': _file(path)}
    scripts, script_readers = _linker_scripts(files,compiler)
    drivers = _drivers(paths, target, version, gcc, pipeline, directories, files)
    return {'family': 'system-gcc', 'target': target, 'version': version,
        'sysroot': {'kind': 'verified-compiler-default', 'root': '/', 'include_search': drivers['cxx']['include_search'],
                    'search_directories': directories},
        'drivers': drivers,
        'pipeline': {name: {'path': str(path), 'file': _file(path)} for name, path in pipeline.items()},
        'content': {str(path): _inventory(path, (*roots, Path('/usr')), directory_roots=roots) for path in roots},
        'crt_stdlib': files, 'linker_scripts': scripts}, [*pipeline.values(), *script_readers,
            *(Path(item['path']) for item in files.values())]


def _process():
    status = {}
    for line in Path('/proc/self/status').read_text().splitlines():
        key, _, value = line.partition(':')
        status[key] = value.strip()
    require(os.getuid() != 0 and status.get('NoNewPrivs') == '1'
        and all(status.get(name) == '0000000000000000' for name in ('CapInh', 'CapPrm', 'CapEff', 'CapBnd', 'CapAmb')),
        'CI37 measurement is outside its unprivileged protected process')
    require(status.get('Umask') == '0022', 'unsupported CI37 process umask')
    return {'no_new_privileges': True, 'capabilities': 'none', 'umask': '0022',
        'limits': {name: list(resource.getrlimit(getattr(resource, name))) for name in _LIMITS}}


def _capture_ci_environment(selection, candidate_tree, trusted_tree, registry, *, root=ROOT, target='main', _diagnostic=False,
                            read_blob=None, source=None, source_root=None, controller_manifest=None):
    """Actual protected BEFORE/AFTER query; no caller may invent optional tools."""
    if _diagnostic:
        binding = ci_profile.diagnostic_selection(selection,candidate_tree,trusted_tree,registry,
            source=source,source_root=source_root,root=root,target=target,read_blob=read_blob,
            controller_manifest=controller_manifest)
    else:
        policy=ci_profile.load_policy(root)
        require(policy.get('generation_kind')!=ci_profile.CONTROLLER_KIND or controller_manifest is not None,
                'CI37 controller capture requires its sealed admitted D manifest')
        binding = ci_profile.validate_selection(selection, candidate_tree, trusted_tree, registry,
            target=target,policy=policy,root=root,read_blob=read_blob,
            controller_manifest=controller_manifest)
    return _measure_ci_environment(binding,root=root)


def _measure_ci_environment(binding, *, root=ROOT):
    """One exact measurement implementation for gated execution and diagnostics."""
    flags = _flags()
    require(platform.python_implementation() == 'CPython' and re.fullmatch(r'3\.12\.[0-9]+', platform.python_version())
            and Path(sys.prefix) == VENV, 'unsupported CI37 prepared Python')
    lookup = runtime._python_lookup_identity()
    required, manifests = runtime._requirement_inventory(root)
    paths, tools = _tools()
    native, pipeline = _native(paths)
    python = _path(sys.base_prefix)
    node = paths['node'].parent.parent
    require(python.is_relative_to('/opt/hostedtoolcache/Python') and node.is_relative_to('/opt/hostedtoolcache/node'),
            'CI37 prepared roots are not versioned hosted installations')
    roots = (VENV, python, node)
    library = _path(Path(sysconfig.get_config_var('LIBDIR'))/sysconfig.get_config_var('LDLIBRARY'))
    result = {'schema': ci_profile.ENVIRONMENT_SCHEMA, 'profile': ci_profile.PROFILE, 'selection': binding,
        'os': runtime._os_identity(), 'python': {'implementation': 'CPython', 'version': platform.python_version(),
            'executable': _file(_path(sys.executable)), 'library': _file(library),
            'flags': {name: getattr(sys.flags, name) for name in ('debug', 'inspect', 'interactive', 'optimize',
                'dont_write_bytecode', 'no_user_site', 'no_site', 'ignore_environment', 'verbose', 'bytes_warning',
                'quiet', 'hash_randomization', 'isolated', 'dev_mode', 'utf8_mode', 'warn_default_encoding', 'safe_path')},
            'packages': runtime._python_packages(required), 'process_lookup': lookup},
        'prepared': {str(path): _inventory(path, (*roots, Path('/usr')), directory_roots=roots) for path in roots},
        'tools': tools, 'native': native, 'loader': _loader([*paths.values(), *pipeline, _path(sys.executable), library]),
        'system_packages': _system_packages(), 'process': _process(), 'flags': flags,
        'trusted_execution': {**runtime._controller_file_hashes(manifests, root),
            **{path: runtime._file_digest(Path(root)/path) for path in _FILES}}}
    inputs._environment(result)
    require(len(inputs._canonical(result)) <= 2_000_000, 'CI37 identity exceeds its byte bound')
    return result


def _file_identity(value):
    _fields(value, {'mode', 'size', 'sha256'})
    require(type(value['mode']) is int and 0 < value['mode'] <= 0o777 and not value['mode'] & 0o022
        and type(value['size']) is int and 0 <= value['size'] <= 256 * 1024 ** 2
        and type(value['sha256']) is str and _HASH.fullmatch(value['sha256']), 'incomplete CI37 file identity')


def _inventory_identity(value, *, allow_empty=False):
    _fields(value, {'entries', 'bytes', 'digest'})
    require(type(value['entries']) is int and (0 if allow_empty else 1) <= value['entries'] <= 150_000
        and type(value['bytes']) is int and 0 <= value['bytes'] <= 4 * 1024 ** 3
        and type(value['digest']) is str and _HASH.fullmatch(value['digest']), 'incomplete CI37 content inventory')
    require(value['entries'] != 0 or value['bytes'] == 0 and value['digest'] == digest([]),
            'empty CI37 content inventory does not identify the actual empty directory')


def _recorded_path(value, *, prepared=False):
    # Pure original-E admission: never inspect these paths on a consumer VM.
    require(type(value) is str and value.startswith('/') and '\x00' not in value
        and '..' not in Path(value).parts and str(Path(value)) == value,
        'invalid recorded CI37 path')
    require(Path(value).is_relative_to('/usr') or prepared and (
        Path(value).is_relative_to('/opt/hostedtoolcache') or Path(value).is_relative_to(VENV)),
        'unsupported recorded CI37 path')


def _validate_environment(environment, qualified_at, expires_at, now, selection,
                         candidate_tree, trusted_tree, registry, *, root=ROOT, target='main', read_blob=None):
    """Admit ORIGINAL CI37 E only; provenance and before/after proof are external.

    No tool probe, installation or consumer environment capture occurs here.
    Changed runtime/source context cannot inherit this separate profile.
    """
    require(not isinstance(environment,dict) or not isinstance(environment.get('selection'),dict)
        or environment['selection'].get('kind') != ci_profile.DIAGNOSTIC_KIND,
        'manual diagnostic source binding cannot enter production admission')
    policy = ci_profile.load_policy(root)
    binding = ci_profile.validate_selection(selection, candidate_tree, trusted_tree, registry,target=target,policy=policy,root=root,
                                            read_blob=read_blob)
    require(type(now) is datetime and now.tzinfo is not None and now.utcoffset().total_seconds() == 0,
            'CI37 admission requires an independent UTC clock')
    def stamp(value):
        require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', value),
                'invalid CI37 qualification time')
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    qualified, expires = stamp(qualified_at), stamp(expires_at)
    require(stamp(policy['not_before']) <= qualified <= now < expires
        and 0 < (expires-qualified).total_seconds() <= policy['max_age_seconds'],
        'CI37 original environment is expired or outside its reviewed epoch')
    inputs._environment(environment)
    require(len(inputs._canonical(environment)) <= 2_000_000, 'CI37 recorded identity exceeds its byte bound')
    _fields(environment, {'schema', 'profile', 'selection', 'os', 'python', 'prepared', 'tools',
        'native', 'loader', 'system_packages', 'process', 'flags', 'trusted_execution'})
    require(type(environment['schema']) is int and environment['schema'] == ci_profile.ENVIRONMENT_SCHEMA
        and environment['profile'] == ci_profile.PROFILE and environment['selection'] == binding,
        'CI37 recorded profile or finite owner differs from current selection')
    operating = environment['os']
    _fields(operating, {'architecture','distribution','kernel','namespace','runner','timezone_digest','version'})
    require((operating['architecture'],operating['distribution'],operating['version']) == ('x86_64','ubuntu','24.04')
        and type(operating['kernel']) is str and re.fullmatch(r'[A-Za-z0-9._+-]{1,200}', operating['kernel'])
        and type(operating['timezone_digest']) is str and _HASH.fullmatch(operating['timezone_digest']),
        'unsupported recorded CI37 OS identity')
    _fields(operating['runner'], {'ImageOS','ImageVersion','RUNNER_ENVIRONMENT'})
    require(operating['runner']['ImageOS'] == 'ubuntu24' and operating['runner']['RUNNER_ENVIRONMENT'] == 'github-hosted'
        and type(operating['runner']['ImageVersion']) is str and re.fullmatch(r'[0-9]+(?:\.[0-9]+)+',operating['runner']['ImageVersion']),
        'unsupported recorded CI37 image identity')
    _fields(operating['namespace'], {'apparmor_restrict_unprivileged_userns','max_user_namespaces'})
    require(operating['namespace']['apparmor_restrict_unprivileged_userns'] == '0'
        and type(operating['namespace']['max_user_namespaces']) is str
        and re.fullmatch(r'[0-9]{1,20}', operating['namespace']['max_user_namespaces'])
        and int(operating['namespace']['max_user_namespaces']) > 0, 'recorded CI37 namespace support unavailable')
    python = environment['python']
    _fields(python, {'implementation','version','executable','library','flags','packages','process_lookup'})
    require(python['implementation'] == 'CPython' and type(python['version']) is str
        and re.fullmatch(r'3\.12\.[0-9]+',python['version'])
        and inputs._canonical(python['flags']) == inputs._canonical(attested._PYTHON_FLAGS)
        and python['process_lookup'] == {'aliases':['python','python3'],'include_system_site_packages':False,
            'mode':'controller-virtualenv','user_site_enabled':False}, 'unsupported recorded CI37 Python lookup')
    _file_identity(python['executable']); _file_identity(python['library'])
    required, manifests = runtime._requirement_inventory(root)
    packages = python['packages']
    require(type(packages) is dict and 0 < len(packages) <= 2_000 and all(
        type(name) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,199}',name) and type(version) is str
        and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+!-]{0,199}',version) for name,version in packages.items())
        and all(packages.get(name) == version for name,version in required.items()), 'incomplete recorded CI37 Python packages')
    prepared = environment['prepared']
    require(type(prepared) is dict and len(prepared) == 3 and str(VENV) in prepared,
            'CI37 prepared identity must contain the actual venv, Python and Node roots')
    require(set(prepared) == {str(VENV), '/opt/hostedtoolcache/Python/'+python['version']+'/x64',
        '/opt/hostedtoolcache/node/'+environment['tools'].get('node',{}).get('version','').removeprefix('v')+'/x64'},
        'unsupported recorded CI37 prepared roots')
    for path,value in prepared.items():
        _recorded_path(path,prepared=True); _inventory_identity(value)
    _fields(environment['tools'], {*_TOOLS,'sh','system-python'})
    for name,value in environment['tools'].items():
        _fields(value, {'file'} if name in {'sh','system-python'} else {'version','file'})
        _file_identity(value['file'])
        if 'version' in value:
            require(type(value['version']) is str and 0 < len(value['version']) <= 500
                and not re.search(r'[\x00-\x1f\x7f]',value['version']), 'invalid recorded CI37 tool identity')
    require(re.fullmatch(r'v22\.[0-9]+\.[0-9]+',environment['tools']['node']['version']), 'unsupported recorded CI37 Node')
    require(environment['tools']['gmake'] == environment['tools']['make'],
            'recorded CI37 CMake gmake differs from its bound Make executable')
    native = environment['native']
    _fields(native, {'family','target','version','sysroot','pipeline','content','crt_stdlib','linker_scripts','drivers'})
    require(native['family'] == 'system-gcc' and native['target'] == 'x86_64-linux-gnu'
        and type(native['version']) is str and re.fullmatch(r'[0-9]+(?:\.[0-9]+)+',native['version']), 'unsupported recorded CI37 compiler')
    require(all(environment['tools'][name]['version'].endswith(' '+native['version']) for name in ('cc','cxx')),
            'recorded CI37 driver versions differ from native toolchain')
    _fields(native['sysroot'], {'kind','root','include_search','search_directories'})
    require(native['sysroot']['kind'] == 'verified-compiler-default' and native['sysroot']['root'] == '/'
        and type(native['sysroot']['include_search']) is list and bool(native['sysroot']['include_search']),
        'unidentified recorded CI37 sysroot')
    for path in native['sysroot']['include_search']: _recorded_path(path)
    _fields(native['sysroot']['search_directories'], {'install','programs','libraries'})
    for entries in native['sysroot']['search_directories'].values():
        require(type(entries) is list and bool(entries), 'incomplete recorded CI37 compiler search')
        for item in entries:
            _fields(item, {'path','present'}); _recorded_path(item['path'])
            require(type(item['present']) is bool, 'unknown recorded CI37 search membership')
    _fields(native['pipeline'], {'cc1','cc1plus','collect2','as','ld'})
    for item in native['pipeline'].values():
        _fields(item, {'path','file'}); _recorded_path(item['path']); _file_identity(item['file'])
    gcc = '/usr/lib/gcc/x86_64-linux-gnu/'+native['version'].split('.')[0]
    require(all(native['pipeline'][name]['path'] == gcc+'/'+name for name in ('cc1','cc1plus','collect2'))
        and native['pipeline']['as']['file'] == environment['tools']['assembler']['file']
        and native['pipeline']['ld']['file'] == environment['tools']['linker']['file'],
        'recorded CI37 internal executables differ from the bound native toolchain')
    cmake = re.fullmatch(r'cmake version ([0-9]+\.[0-9]+)\.[0-9]+',environment['tools']['cmake']['version'])
    require(cmake is not None and set(native['content']) == {*map(str,_HEADER_ROOTS),gcc,'/usr/share/cmake-'+cmake[1]},
            'incomplete recorded CI37 native content union')
    for path,value in native['content'].items(): _inventory_identity(value,allow_empty=path=='/usr/local/include')
    _fields(native['crt_stdlib'], _CRT)
    for item in native['crt_stdlib'].values():
        _fields(item, {'path','file'}); _recorded_path(item['path']); _file_identity(item['file'])
    _fields(native['drivers'], _DRIVERS)
    for name,(language,programs) in _DRIVERS.items():
        driver = native['drivers'][name]
        _fields(driver, {'path','file','language','specs','pipeline','include_search','search_directories','crt_stdlib'})
        _recorded_path(driver['path']); _file_identity(driver['file'])
        require(Path(driver['path']).parent == Path('/usr/bin') and driver['language'] == language
            and driver['file'] == environment['tools'][name]['file'], 'recorded CI37 compiler driver differs from its actual tool')
        _fields(driver['specs'], {'bytes','digest'})
        require(type(driver['specs']['bytes']) is int and 0 < driver['specs']['bytes'] <= 1_000_000
            and type(driver['specs']['digest']) is str and _HASH.fullmatch(driver['specs']['digest']),
            'missing recorded CI37 compiler specifications')
        _fields(driver['pipeline'], programs)
        require(all(driver['pipeline'][program] == native['pipeline'][program] for program in programs),
                'recorded CI37 driver uses an unbound native executable')
        require(type(driver['include_search']) is list and 0 < len(driver['include_search']) <= 64,
                'incomplete recorded CI37 driver include search')
        for path in driver['include_search']:
            _recorded_path(path)
            require(any(Path(path).is_relative_to(root) for root in (*_HEADER_ROOTS,Path(gcc))),
                    'recorded CI37 driver header lookup escapes complete content inventories')
        require(driver['search_directories'] == native['sysroot']['search_directories']
            and driver['crt_stdlib'] == {item:value['path'] for item,value in native['crt_stdlib'].items()},
            'recorded CI37 driver uses another native search or CRT closure')
    require(native['drivers']['cxx']['include_search'] == native['sysroot']['include_search'],
            'recorded CI37 C++ include search differs from its bound sysroot')
    require(type(native['linker_scripts']) is dict and 0 < len(native['linker_scripts']) <= len(_CRT),
            'missing recorded CI37 linker script closure')
    for path,references in native['linker_scripts'].items():
        _recorded_path(path)
        require(type(references) is dict and 0 < len(references) <= 20, 'unknown recorded CI37 linker references')
        for target,value in references.items(): _recorded_path(target); _file_identity(value)
    loader = environment['loader']
    _fields(loader, {'cache','libraries'}); _file_identity(loader['cache'])
    require(type(loader['libraries']) is dict and 0 < len(loader['libraries']) <= 2_000, 'incomplete recorded CI37 loader closure')
    for path,value in loader['libraries'].items(): _recorded_path(path,prepared=True); _file_identity(value)
    system = environment['system_packages']
    require(type(system) is dict and 0 < len(system) <= 10_000 and all(type(name) is str
        and re.fullmatch(r'[a-z0-9][a-z0-9+.-]*(?::[a-z0-9-]+)?',name) and type(version) is str
        and re.fullmatch(r'[A-Za-z0-9.+:~_-]+',version) for name,version in system.items()), 'incomplete recorded CI37 system inventory')
    _fields(environment['process'], {'no_new_privileges','capabilities','umask','limits'})
    require(environment['process']['no_new_privileges'] is True and environment['process']['capabilities'] == 'none'
        and environment['process']['umask'] == '0022', 'unsupported recorded CI37 process profile')
    _fields(environment['process']['limits'], _LIMITS)
    require(all(type(value) is list and len(value)==2 and all(type(item) is int and item>=-1 for item in value)
        for value in environment['process']['limits'].values()), 'invalid recorded CI37 process limits')
    require(environment['flags'] == {'git_process_overrides':'maintenance-disabled-safe-work','locale':'C.UTF-8',
        'path':'prepared-python-node-system','library_lookup':'prepared-python-base','home':'/home/candidate',
        'cwd':'/work','tmpdir':'/tmp','compiler_overrides':'absent','qt_overrides':'absent','java_overrides':'absent'},
        'unsupported recorded CI37 runtime flags')
    expected = {**runtime._controller_file_hashes(manifests, root),
                **{path: runtime._file_digest(Path(root)/path) for path in _FILES}}
    require(environment['trusted_execution'] == expected, 'CI37 trusted controller or profile policy changed')
    return {'environment_digest': digest(environment), 'profile': ci_profile.PROFILE, 'selection': binding,
            'policy_digest': ci_profile.policy_identity(policy)}


def capture_ci_environment(selection, candidate_tree, trusted_tree, registry, *, root=ROOT, target='main', read_blob=None,
                           controller_manifest=None):
    """No unknown capture outcome may be represented as a reusable identity."""
    try:
        return _capture_ci_environment(selection,candidate_tree,trusted_tree,registry,root=root,target=target,read_blob=read_blob,
                                       controller_manifest=controller_manifest)
    except CIEnvironmentError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        raise CIEnvironmentError('CI37 capture is unavailable; actual fallback is required') from error


def capture_ci_environment_diagnostic(selection, candidate_tree, trusted_tree, registry, *, root=ROOT, target='main',
                                      read_blob=None, source=None, source_root=None, controller_manifest=None):
    """Fixed source-qualified measurement only; never activation, admission or reuse.

    This dedicated API binds the complete actual immutable source and real
    protected policy, independently of the future production generation. Its
    distinct binding cannot enter ordinary capture or original-E admission.
    """
    try:
        return _capture_ci_environment(selection,candidate_tree,trusted_tree,registry,
            root=root,target=target,_diagnostic=True,read_blob=read_blob,source=source,source_root=source_root,
            controller_manifest=controller_manifest)
    except CIEnvironmentError:
        raise
    except (ValueError,KeyError,TypeError,AttributeError,RuntimeError,OSError,subprocess.SubprocessError) as error:
        raise CIEnvironmentError('CI37 diagnostic measurement is unavailable') from error


def validate_environment(*args, **kwargs):
    """Pure original-E admission, with malformed/unknown inputs failing closed."""
    try:
        return _validate_environment(*args, **kwargs)
    except CIEnvironmentError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError, RuntimeError, OSError) as error:
        raise CIEnvironmentError('CI37 original environment is not admitted') from error


def plan_original_reuse(environment, qualified_at, expires_at, now, original_selection,
                        current_selection, original_tree, current_tree, trusted_tree,
                        registry, results, *, root=ROOT, read_blob=None):
    """Pure same-profile plan, never authentication or a renewed PASS receipt.

    The native adapter must authenticate the ORIGINAL schema3 receipt, owner,
    environment and final whole-receipt hash separately. No full/quick profile
    conversion and no consumer environment measurement occur in this helper.
    """
    admission = validate_environment(environment, qualified_at, expires_at, now,
        current_selection, current_tree, trusted_tree, registry, root=root,read_blob=read_blob)
    original = ci_profile.validate_selection(original_selection, original_tree, trusted_tree, registry,
                                             policy=ci_profile.load_policy(root),root=root,read_blob=read_blob)
    require(original == admission['selection'] and type(results) is dict
        and set(results) == set(ci_profile.SUITES), 'CI37 original and current owners differ')
    selected = {**registry, 'suites': {name:registry['suites'][name] for name in ci_profile.SUITES}}
    plan = inputs.plan_reuse(selected, original_tree, current_tree, results, environment, environment)
    require(not plan['required'] and plan['reused'] == list(ci_profile.SUITES),
            'CI37 original source proof does not cover every currently selected owner')
    return {'kind':'original-ci37-source-plan','reusable':False,'reused_suites':plan['reused'],
        'executed_suites':[], 'original_environment_digest':admission['environment_digest'],
        'original_expires_at':expires_at,'admission':admission}
