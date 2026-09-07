"""Pico-only mixed producer/reuse evidence. Never relabel Conan Cache as Build.

Cold origins are checked by unchanged SH009. Local mixed origins retain raw
Conan output, independently pinned readiness and successful worker receipts.
The caller pins and hashes every input and payload using the Pico byte inventory.
"""
import json
from artifact_identity import digest_file, hex_digest, require
from conan_inventory import BOUND_FIELDS, read_checkpoint
from conan_sources import verify_sources, join_sources
from sbom_validation import read_sbom



def producer_paths(repo):
    paths = {'conanfile.py', 'android/common/conan/conanfile-pico.py'}
    base = repo / 'android/phone/fdroid'
    for folder in ('conan', 'profiles', 'recipes/qt'):
        paths.update(p.relative_to(repo).as_posix() for p in (base/folder).rglob('*')
                     if p.is_file() and '__pycache__' not in p.parts)
    for name in ('source-closure.lock.json','qt-source.lock.json','qt-license.lock.tsv',
                 'base-toolchain.lock.json','toolchain-provisioning.lock.json',
                 'recipe-exports/index.json','recipe-exports/pkglist.json'):
        paths.add('android/phone/fdroid/manifests/'+name)
    paths.update(p.relative_to(repo).as_posix() for p in (base/'locks').glob('*.lock'))
    index = read_sbom(base/'manifests/recipe-exports/index.json')
    for ref, entry in index['recipes'].items():
        paths.update('android/phone/fdroid/manifests/recipe-exports/'+ref+'/'+name
                     for name in entry['files'])
    return sorted(paths)


def verify_producer_files(repo, spec):
    paths = producer_paths(repo)
    require(set(spec.get('producerSourceFiles', {})) == set(paths), 'PICO_REUSE_SOURCE_SET')
    require(all(digest_file(repo/p) == spec['producerSourceFiles'][p] for p in paths),
            'PICO_REUSE_PRODUCER_SOURCE_CHANGED')
    required = [p for p in paths if ('/profiles/' in p and p.rsplit('/',1)[1] in
                ('android-arm64-v8a-api26-16k','linux-x86_64-bootstrap','linux-x86_64-hosttools')) or
                p.endswith(('base-toolchain.lock.json','toolchain-provisioning.lock.json'))]
    for origin in spec.get('coldOrigins', []):
        require(set(origin.get('toolchainFiles', {})) == set(required) and
                all(origin['toolchainFiles'][p] == spec['producerSourceFiles'][p] for p in required),
                'PICO_REUSE_TOOLCHAIN_CHANGED')

def key(node):
    return tuple(node.get(k) for k in ('ref', 'package_id', 'prev'))


def semantic_node(nodes, node_id, active=()):
    require(node_id not in active and len(active) < 64, 'PICO_REUSE_GRAPH_CYCLE')
    node = nodes[node_id]
    # Conan changes edge.skip after deciding which already available binaries
    # are needed. Retain the exact raw graphs; compare all dependency identity,
    # visibility, context and package-ID semantics independently of this state.
    deps = []
    for child, edge in node['dependencies'].items():
        require(child in nodes, 'PICO_REUSE_DEPENDENCY')
        deps.append({'edge': {k: v for k, v in edge.items() if k not in ('ref', 'skip')},
                     'node': semantic_node(nodes, child, active + (node_id,))})
    return {'identity': {k: node[k] for k in BOUND_FIELDS if k not in ('dependencies', 'context')},
            'dependencies': sorted(deps, key=lambda x: json.dumps(x, sort_keys=True))}


