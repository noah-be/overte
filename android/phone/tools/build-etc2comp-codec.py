#!/usr/bin/env python3
"""Build the measured Phone ETC candidate into a new, isolated output directory.

No downloads, Conan cache changes, application build, or installation. The input
must be the already CMake-patched source used by the measured production codec.
The output remains available, including logs and manifest, on failure.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess

EXPECTED = {
    'EtcLib/EtcCodec/EtcBlock4x4Encoding.cpp': (
        '435eb3700024f584d8cd90df3f8b321828d0a956cd15cc640a2d3f542a93f2a0',
        '6bf1416fe873a6c1c5a00fee8413ea149309998ab534b776b729b765e0f76951'),
    'EtcLib/EtcCodec/EtcBlock4x4Encoding.h': (
        'c1203ed6061e14d6429563fb7c619151beaffa79071e54140996f7dc66098a2f',
        '23db946cf51a6109c52c19fa29e09ac208ffce08c435fefcbe49a3286f760be8'),
}
SOURCE_INVENTORY_SHA256 = 'd80be424311a44031461c5825c44f166ef841958d37c5fd6eea63be619633d18'
PATCH_SHA256 = 'baf9602ec395959f1aae82e26a79589dc95335fa897ce03b17100f285148bf53'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    paths = sorted(root.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Source tree must not contain symlinks')
    return {path.relative_to(root).as_posix(): digest(path) for path in paths if path.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--ndk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=3, choices=range(1, 7))
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    ndk = args.ndk.resolve(strict=True)
    output = args.output.resolve()
    if output.exists() or output == source or source in output.parents or ndk in output.parents:
        raise ValueError('Output must be new and outside source and NDK trees')
    patch = Path(__file__).resolve().with_name('etc2comp-rgba-inline.patch')
    if digest(patch) != PATCH_SHA256:
        raise ValueError('Candidate patch hash mismatch')
    if 'Pkg.Revision = 27.3.13750724' not in (ndk / 'source.properties').read_text():
        raise ValueError('This measured candidate requires NDK 27.3.13750724')
    initial = inventory(source)
    inventory_sha256 = hashlib.sha256(json.dumps(initial, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if inventory_sha256 != SOURCE_INVENTORY_SHA256:
        raise ValueError('Unexpected source inventory; use the measured production codec source')
    for name, (before, _) in EXPECTED.items():
        if initial.get(name) != before:
            raise ValueError('Unexpected original source: ' + name)
    toolchain = ndk / 'build/cmake/android.toolchain.cmake'
    if not toolchain.is_file():
        raise ValueError('NDK CMake toolchain missing')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'status': 'preparing', 'source': str(source), 'ndk': str(ndk),
                'source_files_before': initial, 'patch_sha256': PATCH_SHA256,
                'builder_sha256': digest(Path(__file__).resolve()), 'commands': [],
                'build_flags': '-O2 -g -DNDEBUG -fPIC -std=gnu++11; NDK standard Android hardening flags',
                'assertions': 'Original EtcConfig.h forced development assertions retained',
                'limits': ['Static codec build only; no application or device validation.']}

    def save():
        manifest['commands_sha256'] = hashlib.sha256(json.dumps(manifest['commands'], sort_keys=True).encode()).hexdigest()
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

    def run(command, logfile, cwd=None):
        manifest['commands'].append({'argv': command, 'cwd': str(cwd or output), 'log': logfile})
        save()
        with (output / logfile).open('w') as log:
            subprocess.run(command, cwd=cwd or output, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=600)

    save()
    try:
        copied = output / 'source'
        shutil.copytree(source, copied)
        # The reviewed unified patch has LF lines; preserve production CRLF
        # bytes by normalizing only its two bound files for patch application.
        for name in EXPECTED:
            path = copied / name
            path.write_bytes(path.read_bytes().replace(b'\r\n', b'\n'))
        run(['patch', '--batch', '--forward', '--fuzz=0', '-p2', '-i', str(patch)], 'patch.log', copied)
        for name, (_, after) in EXPECTED.items():
            path = copied / name
            path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            if digest(path) != after:
                raise ValueError('Patched source does not match measured candidate: ' + name)
        patched = inventory(copied)
        changed = {name for name in set(initial) | set(patched) if initial.get(name) != patched.get(name)}
        if changed != set(EXPECTED):
            raise ValueError('Unexpected source changes during patching')
        manifest['source_files_patched'] = patched
        manifest['status'] = 'building'
        configure = ['cmake', '-S', str(copied), '-B', str(output / 'build'), '-G', 'Ninja',
                     '-DCMAKE_TOOLCHAIN_FILE=' + str(toolchain), '-DANDROID_ABI=arm64-v8a',
                     '-DANDROID_PLATFORM=android-26', '-DCMAKE_BUILD_TYPE=RelWithDebInfo',
                     '-DCMAKE_CXX_FLAGS_RELWITHDEBINFO=-O2 -g -DNDEBUG',
                     '-DCMAKE_CXX_STANDARD=11', '-DCMAKE_CXX_EXTENSIONS=ON',
                     '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', '-DBUILD_SHARED_LIBS=OFF',
                     '-DCMAKE_POLICY_VERSION_MINIMUM=3.5', '-DCMAKE_EXPORT_COMPILE_COMMANDS=ON']
        run(configure, 'configure.log')
        run(['cmake', '--build', str(output / 'build'), '--target', 'EtcLib', '-j', str(args.jobs)], 'build.log')
        archive = output / 'build/EtcLib/libEtcLib.a'
        if not archive.is_file():
            raise ValueError('Expected static archive absent')
        if inventory(source) != initial:
            raise ValueError('Original source changed during build')
        manifest.update(status='complete', archive=str(archive), archive_sha256=digest(archive),
                        source_unchanged=True, compile_commands_sha256=digest(output / 'build/compile_commands.json'))
        save()
        print(json.dumps({'archive': str(archive), 'sha256': manifest['archive_sha256']}))
    except Exception as error:
        manifest.update(status='failed', error=type(error).__name__ + ': ' + str(error))
        save()
        raise


if __name__ == '__main__':
    main()
