#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""F-Droid manual build: acquire locked inputs, then build without networking.

Runs on the provisioned buildserver directly; no Podman, developer binaries,
Gradle wrapper, production key, or private service is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[4]
FDROID = ROOT / 'android/phone/fdroid'
APK = ROOT / 'android/phone/apps/phoneInterface/build/outputs/apk/release/phoneInterface-release-unsigned.apk'
GRADLE_SHA256 = '20f1b1176237254a6fc204d8434196fa11a4cfb387567519c61556e8710aed78'
GRADLE_URL = 'https://services.gradle.org/distributions/gradle-8.13-bin.zip'


def run(command, *, env=None, cwd=ROOT):
    subprocess.run([str(x) for x in command], cwd=cwd, env=env, check=True)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_coordinates(commit, code, name):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('source commit must be a full lowercase Git commit SHA')
    if not 1 <= code <= 2147483647:
        raise ValueError('invalid Android versionCode')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,99}', name):
        raise ValueError('invalid Android versionName')


def extract_gradle(archive, target):
    if digest(archive) != GRADLE_SHA256:
        raise ValueError('Gradle distribution SHA-256 mismatch')
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if (not parts or parts[0] != 'gradle-8.13' or '..' in parts
                    or Path(info.filename).is_absolute()
                    or (info.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('unsafe Gradle archive member')
        z.extractall(target)
    executable = target / 'gradle-8.13/bin/gradle'
    executable.chmod(0o755)
    return executable


def environment(args):
    # Keep basic process identity/locale, not developer graph selectors,
    # credentials, compiler overrides, or JVM/Gradle injection flags.
    env = {key: value for key, value in os.environ.items() if key in {
        'PATH', 'HOME', 'USER', 'LOGNAME', 'LANG', 'LC_ALL', 'TZ', 'TMPDIR',
        'SSL_CERT_FILE', 'SSL_CERT_DIR'}}
    env.update(
        OVERTE_ATTEMPT_ROOT=str(args.work_dir),
        OVERTE_SOURCE_CLOSURE_STORE=str(args.source_store),
        OVERTE_SOURCE_COMMIT=args.commit,
        ANDROID_SDK_ROOT=str(args.sdk), ANDROID_HOME=str(args.sdk),
        ANDROID_NDK_HOME=str(args.sdk / 'ndk/27.3.13750724'),
        GRADLE_USER_HOME=str(args.work_dir / 'gradle-home'),
        JAVA_HOME=str(args.java_home),
        OVERTE_FDROID_STANDARD_TOOLCHAIN='1',
    )
    env['PATH'] = os.pathsep.join([str(args.java_home / 'bin'),
                                    str(args.sdk / 'cmdline-tools/22.0/bin'),
                                    env.get('PATH', '')])
    env['PHONE_APK_ANALYZER'] = str(args.sdk / 'cmdline-tools/22.0/bin/apkanalyzer')
    return env


def isolation_prefix():
    # Gradle's local daemon handshake needs loopback even in an otherwise
    # empty network namespace. No physical interfaces or default route exist.
    return ['unshare', '--user', '--map-root-user', '--net', 'sh', '-ec',
            'ip link set lo up; exec "$@"', 'overte-offline']


def preflight(args, env):
    validate_coordinates(args.commit, args.version_code, args.version_name)
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if actual != args.commit:
        raise ValueError('checkout commit differs from metadata commit')
    for relative in ['platforms/android-36/android.jar', 'build-tools/35.0.0/aapt2',
                     'build-tools/36.0.0/aapt2',
                     'ndk/27.3.13750724/source.properties', 'cmake/3.31.6/bin/cmake',
                     'cmdline-tools/22.0/bin/apkanalyzer',
                     'build-tools/36.0.0/zipalign',
                     'ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-readelf']:
        if not (args.sdk / relative).is_file():
            raise ValueError('missing Android SDK input: ' + relative)
    for tool in ('unzip', 'realpath'):
        if shutil.which(tool, path=env.get('PATH')) is None:
            raise ValueError('missing APK inspection tool: ' + tool)
    run([env['PHONE_APK_ANALYZER'], '--help'], env=env)
    epoch = subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'],
                                    cwd=ROOT, text=True).strip()
    if not epoch.isdigit():
        raise ValueError('invalid source commit timestamp')
    env.update(SOURCE_DATE_EPOCH=epoch, QT_RCC_SOURCE_DATE_OVERRIDE=epoch,
               TZ='UTC', LC_ALL='C.UTF-8', PYTHONHASHSEED='0', QT_HASH_SEED='0')
    run([sys.executable, FDROID / 'submission/toolchain.py'], env=env)
    run([*isolation_prefix(), sys.executable, '-c',
         'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); '
         's.listen(); c=socket.create_connection(s.getsockname(),timeout=3); '
         'c.close(); s.close()'], env=env)
    print('FDROID_BUILDSERVER_PREFLIGHT=PASS', flush=True)


def acquire(args, env):
    args.work_dir.mkdir(parents=True, exist_ok=False)
    closure = FDROID / 'conan/source_closure_store.py'
    run([sys.executable, closure, 'acquire', '--manifest', FDROID / 'manifests/source-closure.lock.json',
         '--repo-root', ROOT, '--store', args.source_store], env=env)
    archive = args.work_dir / 'gradle-8.13-bin.zip'
    with urllib.request.urlopen(GRADLE_URL, timeout=120) as response, archive.open('wb') as target:
        shutil.copyfileobj(response, target)
    gradle = extract_gradle(archive, args.work_dir)
    env['OVERTE_GRADLE_ACQUISITION_BUILD_DIR'] = str(args.work_dir / 'acquisition-build')
    run([gradle, '--no-daemon', '--project-cache-dir', args.work_dir / 'acquisition-cache',
         '-p', FDROID / 'gradle-acquisition', 'resolveFdroidAcquisition'], env=env)
    del env['OVERTE_GRADLE_ACQUISITION_BUILD_DIR']
    # This prepares source archives only. The existing source-only executor
    # retains its own empty-binary-cache and exact-lock checks at build time.
    run([FDROID / 'scripts/build-dependencies.sh', '--prepare'], env=env)
    (args.work_dir / 'acquired.json').write_text(json.dumps({
        'source_commit': args.commit, 'version_code': args.version_code,
        'version_name': args.version_name,
        'source_manifest_sha256': digest(FDROID / 'manifests/source-closure.lock.json'),
        'gradle_sha256': digest(archive),
    }, indent=2) + '\n')
    return gradle


def write_reproducible_cmake(args):
    mappings = {str(ROOT): '/usr/src/overte', str(args.work_dir): '/usr/src/overte-build',
                str(args.sdk): '/opt/android-sdk'}
    for path in sorted((args.work_dir / 'reproducible-paths').glob('*.json')):
        mappings.update(json.loads(path.read_text()))
    output = args.work_dir / 'reproducible-paths.cmake'
    lines = ['# Generated diagnostic/debug paths; original sources remain untouched.']
    for old, new in sorted(mappings.items(), key=lambda pair: (len(pair[0]), pair[0])):
        if any(c in old + new for c in ('"', ';', '$', '\\', '\n', '\r')):
            raise ValueError('unsafe compiler path mapping')
        lines.append(f'add_compile_options("-ffile-prefix-map={old}={new}")')
    output.write_text('\n'.join(lines) + '\n')
    return output


def release_command(args, gradle):
    return [gradle, '--offline', '--no-daemon', '--no-build-cache',
            '-Dorg.gradle.jvmargs=-Xmx6g -XX:MaxMetaspaceSize=1g -Dfile.encoding=UTF-8',
            '--settings-file', ROOT / 'android/phone/settings.gradle',
            '-p', ROOT / 'android/phone', f'-PVERSION_CODE={args.version_code}',
            f'-PRELEASE_NUMBER={args.version_name}',
            f'-Pandroid.aapt2FromMavenOverride={args.sdk}/build-tools/36.0.0/aapt2',
            ':phoneInterface:assembleRelease', '--max-workers', str(os.cpu_count() or 1)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--version-code', required=True, type=int)
    parser.add_argument('--version-name', required=True)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--java-home', type=Path, default=Path('/usr/lib/jvm/java-21-openjdk-amd64'))
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--source-store', type=Path, help='optional existing hash-verified source archives, never binary packages')
    parser.add_argument('--check', action='store_true', help='check prerequisites only')
    parser.add_argument('--acquire-only', action='store_true', help='acquire/prepare inputs without compiling')
    args = parser.parse_args()
    args.sdk = args.sdk.resolve()
    args.java_home = args.java_home.resolve()
    args.work_dir = args.work_dir.resolve()
    args.source_store = (args.source_store or args.work_dir / 'source-store').resolve()
    if args.work_dir.exists():
        raise ValueError('work directory must be new; no developer caches are reused')
    env = environment(args)
    preflight(args, env)
    if args.check:
        return
    for directory in ('build', '.cxx'):
        if (APK.parents[4] / directory).exists():
            raise ValueError('application build output exists; use a clean F-Droid checkout')
    gradle = acquire(args, env)
    if args.acquire_only:
        print('FDROID_INPUT_ACQUISITION=PASS (no build performed)')
        return
    env['OVERTE_FDROID_CONAN_DIR'] = str(args.work_dir / 'target')
    isolation = isolation_prefix()
    run([*isolation, FDROID / 'scripts/build-dependencies.sh', '--build'], env=env)
    env['OVERTE_FDROID_REPRODUCIBLE_CMAKE'] = str(write_reproducible_cmake(args))
    run([*isolation, *release_command(args, gradle)], env=env)
    if not APK.is_file():
        raise ValueError('unsigned release APK is absent')
    (args.work_dir / 'result.json').write_text(json.dumps({
        'source_commit': args.commit, 'apk_sha256': digest(APK),
        'version_code': args.version_code, 'version_name': args.version_name,
        'network_during_compilation': 'isolated', 'signed': False,
    }, indent=2) + '\n')
    print('FDROID_SOURCE_BUILD=PASS (unsigned APK; not F-Droid admission)')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, zipfile.BadZipFile) as error:
        print(f'FDROID_SOURCE_BUILD=FAIL: {error}', file=sys.stderr)
        sys.exit(1)