def verify(spec, checked_path, phase, expected_source, closure, index):
    require(hex_digest(expected_source, 40), 'PICO_REUSE_APPLICATION_SOURCE')
    producer_source = spec.get('dependencySourceRevision')
    require(hex_digest(producer_source, 40), 'PICO_REUSE_PRODUCER_SOURCE')
    # A later application commit can consume the same dependency production
    # only through independently pinned, unchanged producer source inputs.
    require(type(spec.get('producerSourceFiles')) is dict and spec['producerSourceFiles'],
            'PICO_REUSE_PRODUCER_FILES')
    origins = {}
    for origin in spec.get('coldOrigins', []):
        args = [checked_path(origin[k]) for k in ('sourceClosure', 'actualGraph', 'expectedGraph', 'checkpoint')]
        old_index = checked_path(origin['recipeIndex'])
        joined = verify_sources(*args, origin['sourceRevision'], origin['phase'],
                                digest_file(args[2]), digest_file(args[0]), digest_file(old_index))
        nodes = read_sbom(args[1])['graph']['nodes']
        for row in joined['packages']:
            origins.setdefault(key(row), []).append((nodes, row['nodeId'], origin['sourceRevision']))

    def validate_graph(actual_path, expected_path, checkpoint_path, source, receipt=None, permit_skip=False):
        actual = read_sbom(actual_path)['graph']['nodes']
        pinned = read_sbom(expected_path)['graph']['nodes']
        cp = read_checkpoint(checkpoint_path)
        require(cp['name'] in ('target', 'host-tools', 'bootstrap') and
                cp['source_commit'] == source and cp['result_sha256'] == digest_file(actual_path) and
                cp['manifest_sha256'] == digest_file(closure) and
                cp['recipe_index_sha256'] == digest_file(index), 'PICO_REUSE_CHECKPOINT')
        require(type(actual) is dict and set(actual) == set(pinned) and '0' in actual and
                1 < len(actual) <= 1024, 'PICO_REUSE_NODE_SET')
        if receipt:
            require(receipt.get('exitCode') == 0 and receipt.get('sourceRevision') == source and
                    receipt.get('resultSha256') == digest_file(actual_path) and
                    receipt.get('expectedGraphSha256') == digest_file(expected_path) and
                    receipt.get('network') == 'none' and
                    receipt.get('producerSourceFiles') == spec['producerSourceFiles'], 'PICO_REUSE_WORKER_RECEIPT')
        rows = []
        for node_id, node in actual.items():
            n = pinned[node_id]
            require(node_id.isascii() and node_id.isdigit() and str(int(node_id)) == node_id and
                    node.get('id') == n.get('id') == node_id, 'PICO_REUSE_NODE_ID')
            require(node.get('remote') is None and node.get('binary_remote') is None, 'PICO_REUSE_REMOTE')
            if node_id == '0':
                require(all(node.get(k) == n.get(k) for k in ('settings', 'options', 'context')),
                        'PICO_REUSE_CONSUMER')
            else:
                require(all(node.get(k) == n.get(k) for k in BOUND_FIELDS if k != 'dependencies'),
                        'PICO_REUSE_IDENTITY')
            # Compare the whole edge structure, not just the directly named libs.
            require(set(node['dependencies']) == set(n['dependencies']) and
                    all({k:v for k,v in edge.items() if k != 'skip'} ==
                        {k:v for k,v in n['dependencies'][child].items() if k != 'skip'}
                        for child,edge in node['dependencies'].items()), 'PICO_REUSE_EDGES')
            if node_id == '0': continue
            require(n.get('binary') == 'Build', 'PICO_REUSE_READINESS')
            if permit_skip and node.get('binary') == 'Skip':
                # This is an unused node in an intermediate producer invocation,
                # never a package accepted into the final consumed phase.
                continue
            require(hex_digest(node.get('rrev'),32) and hex_digest(node.get('package_id'),40) and
                    hex_digest(node.get('prev'),32), 'PICO_REUSE_REVISION')
            require(node['ref'].endswith('#'+node['rrev']) and node['context'] in ('host','build') and
                    bool(node.get('license')), 'PICO_REUSE_REFERENCE')
            if node.get('binary') == 'Build':
                require(receipt is not None, 'PICO_REUSE_MISSING_BUILD_RECEIPT')
                origins.setdefault(key(node), []).append((actual, node_id, source))
                origin_source = source
            else:
                require(node.get('binary') == 'Cache', 'PICO_REUSE_BINARY')
                matches = [(ns,k,src) for ns,k,src in origins.get(key(node), [])
                           if semantic_node(actual,node_id) == semantic_node(ns,k)]
                require(matches, 'PICO_REUSE_UNPROVEN_CACHE')
                origin_source = matches[0][2]
            rows.append(dict(nodeId=node_id, **{k:node[k] for k in BOUND_FIELDS}, prev=node['prev'],
                             observedBinary=node['binary'], productionSourceRevision=origin_source))
        return actual, cp, rows

    # Ordered successful local invocations establish actual new Build origins.
    # Their original Cache/Skip/Build strings are retained unchanged.
    for invocation in spec.get('localBuilds', []):
        actual, expected, cp, receipt = [checked_path(invocation[k]) for k in
                                        ('actualGraph','expectedGraph','checkpoint','receipt')]
        validate_graph(actual, expected, cp, producer_source, read_sbom(receipt), permit_skip=True)
    item = spec['phases'][phase]
    actual, expected, checkpoint = [checked_path(item[k]) for k in ('actualGraph','expectedGraph','checkpoint')]
    final_receipt = read_sbom(checked_path(item['receipt'])) if item.get('receipt') else None
    raw, cp, rows = validate_graph(actual,expected,checkpoint,producer_source,final_receipt)
    require(cp['name'] == phase and cp['attempt_root'] == spec['attemptRoot'], 'PICO_REUSE_PHASE')
    inventory = dict(contract='overte-sh009-conan-inventory-v1',
                     status='CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING', phase=phase,
                     sourceRevision=expected_source, dependencySourceRevision=producer_source,
                     packages=rows, recipeIndexSha256=digest_file(index),
                     sourceClosureSha256=digest_file(closure), resultSha256=digest_file(actual),
                     expectedGraphSha256=digest_file(expected), jobs=int(cp['jobs']))
    result = join_sources(inventory,read_sbom(closure))
    result['qualification'] = 'PICO_MIXED_PRODUCTION_AND_VERIFIED_REUSE_NOT_COLD_BUILD'
    return result
