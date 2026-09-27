#!/usr/bin/env python3
"""Identify reusable shader outputs from the actual Ninja inputs and tool binaries."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess


def cache_key(build, targets=None):
    build = build.resolve()
    inputs = subprocess.check_output(['ninja', '-C', str(build), '-t', 'inputs', 'shadergen'], text=True)
    commands = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands', 'shadergen'], text=True)
    paths = {Path(name) if Path(name).is_absolute() else build / name for name in shlex.split(inputs)}
    if not paths or not commands.strip():
        raise ValueError('missing shader build graph')
    if targets is not None:
        if not targets or any(not re.fullmatch(r'[A-Za-z0-9_-]+', name) for name in targets):
            raise ValueError('invalid selected targets')
        selected = subprocess.check_output(['ninja', '-C', str(build), '-t', 'inputs', *targets], text=True)
        selected_paths = {Path(name) if Path(name).is_absolute() else build / name
                          for name in shlex.split(selected)}
        generators = {path for path in paths if path.name == 'shadergen.py'}
        if len(generators) != 1:
            raise ValueError('missing shader generator dependency')
        if not generators.issubset(selected_paths):
            return ''  # Do not save incomplete caches from shader-free test jobs.
    tool_config = build / 'cmake/ConanToolsDirs.cmake'
    paths.update((tool_config, build / 'libraries/shaders/shadergen.txt'))
    config = tool_config.read_text()
    for variable, executable in (('GLSLANG_DIR', 'glslangValidator'), ('SCRIBE_DIR', 'scribe'),
                                 ('SPIRV_CROSS_DIR', 'spirv-cross'), ('SPIRV_TOOLS_DIR', 'spirv-opt')):
        match = re.search(r'set\(' + variable + r'\s+"([^"\n]+)"\)', config)
        if not match:
            raise ValueError('missing shader compiler: ' + variable)
        paths.add(Path(match.group(1)) / executable)
    digest = hashlib.sha256(b'overte-native-shaders-v1\0' + commands.encode())
    for path in sorted(paths):
        if not path.is_file():
            raise ValueError('missing shader input: ' + str(path))
        digest.update(str(path).encode() + b'\0')
        with path.open('rb') as stream:
            digest.update(hashlib.file_digest(stream, 'sha256').digest())
    return digest.hexdigest()


def refresh(build):
    # Call only after an exact content-key cache hit. A new checkout gives source
    # files fresh timestamps; shadergen's timestamp check otherwise recompiles
    # identical inputs. Never restore CMake/Ninja state or change source times.
    build = build.resolve()
    outputs = build / 'libraries/shaders/shaders'
    if outputs.is_symlink() or not outputs.resolve().is_relative_to(build):
        raise ValueError('shader output directory escaped the build tree')
    files = list(outputs.rglob('*'))
    if not files:
        raise ValueError('empty shader cache')
    if any(path.is_symlink() for path in files):
        raise ValueError('symlinks are not shader cache outputs')
    for path in files:
        if path.is_file():
            path.touch()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('key', 'refresh'))
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--selection', type=Path)
    args = parser.parse_args()
    if args.command == 'key':
        targets = json.loads(args.selection.read_text())['targets'] if args.selection else None
        key = cache_key(args.build, targets)
        if args.output:
            with args.output.open('a') as stream:
                stream.write('key=' + key + '\n')
        print(key)
    else:
        refresh(args.build)
