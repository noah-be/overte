# SPDX-License-Identifier: Apache-2.0
"""Normalize proven path leaks in the isolated Phone F-Droid Conan build."""
import json
import os
from pathlib import Path


def identity(recipe):
    return '/usr/src/overte-dependencies/' + str(recipe.ref).replace('@', '/').replace('#', '/')


def path_maps(recipe):
    mappings = {}
    for dependency in recipe.dependencies.values():
        if dependency.package_folder:
            mappings[dependency.package_folder] = identity(dependency) + '/package'
    base = identity(recipe)
    # For no-copy-source recipes the two roots can be equal. Use one name.
    for field, suffix in [('source_folder', '/source'), ('build_folder', '/build'),
                          ('package_folder', '/package')]:
        value = getattr(recipe, field, None)
        if value:
            mappings[value] = base + suffix
    sdk = os.environ.get('ANDROID_SDK_ROOT')
    if sdk:
        mappings[sdk] = '/opt/android-sdk'
    return sorted(mappings.items(), key=lambda pair: (len(pair[0]), pair[0]))


def normalize_node_config(source, mappings):
    # Node embeds config.gypi as process.config. Keep real paths for GYP's build,
    # but replace local paths in the informational copy embedded by js2c.
    path = Path(source) / 'tools/js2c.cc'
    text = path.read_text()
    marker = '  std::vector<char> transformed = JSONify(code);'
    if text.count(marker) != 1:
        raise ValueError('Unexpected Node js2c configuration embedding implementation')
    statements = ['  std::string reproducible_config(code.begin(), code.end());']
    # Specific paths first so a parent cannot mask a more precise replacement.
    for old, new in reversed(mappings):
        statements += [
            '  {',
            f'    const std::string from = {json.dumps(old)};',
            f'    const std::string to = {json.dumps(new)};',
            '    size_t pos = 0;',
            '    while ((pos = reproducible_config.find(from, pos)) != std::string::npos) {',
            '      reproducible_config.replace(pos, from.size(), to);',
            '      pos += to.size();',
            '    }',
            '  }',
        ]
    statements += ['  code.assign(reproducible_config.begin(), reproducible_config.end());', marker]
    path.write_text(text.replace(marker, '\n'.join(statements)))


def pre_generate(conanfile):
    if os.environ.get('OVERTE_FDROID_STANDARD_TOOLCHAIN') != '1':
        return
    # The top-level install consumer has no package reference or package folder.
    if not conanfile.package_folder:
        return
    maps = path_maps(conanfile)
    # OpenSSL's only observed difference is its build date (SOURCE_DATE_EPOCH
    # fixes it). It embeds compiler flags verbatim; do not add path-bearing flags.
    if conanfile.name != 'openssl':
        for old, new in maps:
            flag = f'-ffile-prefix-map={old}={new}'
            for option in ('tools.build:cflags', 'tools.build:cxxflags'):
                conanfile.conf.append(option, flag)
    if conanfile.name == 'libnode':
        normalize_node_config(conanfile.source_folder, maps)
    # Capture mappings while the build folders still exist. Used by the final
    # app compiler for included dependency headers and DWARF build IDs.
    directory = Path(os.environ['OVERTE_ATTEMPT_ROOT']) / 'reproducible-paths'
    directory.mkdir(exist_ok=True)
    import hashlib
    key = hashlib.sha256((str(conanfile.ref) + str(conanfile.build_folder)).encode()).hexdigest()
    (directory / (key + '.json')).write_text(json.dumps(maps, indent=2) + '\n')
