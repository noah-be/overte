#!/usr/bin/env python3
"""Prepare/dry-run an isolated QtCore O2 build; build requires a separate command.

Usage after review:
  python3 prepare-phone-qtcore-o2.py dry-run --package-root PACKAGE --sdk SDK \
      --work-dir NEW_DIRECTORY --base-apk INSTALLED_APK_COPY
  python3 prepare-phone-qtcore-o2.py build [the same arguments]

No device installation, dependency resolution, configure, cache cleanup or install.
Only the copied Qt build tree is writable inside the offline container.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import os
import zipfile
import tempfile
import shutil
import shlex

CORE_REL = Path('qtbase/src/corelib')
TARGET = '../../lib/libQt5Core_arm64-v8a.so'
APK_CORE = 'lib/arm64-v8a/libQt5Core_arm64-v8a.so'
# The validated O2 build omits this otherwise unused libc++ implementation vtable.
# No other missing public or weak export is permitted, and APK consumers must not
# import this symbol. This is not a blanket exemption for weak symbols.
OPTIONAL_INTERNAL_EXPORT = '_ZTVNSt6__ndk110__function6__baseIFvvEEE'


def configure(args):
    global PACKAGE, CONAN, ORIGINAL_BUILD, WORK, COPY, CONTROL, CORE, OUTPUT
    global IMAGE, CONTAINER_BUILD, CONTAINER_CONAN, SDK, JOBS, BASE_APK
    PACKAGE = args.package_root.resolve(strict=True)
    if PACKAGE.parent.name != 'b' or PACKAGE.parent.parent.name != 'p':
        raise RuntimeError('Expected Conan package-root layout: CONAN/p/b/PACKAGE')
    CONAN = PACKAGE.parents[2]
    ORIGINAL_BUILD = PACKAGE / 'b/build_folder'
    WORK = args.work_dir.absolute()
    if WORK.is_symlink():
        raise RuntimeError('Work directory must not be a symlink')
    WORK = WORK.resolve()
    SDK = args.sdk.resolve(strict=True)
    BASE_APK = args.base_apk.resolve(strict=True)
    # Do not shadow original caches, sources or tools with the writable bind mount.
    for protected in [CONAN, SDK]:
        if WORK.is_relative_to(protected) or protected.is_relative_to(WORK):
            raise RuntimeError('Work directory must be disjoint from Conan and SDK')
    if BASE_APK.is_relative_to(WORK):
        raise RuntimeError('Baseline APK must be outside the work directory')
    COPY = WORK / 'build_folder'
    CONTROL = WORK / 'control'
    CORE = COPY / CORE_REL
    OUTPUT = COPY / 'qtbase/lib/libQt5Core_arm64-v8a.so'
    text = (ORIGINAL_BUILD / CORE_REL / 'Makefile').read_text()
    match = re.search(r'^QMAKE\s*=\s*(\S+)/qtbase/bin/qmake\s*$', text, re.M)
    if not match:
        raise RuntimeError('Cannot identify configured container build root')
    CONTAINER_BUILD = match.group(1)
    suffix = '/p/b/' + PACKAGE.name + '/b/build_folder'
    if not CONTAINER_BUILD.endswith(suffix):
        raise RuntimeError('Configured paths do not match the supplied package')
    CONTAINER_CONAN = CONTAINER_BUILD[:-len(suffix)]
    # The SDK mount must reproduce the path compiled into this existing Makefile.
    if '/opt/android-sdk/ndk/27.3.13750724/' not in text:
        raise RuntimeError('Expected the validated NDK 27.3.13750724 Makefile')
    if not (SDK / 'ndk/27.3.13750724').is_dir():
        raise RuntimeError('SDK does not contain NDK 27.3.13750724')
    if args.jobs < 1:
        raise RuntimeError('jobs must be positive')
    JOBS = args.jobs
    # Resolve a local immutable image ID; never pull a mutable image implicitly.
    IMAGE = subprocess.check_output(
        ['podman', 'image', 'inspect', '--format', '{{.Id}}', args.image],
        text=True).strip()
    if not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', IMAGE):
        raise RuntimeError('Unexpected container image identity')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def elf_identity(path):
    reader = SDK / 'ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf'
    text = subprocess.check_output([str(reader), '-h', '-d', '--dyn-syms', '--wide', str(path)], text=True)
    def field(name):
        match = re.search(r'^\s*' + name + r':\s*(.+)$', text, re.M)
        if not match:
            raise RuntimeError('ELF lacks ' + name)
        return match.group(1).strip()
    soname = re.findall(r'\(SONAME\).*?\[([^\]]+)\]', text)
    if len(soname) != 1:
        raise RuntimeError('ELF must have exactly one SONAME')
    exports, undefined = [], []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0].endswith(':') and parts[0][:-1].isdigit():
            if parts[6] == 'UND':
                undefined.append(parts[7])
            if parts[4] in ['GLOBAL', 'WEAK'] and parts[5] in ['DEFAULT', 'PROTECTED'] and parts[6] != 'UND':
                # Addresses and function sizes change with optimization/stripping.
                # Exported data sizes remain ABI-relevant.
                exports.append([parts[7], parts[3], parts[4], parts[5],
                                int(parts[2]) if parts[3] in ['OBJECT', 'TLS'] else None])
    if not exports:
        raise RuntimeError('ELF has no public exports')
    return {'class': field('Class'), 'machine': field('Machine'), 'soname': soname[0],
            'needed': sorted(re.findall(r'\(NEEDED\).*?\[([^\]]+)\]', text)),
            'exports': sorted(exports), 'undefined': sorted(undefined)}


def require_same_abi(expected, actual):
    if expected['class'] != 'ELF64' or expected['machine'] != 'AArch64':
        raise RuntimeError('Expected arm64 ELF input')
    if expected['soname'] != 'libQt5Core_arm64-v8a.so':
        raise RuntimeError('Unexpected QtCore SONAME')
    for key in ['class', 'machine', 'soname', 'needed']:
        if expected[key] != actual[key]:
            raise RuntimeError('QtCore ABI mismatch: ' + key)
    before = {entry[0]: entry[1:] for entry in expected['exports']}
    after = {entry[0]: entry[1:] for entry in actual['exports']}
    for exports in [before, after]:
        if OPTIONAL_INTERNAL_EXPORT in exports and exports[OPTIONAL_INTERNAL_EXPORT][1] != 'WEAK':
            raise RuntimeError('Internal export is unexpectedly strong')
    removed, added = sorted(before.keys() - after.keys()), sorted(after.keys() - before.keys())
    if any(name != OPTIONAL_INTERNAL_EXPORT for name in removed + added):
        raise RuntimeError('QtCore ABI mismatch: exports')
    if any(before[name] != after[name] for name in before.keys() & after.keys()):
        raise RuntimeError('QtCore ABI mismatch: exports')
    return {'removed_exports': removed, 'added_exports': added}


def verify_optional_export_consumers(delta):
    if not delta['removed_exports'] and not delta['added_exports']:
        return
    with tempfile.TemporaryDirectory(prefix='phone-qtcore-consumers-') as tmp, zipfile.ZipFile(BASE_APK) as archive:
        for name in archive.namelist():
            if name == APK_CORE or not name.startswith('lib/arm64-v8a/') or not name.endswith('.so'):
                continue
            data = archive.read(name)
            if OPTIONAL_INTERNAL_EXPORT.encode() not in data:
                continue
            path = Path(tmp) / 'consumer.so'
            path.write_bytes(data)
            if OPTIONAL_INTERNAL_EXPORT in elf_identity(path)['undefined']:
                raise RuntimeError('APK library imports omitted QtCore internal export: ' + name)


def packaging_input_abi():
    original = elf_identity(ORIGINAL_BUILD / 'qtbase/lib/libQt5Core_arm64-v8a.so')
    # This is inspection only, not APK extraction into a shared runtime directory.
    with tempfile.TemporaryDirectory(prefix='phone-qtcore-abi-') as tmp:
        candidate = Path(tmp) / 'QtCore.so'
        with zipfile.ZipFile(BASE_APK) as archive:
            if archive.namelist().count(APK_CORE) != 1:
                raise RuntimeError('Baseline APK must contain exactly one arm64 QtCore')
            with archive.open(APK_CORE) as source, candidate.open('wb') as destination:
                shutil.copyfileobj(source, destination)
        delta = require_same_abi(original, elf_identity(candidate))
        verify_optional_export_consumers(delta)
    return original


def compiler_provenance(logfile):
    commands, languages = [], set()
    for line in logfile.read_text().splitlines():
        if not re.match(r'^/opt/android-sdk/ndk/[^ ]+/bin/clang(?:\+\+)?\s', line):
            continue
        tokens = shlex.split(line)
        if '-c' not in tokens and not any(token in ['c-header', 'c++-header'] for token in tokens):
            continue  # Link or preprocessor metadata command.
        optimization = [token for token in tokens if re.fullmatch(r'-O(?:[0-3szg]|fast)', token)]
        if not optimization or optimization[-1] != '-O2':
            raise RuntimeError('Compiler invocation does not end with -O2')
        for index, token in enumerate(tokens):
            definition = tokens[index + 1] if token == '-D' and index + 1 < len(tokens) else token[2:] if token.startswith('-D') else ''
            if definition.split('=')[0] in ['QT_NO_DEBUG', 'NDEBUG']:
                raise RuntimeError('Compiler invocation disables assertions')
        if '-target' not in tokens or tokens[tokens.index('-target') + 1] != 'aarch64-linux-android26':
            raise RuntimeError('Compiler invocation changes target ABI')
        languages.update(token for token in tokens if token in ['c-header', 'c++-header'])
        commands.append(tokens)
    if not commands or languages != {'c-header', 'c++-header'}:
        raise RuntimeError('Compiler log must include both C and C++ PCH rebuilds')
    canonical = sorted(json.dumps(command) for command in commands)
    return {'compile_commands': len(commands), 'pch_languages': sorted(languages),
            'commands_sha256': hashlib.sha256('\n'.join(canonical).encode()).hexdigest(),
            'log_sha256': sha(logfile), 'assertion_defines_disabled': False,
            'optimization': '-O2', 'target': 'aarch64-linux-android26'}


def source_digest():
    """Bind the complete existing patched Qt source, not a nominal upstream tag."""
    source = PACKAGE / 'b/qt5'
    digest = hashlib.sha256()
    count = 0
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source).as_posix()
        if path.is_symlink():
            value = {'path': relative, 'link': os.readlink(path)}
        elif path.is_file():
            value = {'path': relative, 'sha256': sha(path)}
        else:
            continue
        digest.update((json.dumps(value, sort_keys=True) + '\n').encode())
        count += 1
    return {'sha256': digest.hexdigest(), 'entries': count}


def identity():
    paths = [PACKAGE / 'p/conaninfo.txt', PACKAGE / 'p/config.summary',
             PACKAGE / 'p/mkspecs/qconfig.pri', ORIGINAL_BUILD / CORE_REL / 'Makefile',
             ORIGINAL_BUILD / 'qtbase/lib/libQt5Core_arm64-v8a.so']
    with zipfile.ZipFile(BASE_APK) as archive:
        if archive.namelist().count(APK_CORE) != 1:
            raise RuntimeError('Baseline APK must contain exactly one arm64 QtCore')
        with archive.open(APK_CORE) as entry:
            digest = hashlib.sha256()
            for block in iter(lambda: entry.read(1024 * 1024), b''):
                digest.update(block)
    return {
        'inputs': {str(path.relative_to(PACKAGE)): sha(path) for path in paths},
        'source': source_digest(),
        'base_apk_sha256': sha(BASE_APK),
        'base_apk_qtcore_sha256': digest.hexdigest(),
        'tool_sha256': sha(Path(__file__)),
        'ndk_source_properties_sha256': sha(SDK / 'ndk/27.3.13750724/source.properties'),
        'compiler_sha256': sha(SDK / 'ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'),
        'image': IMAGE,
        'package_root': str(PACKAGE), 'sdk': str(SDK), 'jobs': JOBS,
        'base_apk_origin': 'Caller-supplied installed APK copy; verify device identity separately',
    }


def guard():
    info = (PACKAGE / 'p/conaninfo.txt').read_text()
    for required in ['arch=armv8', 'build_type=Debug', 'os=Android', 'multiconfiguration=False']:
        if required not in info.splitlines():
            raise RuntimeError('Unexpected Qt package configuration: ' + required)
    lines = (ORIGINAL_BUILD / CORE_REL / 'Makefile').read_text().splitlines()
    definitions = '\n'.join(line for line in lines if line.startswith(('DEFINES ', 'CFLAGS ', 'CXXFLAGS ')))
    if re.search(r'(?:^|\s)-D\s*(?:QT_NO_DEBUG|NDEBUG)(?:=|\s|$)', definitions):
        raise RuntimeError('Original QtCore unexpectedly disables assertions')
    for variable in ['CFLAGS', 'CXXFLAGS']:
        flags = next(line for line in lines if line.startswith(variable + ' '))
        if re.search(r'(?:^|\s)-O\S*', flags):
            raise RuntimeError('Baseline already specifies optimization')


def verify_write_paths():
    for path in [WORK, COPY, CONTROL, CORE, OUTPUT, CORE / 'Makefile', CORE / OUTPUT.name]:
        if path.is_symlink():
            raise RuntimeError('Writable build/control path must not be a symlink')
    # These are the locations the selected target may modify. Reject escaping links.
    for relative in ['qtbase/src/corelib', 'qtbase/src/corelib/.obj',
                     'qtbase/src/corelib/.moc', 'qtbase/src/corelib/.pch', 'qtbase/lib']:
        path = COPY / relative
        if not path.resolve().is_relative_to(COPY.resolve()):
            raise RuntimeError('Writable build path escapes isolated copy: ' + relative)
    # Generated files inside these directories may themselves be symlinks.
    for folder in ['.obj', '.moc', '.pch', '.rcc', '.tracegen']:
        for path in (CORE / folder).rglob('*'):
            if not path.resolve().is_relative_to(COPY.resolve()):
                raise RuntimeError('Generated output path escapes isolated copy: ' + folder)
    for relative in [str(CORE_REL / 'Makefile'), 'qtbase/lib/libQt5Core_arm64-v8a.so']:
        a, b = (ORIGINAL_BUILD / relative).stat(), (COPY / relative).stat()
        if (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino):
            raise RuntimeError('Copy unexpectedly shares original inode')


def prepare():
    if WORK.exists():
        if not (WORK / 'prepared.json').is_file():
            raise RuntimeError('Unrecognized/unfinished work directory; preserve and inspect it')
        return
    WORK.mkdir(mode=0o700, parents=True)
    CONTROL.mkdir()
    baseline = identity()
    input_abi = packaging_input_abi()
    # Copy-on-write where supported, ordinary independent copy otherwise. Never -l.
    subprocess.run(['cp', '-a', '--reflink=auto', str(ORIGINAL_BUILD), str(COPY)], check=True)
    verify_write_paths()
    # A later stamp guarantees recompilation even when all copied sources/objects
    # retain their original timestamps. Keep the stamp stable between dry-run/build.
    stamp = CONTROL / 'optimization.stamp'
    stamp.write_text('QtCore: same Debug configuration and assertions; add -O2 only\n')
    newest_object = max((p.stat().st_mtime for folder in ['.obj', '.pch']
                         for p in (CORE / folder).rglob('*') if p.is_file()), default=0)
    stamp_time = max(time.time(), newest_object + 2)
    os.utime(stamp, (stamp_time, stamp_time))
    compiler = '/opt/android-sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'
    (CONTROL / 'optimization.mk').write_text(
        # Preserve compiler/flags while exposing full commands in the actual log.
        'CC = ' + compiler + '\nCXX = ' + compiler + '++\n' +
        'CFLAGS += -O2\n'
        'CXXFLAGS += -O2\n'
        '$(OBJECTS) .pch/Qt5Core_arm64-v8a.pch/c.pch .pch/Qt5Core_arm64-v8a.pch/c++.pch: /task/optimization.stamp\n')
    save(WORK / 'prepared.json', {
        'baseline': baseline, 'image': IMAGE, 'input_abi': input_abi,
        'source': str(PACKAGE / 'b/qt5'), 'copy': str(COPY),
        'configuration_change': 'append -O2 to CFLAGS/CXXFLAGS only',
        'assertions_preserved': True,
        'control_sha256': sha(CONTROL / 'optimization.mk'),
    })


def command(dry):
    # Read-only Conan includes the exact existing patched sources and dependencies.
    # The nested writable mount shadows only the independent build-folder copy.
    result = ['podman', 'run', '--rm', '--userns=keep-id',
              '--security-opt', 'label=disable', '--network=none', '--read-only',
              '--tmpfs', '/tmp:rw,size=1g',
              '-v', str(SDK) + ':/opt/android-sdk:ro',
              '-v', str(CONAN) + ':' + CONTAINER_CONAN + ':ro',
              '-v', str(COPY) + ':' + CONTAINER_BUILD + ':rw',
              '-v', str(CONTROL) + ':/task:ro', IMAGE,
              'make', '-C', CONTAINER_BUILD + '/qtbase/src/corelib',
              '-f', 'Makefile', '-f', '/task/optimization.mk', '-o', 'Makefile']
    # Existing configuration is deliberately retained; prevent automatic qmake
    # regeneration of Makefile. Do not use -B or a top-level recursive target.
    result += ['-n'] if dry else ['-j' + str(JOBS)]
    return result + [TARGET]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['dry-run', 'build'])
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--base-apk', type=Path, required=True,
                        help='Verified copy of the installed APK, supplied without device actions')
    parser.add_argument('--image', default='localhost/overte-sh001-fdroid-toolchain:three-gates')
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    configure(args)
    guard()
    if args.phase == 'dry-run':
        prepare()
    elif not (WORK / 'dry-run.json').is_file():
        raise RuntimeError('Successful dry-run is required before build')
    prepared = json.loads((WORK / 'prepared.json').read_text())
    if IMAGE != prepared['image']:
        raise RuntimeError('Container image changed since dry-run preparation')
    if identity() != prepared['baseline']:
        raise RuntimeError('Original Qt inputs changed since preparation')
    if sha(CONTROL / 'optimization.mk') != prepared['control_sha256']:
        raise RuntimeError('Optimization control changed; review and rerun preparation')
    if sha(CORE / 'Makefile') != prepared['baseline']['inputs']['b/build_folder/qtbase/src/corelib/Makefile']:
        raise RuntimeError('Copied Makefile changed unexpectedly')
    verify_write_paths()
    dry = args.phase == 'dry-run'
    if not dry:
        previous = json.loads((WORK / 'dry-run.json').read_text())
        if previous['returncode'] != 0:
            raise RuntimeError('Dry-run failed')
    logfile = WORK / (args.phase + '.log')
    if logfile.exists():
        raise RuntimeError('Existing phase output must be preserved/reviewed: ' + str(logfile))
    argv = command(dry)
    with logfile.open('x') as stream:
        completed = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
    verify_write_paths()
    if identity() != prepared['baseline']:
        raise RuntimeError('Original input identity changed during operation')
    result = {'returncode': completed.returncode, 'command': argv,
              'log': str(logfile), 'baseline_unchanged': True}
    if completed.returncode == 0:
        result['compiler_provenance'] = compiler_provenance(logfile)
        if not dry and result['compiler_provenance']['commands_sha256'] != previous['compiler_provenance']['commands_sha256']:
            raise RuntimeError('Actual compiler commands differ from reviewed dry-run')
    if not dry and completed.returncode == 0:
        delta = require_same_abi(prepared['input_abi'], elf_identity(OUTPUT))
        verify_optional_export_consumers(delta)
        result['abi_export_delta'] = delta
        result['abi_matches_baseline_apk'] = True
        result['output'] = str(OUTPUT)
        result['sha256'] = sha(OUTPUT)
        result['baseline'] = prepared['baseline']
        result['configuration_change'] = prepared['configuration_change']
        result['assertions_preserved'] = True
        result['note'] = 'Not installed; ELF alignment and device validation remain required; ABI and compiler flags verified'
    save(WORK / (args.phase + '.json'), result)
    if completed.returncode:
        raise RuntimeError('Phase failed; inspect preserved log: ' + str(logfile))
    print(args.phase + ' complete; inspect ' + str(logfile))


if __name__ == '__main__':
    main()
