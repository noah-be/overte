#!/usr/bin/env python3
"""Map changed paths through CMake's configured target and include dependency graph."""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess


def select(targets, tests, paths, source, broad=False):
    by_name = {target['name']: target for target in targets}
    if len(by_name) != len(targets) or not tests or any(name not in by_name for name in tests):
        raise ValueError('native target inventory is incomplete')
    affected = set()
    roots = []
    for path in paths:
        parts = Path(path).parts
        # Every native test executable owns one *Test(s).cpp translation unit.
        # Headers and helpers stay at group scope because they may be shared.
        if len(parts) == 4 and parts[0] == 'tests' and parts[2] == 'src' and path.endswith('.cpp'):
            owner = parts[1] + '-' + Path(path).stem
            if owner in tests:
                affected.add(by_name[owner]['id'])
                continue
        if len(parts) > 1 and parts[0] in ('libraries', 'tests', 'plugins', 'tools'):
            roots.append(source / parts[0] / parts[1])
        elif parts[0] in ('interface', 'assignment-client', 'domain-server', 'ice-server'):
            roots.append(source / parts[0])
        else:
            broad = True
    matched_roots = set()
    for target in targets:
        inputs = [source / item['path'] for item in target.get('sources', [])]
        # Include-only dependencies are absent from the CMake link graph. Capture
        # their consumers conservatively at component-directory granularity.
        inputs += [Path(item['path']) for group in target.get('compileGroups', [])
                   for item in group.get('includes', [])]
        matches = {root for root in roots if any(p.is_relative_to(root) for p in inputs)}
        matched_roots.update(matches)
        if matches:
            affected.add(target['id'])
    # One known component must not hide another removed/unmapped component in
    # the same change set. Every component root needs a graph match.
    if set(roots) - matched_roots:
        broad = True
    progress = True
    while progress:
        progress = False
        for target in targets:
            if target['id'] not in affected and any(dep['id'] in affected for dep in target.get('dependencies', [])):
                affected.add(target['id'])
                progress = True
    selected = sorted(name for name in tests if broad or by_name[name]['id'] in affected)
    build = set(selected)
    # Build changed production components even if no test currently covers them.
    for target in targets:
        if target.get('type') not in ('EXECUTABLE', 'STATIC_LIBRARY', 'SHARED_LIBRARY', 'MODULE_LIBRARY', 'OBJECT_LIBRARY'):
            continue
        directory = source / target.get('paths', {}).get('source', '.')
        if directory.is_relative_to(source / 'tests'):
            continue
        if broad or target['id'] in affected:
            # Link consumers as well: deleting a symbol in a .cpp file can break
            # an application even when the corresponding test never calls it.
            build.add(target['name'])
    if not affected and not broad:
        # A removed or newly introduced component may not appear in the graph.
        return select(targets, tests, [], source, broad=True)
    if not selected:
        # A changed leaf application still gets the small native core regression
        # suite plus its own production build; it never becomes a test-free pass.
        selected = sorted(name for name in tests if name.startswith('shared-'))
        build.update(selected)
    if not selected or not build:
        raise ValueError('empty native selection')
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+', name) for name in build):
        raise ValueError('unsupported native target name')
    return {'targets': sorted(build), 'tests': [name + '-test' for name in selected],
            'broad': broad, 'affected_target_count': len(affected)}


def validate_input_routes(targets, source, planner):
    """A new compiled input cannot silently enter a host-only path exemption."""
    for target in targets:
        if target.get('type') not in ('EXECUTABLE', 'STATIC_LIBRARY', 'SHARED_LIBRARY', 'MODULE_LIBRARY', 'OBJECT_LIBRARY'):
            continue
        for item in target.get('sources', []):
            if item.get('isGenerated'):
                continue
            path = source / item['path']
            if path.suffix.lower() not in ('.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx', '.qrc'):
                continue
            if path.is_relative_to(source) and planner([path.relative_to(source).as_posix()])['mode'] == 'skip':
                raise ValueError(f'Native input falls under a host-only routing exemption: {path}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    reply = args.build / '.cmake/api/v1/reply'
    indexes = sorted(reply.glob('index-*.json'))
    if not indexes:
        raise ValueError('missing CMake file API reply')
    index = json.loads(indexes[-1].read_text())
    model = json.loads((reply / index['reply']['codemodel-v2']['jsonFile']).read_text())
    if len(model['configurations']) != 1:
        raise ValueError('native CI requires a single build configuration')
    targets = [json.loads((reply / entry['jsonFile']).read_text()) for entry in model['configurations'][0]['targets']]
    spec = importlib.util.spec_from_file_location('native_input_routing', Path(__file__).with_name('check.py'))
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    validate_input_routes(targets, args.source.resolve(), routing.plan)
    policy = json.loads((args.source / '.github/native-tests.json').read_text())
    plan = json.loads(args.plan.read_text())
    names = set(policy['tests'])
    if plan['mode'] == 'core':
        names = {name for name in names if name.startswith('shared-')}
    result = select(targets, names, plan['paths'], args.source.resolve(),
                    broad=plan.get('force_broad', False) or not plan['paths'])
    discovered = json.loads(subprocess.check_output(['ctest', '--test-dir', str(args.build), '--show-only=json-v1'], text=True))
    registered = {entry['name'] for entry in discovered['tests']}
    if set(result['tests']) - registered:
        raise ValueError('selected tests are missing from CTest')
    result['sha'] = plan['sha']
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
