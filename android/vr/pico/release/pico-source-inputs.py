#!/usr/bin/env python3
"""Resolve Pico build inputs through existing SH009 phase/source joins; never build."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'provenance'))
from artifact_identity import IdentityError, digest_file, hex_digest, require
from sbom_validation import read_sbom
from conan_sources import verify_sources
from conan_inventory import read_checkpoint

SHADER_TOOLS = {'scribe': 'tools/scribe', 'glslang': 'bin/glslangValidator',
                'spirv-cross': 'bin/spirv-cross', 'spirv-tools': 'bin/spirv-opt'}
QML_MODULES = ['Qt/labs/settings', 'QtQml', 'QtQml/Models.2', 'QtQml/WorkerScript.2',
    'QtQuick.2', 'QtQuick/Controls', 'QtQuick/Controls.2', 'QtQuick/Dialogs',
    'QtQuick/PrivateWidgets', 'QtQuick/Templates.2', 'QtQuick/Layouts',
    'QtQuick/Window.2', 'Qt/labs/folderlistmodel', 'QtGraphicalEffects']
# Additional dynamically loaded Qt libraries from the existing Pico caller.
# Ordinary link dependencies are packaged by AGP's CMake graph, not twice.
EXTRA_QT_LIBRARIES = ['QuickParticles', 'Contacts', 'DocGallery', 'Feedback',
                     'Organizer', 'PositioningQuick', 'VersitOrganizer', 'Versit']


def resolve(root, binding_path, expected_binding, expected_source):
    require(hex_digest(expected_binding) and hex_digest(expected_source, 40), 'PICO_EXPECTED_IDENTITY')
    root = Path(root)
    require(root.is_absolute() and root.resolve(strict=True) == root and root.is_dir(), 'PICO_GRAPH_ROOT')
    # All emitted paths may be CMake quoted arguments; forbid code/list expansion.
    require(not any(c in str(root) for c in '\\";$\n\r'), 'PICO_GRAPH_PATH')
    binding_path = Path(binding_path)
    require(not binding_path.is_symlink() and digest_file(binding_path) == expected_binding, 'PICO_BINDING_HASH')
    spec = read_sbom(binding_path)
    require(spec.get('contract') == 'overte-pico-source-inputs-v1' and
            spec.get('sourceRevision') == expected_source, 'PICO_BINDING_SOURCE')
    files = spec.get('files')
    require(type(files) is dict and 0 < len(files) <= 100000, 'PICO_PAYLOAD_INVENTORY')

    def path(value):
        require(type(value) is str and value and not any(c in value for c in '\\";$\n\r') and
                all(part not in ('', '.', '..') for part in value.split('/')) and
                not Path(value).is_absolute(), 'PICO_RELATIVE_PATH')
        result = root / value
        require(result.resolve(strict=True).is_relative_to(root), 'PICO_PATH_ESCAPE')
        return result

    def checked(file):
        file = Path(file)
        relative = file.relative_to(root).as_posix()
        path(relative)
        require(file.is_file() and hex_digest(files.get(relative)), 'PICO_PAYLOAD_HASH')
        value = hashlib.sha256()
        with file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
        require(value.hexdigest() == files[relative], 'PICO_PAYLOAD_HASH')
        return file

    def directory(folder):
        require(folder.is_dir(), 'PICO_INPUT_DIRECTORY')
        for entry in folder.rglob('*'):
            path(entry.relative_to(root).as_posix())
            if entry.is_file(): checked(entry)
        return folder

    closure = checked(path(spec['sourceClosure']))
    index = checked(path(spec['recipeIndex']))
    phases, raw = {}, {}
    for phase in ('target', 'host-tools'):
        item = spec['phases'][phase]
        actual, expected, checkpoint = [checked(path(item[k])) for k in ('actualGraph', 'expectedGraph', 'checkpoint')]
        require(read_checkpoint(checkpoint)['attempt_root'] == str(root), 'PICO_ATTEMPT_ROOT')
        phases[phase] = verify_sources(closure, actual, expected, checkpoint, expected_source, phase,
            files[expected.relative_to(root).as_posix()], files[closure.relative_to(root).as_posix()],
            files[index.relative_to(root).as_posix()])
        raw[phase] = read_sbom(actual)['graph']['nodes']

    def package(phase, name):
        matches = [n for n in raw[phase].values() if (n.get('ref') or '').split('/')[0] == name
                   and n.get('context') == 'host']
        require(len(matches) == 1, 'PICO_PACKAGE_SELECTION')
        node = matches[0]
        settings = node['settings']
        require((settings.get('os'), settings.get('arch')) ==
                (('Android', 'armv8') if phase == 'target' else ('Linux', 'x86_64')), 'PICO_PACKAGE_ARCH')
        if phase == 'target':
            require(settings.get('build_type') == 'Debug' and str(settings.get('os.api_level')) == '26', 'PICO_TARGET_PROFILE')
        folder = Path(node['package_folder'])
        require(folder.is_absolute() and folder.is_relative_to(root), 'PICO_PACKAGE_PATH')
        return node, directory(path(folder.relative_to(root).as_posix()))

    qt_node, qt = package('target', 'qt')
    ssl_node, ssl = package('target', 'openssl')
    _, draco = package('target', 'draco')
    package('target', 'openxr')
    host_qt_node, host_qt = package('host-tools', 'qt')
    require(ssl_node['ref'].split('#')[0] == 'openssl/3.5.8@overte/stable', 'PICO_PROVIDER_VERSION')
    require(qt_node['ref'].startswith('qt/5.15.'), 'PICO_QT_VARIANT')
    require(host_qt_node['ref'] == qt_node['ref'], 'PICO_QT_HOST_RECIPE_MISMATCH')
    generators = directory(path(spec['generators']))
    checked(generators / 'conandeps_legacy.cmake')
    qt_data = checked(generators / 'Qt5-debug-armv8-data.cmake').read_text()
    require(re.findall(r'set\(qt_PACKAGE_FOLDER_DEBUG "([^"]+)"\)', qt_data) == [str(qt)], 'PICO_QT_GENERATOR_BINDING')
    # Existing runtime patch is a required source prerequisite. This only checks
    # its presence in the declared source, not that binaries were built from it.
    qt_source = directory(path(spec['qtSourceDirectory']))
    patch = REPO / 'android/common/conan/patches/qt-pico-android-runtime.patch'
    require(spec.get('qtRuntimePatchSha256') == digest_file(patch), 'PICO_QT_PATCH_IDENTITY')
    result = subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=qt_source,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    require(result.returncode == 0, 'PICO_QT_RUNTIME_PATCH_MISSING')

    def elf(file, machine, executable=False):
        checked(file)
        with file.open('rb') as stream: header = stream.read(20)
        require(len(header) == 20 and header[:6] == b'\x7fELF\x02\x01' and
                struct.unpack_from('<H', header, 18)[0] == machine and
                (not executable or os.access(file, os.X_OK)), 'PICO_ELF_ARCH')
        return str(file)

    tools = {name: elf(host_qt / 'bin' / name, 62, True) for name in ('moc', 'rcc', 'uic', 'qmake')}
    for name, relative in SHADER_TOOLS.items():
        _, folder = package('host-tools', name)
        tools[Path(relative).name] = elf(folder / relative, 62, True)
    runtime = {}
    # Only host-context Android packages enter the APK. Development OpenSSL
    # symlinks are intentionally not payloads; no duplicate renamed providers.
    for node in raw['target'].values():
        if node.get('context') != 'host' or node.get('settings', {}).get('os') != 'Android' or not node.get('ref'):
            continue
        _, folder = package('target', node['ref'].split('/')[0])
        for file in folder.rglob('*'):
            if not file.is_file() or '.so' not in file.name: continue
            if file.name in ('libssl.so', 'libcrypto.so') and file.is_symlink() and folder == ssl:
                require(file.resolve() == (ssl / 'lib' / file.name.replace('.so', '_3.so')).resolve(), 'PICO_PROVIDER_ALIAS')
                continue
            require(file.name.endswith('.so') and (not file.name.startswith(('libssl', 'libcrypto'))
                    or file.name in ('libssl_3.so', 'libcrypto_3.so')), 'PICO_LEGACY_PROVIDER_OR_SONAME')
            require(file.name not in runtime or runtime[file.name] == str(file), 'PICO_DUPLICATE_PAYLOAD')
            runtime[file.name] = elf(file, 183)
    for name in ('libssl_3.so', 'libcrypto_3.so'):
        require(runtime.get(name) == str(ssl / 'lib' / name), 'PICO_CANONICAL_PROVIDER')
    staged = {name: value for name, value in runtime.items() if
              Path(value).is_relative_to(qt / 'plugins') or Path(value).is_relative_to(qt / 'qml') or
              name in ('libssl_3.so', 'libcrypto_3.so') or
              name in ('libQt5' + module + '_arm64-v8a.so' for module in EXTRA_QT_LIBRARIES)}
    # These are the exact extraction destinations consumed by QtActivityLoader.
    # Missing a declared plugin must fail before a package can be assembled.
    resources = REPO / 'android/vr/pico/apps/picoInterface/src/main/res/values/qt_dependencies.xml'
    for item in ET.parse(resources).findall("./string-array[@name='bundled_in_lib']/item"):
        require(item.text.split(':', 1)[0] in staged, 'PICO_QT_RUNTIME_BINDING')
    for module in QML_MODULES:
        checked(qt / 'qml' / module / 'qmldir')
    checked(qt / 'jar/QtAndroid.jar')
    checked(draco / 'include/draco/compression/decode.h')
    checked(draco / 'lib/libdraco.a')
    # Recheck the frozen binding and all supplied bytes after resolution.
    for relative in files: checked(path(relative))
    require(digest_file(binding_path) == expected_binding, 'PICO_INPUT_CHANGED')
    return {'status': 'PICO_INPUT_BYTES_BOUND_NATIVE_VERIFICATION_PENDING',
        'sourceRevision': expected_source, 'bindingSha256': expected_binding,
        'graphRoot': str(root), 'generators': str(generators), 'qtPackage': str(qt),
        'dracoInclude': str(draco / 'include'), 'tools': tools, 'runtime': runtime, 'stagedRuntime': staged,
        'qmlModules': QML_MODULES, 'provenance': phases,
        'acceptance': 'No graph equivalence, build attestation, SONAME/NEEDED, 16KiB or VR acceptance'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph-root', default=os.environ.get('PICO_SOURCE_GRAPH_ROOT'))
    parser.add_argument('--binding', default=os.environ.get('PICO_SOURCE_INPUTS'))
    parser.add_argument('--expected-binding-sha256', default=os.environ.get('PICO_SOURCE_INPUTS_SHA256'))
    parser.add_argument('--expected-source-sha', default=os.environ.get('PICO_EXPECTED_SOURCE_SHA'))
    # Existing deps --source-graph adapter ABI; this never writes the source tree.
    parser.add_argument('--pico-root')
    args = parser.parse_args()
    try:
        require(all((args.graph_root, args.binding, args.expected_binding_sha256, args.expected_source_sha)), 'PICO_EXPLICIT_INPUTS_REQUIRED')
        if args.pico_root:
            require(Path(args.pico_root).resolve() == REPO / 'android/vr/pico', 'PICO_CONSUMER_ROOT')
        revision = subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True, timeout=5).strip()
        require(revision == args.expected_source_sha, 'PICO_CHECKOUT_SOURCE')
        print(json.dumps(resolve(args.graph_root, args.binding, args.expected_binding_sha256, args.expected_source_sha), sort_keys=True))
    except IdentityError as error:
        print('PICO_SOURCE_INPUTS_REJECTED: ' + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError, subprocess.SubprocessError):
        print('PICO_SOURCE_INPUTS_REJECTED', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__': sys.exit(main())
