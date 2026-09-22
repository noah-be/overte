#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check the standard trixie toolchain without freezing Debian patch releases."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def validate(versions):
    # Match the explicit Linux Conan settings, while accepting distro updates.
    for compiler in ('gcc', 'g++'):
        if versions[compiler].split('.')[0] != '14':
            raise ValueError(f'{compiler}: Debian trixie GCC 14 is required')
    if versions['gcc'] != versions['g++']:
        raise ValueError('gcc and g++ versions differ')
    for name, minimum, major in [('cmake', (3, 31), 3), ('ninja', (1, 12), 1)]:
        version = tuple(int(x) for x in versions[name].split('.'))
        if version[0] != major or version[:2] < minimum:
            raise ValueError(f'{name}: expected major {major}, at least {minimum[0]}.{minimum[1]}')
    if versions['java'].split('.')[0] != '21':
        raise ValueError('OpenJDK 21 is required')
    if versions['conan'] != '2.25.2':
        raise ValueError('Conan 2.25.2 is required by the recipe lock')


def inspect():
    java = Path(os.environ['JAVA_HOME']) / 'bin/java'
    commands = {
        'gcc': (['gcc', '-dumpfullversion'], r'^(\d+(?:\.\d+)*)\s*$'),
        'g++': (['g++', '-dumpfullversion'], r'^(\d+(?:\.\d+)*)\s*$'),
        'cmake': (['cmake', '--version'], r'^cmake version (\d+(?:\.\d+)*)'),
        'ninja': (['ninja', '--version'], r'^(\d+(?:\.\d+)*)\s*$'),
        'java': ([str(java), '-version'], r'version "(\d+(?:\.\d+)*)'),
        'conan': (['conan', '--version'], r'^Conan version (\d+(?:\.\d+)*)'),
    }
    versions = {}
    # Even the Conan version query must not initialize the real build cache.
    with tempfile.TemporaryDirectory(prefix='overte-toolchain-') as probe:
        env = dict(os.environ, CONAN_HOME=probe)
        for name, (command, pattern) in commands.items():
            output = subprocess.check_output(command, env=env, text=True,
                                             stderr=subprocess.STDOUT)
            match = re.search(pattern, output)
            if not match:
                raise ValueError(f'cannot identify {name} version')
            versions[name] = match.group(1)
    validate(versions)
    return versions


if __name__ == '__main__':
    try:
        print(json.dumps({'status': 'PASS', 'toolchain': inspect()}, sort_keys=True))
    except (KeyError, ValueError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}, sort_keys=True))
        raise SystemExit(1)
