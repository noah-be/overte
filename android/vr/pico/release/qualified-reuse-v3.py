"""Pico V3 immutable producer lineage and completed mixed-production evidence.

This verifies pinned bytes and relationships, not an authenticated build attestation.
Transport receipts never establish a Build origin. V1/V2 validators are unchanged.
"""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

from artifact_identity import digest_file, hex_digest, require
from conan_inventory import BOUND_FIELDS, read_checkpoint
from conan_sources import join_sources, verify_sources
from sbom_validation import read_sbom

legacy_spec = importlib.util.spec_from_file_location('pico_reuse_v2', Path(__file__).with_name('qualified-reuse.py'))
legacy = importlib.util.module_from_spec(legacy_spec)
legacy_spec.loader.exec_module(legacy)
PHASES = ('bootstrap', 'host-tools', 'target')
SOURCE_ROOT = 'android/phone/fdroid/'
MANIFEST = SOURCE_ROOT + 'manifests/source-closure.lock.json'
INDEX = SOURCE_ROOT + 'manifests/recipe-exports/index.json'


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def git_map(repo, revision):
    """Read the complete owning producer closure from the exact local Git commit."""
    require(hex_digest(revision, 40), 'PICO_V3_PRODUCER_REVISION')
    require(subprocess.check_output(['git', '-C', str(repo), 'cat-file', '-t', revision], timeout=10).strip() == b'commit',
            'PICO_V3_PRODUCER_COMMIT')
    records = subprocess.check_output(['git', '-C', str(repo), 'ls-tree', '-r', '-z', revision], timeout=15)
    blobs = {}
    for record in records.split(b'\0'):
        if not record: continue
        metadata, path = record.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        if kind == 'blob': blobs[path.decode()] = (mode, blob)
    paths = {'conanfile.py', 'android/common/conan/conanfile-pico.py'}
    paths.update(p for p in blobs if '__pycache__' not in p.split('/') and
                 any(p.startswith(SOURCE_ROOT + folder + '/') for folder in ('conan', 'profiles', 'recipes/qt')))
    paths.update(SOURCE_ROOT + 'manifests/' + name for name in
        ('source-closure.lock.json', 'qt-source.lock.json', 'qt-license.lock.tsv', 'base-toolchain.lock.json',
         'toolchain-provisioning.lock.json', 'recipe-exports/index.json', 'recipe-exports/pkglist.json'))
    paths.update(p for p in blobs if p.startswith(SOURCE_ROOT + 'locks/') and
                 '/' not in p[len(SOURCE_ROOT + 'locks/'):] and p.endswith('.lock'))
    require(INDEX in blobs and blobs[INDEX][0] in ('100644', '100755'), 'PICO_V3_GIT_INDEX')
    index = json.loads(subprocess.check_output(['git', '-C', str(repo), 'cat-file', 'blob', blobs[INDEX][1]], timeout=10))
    for ref, entry in index['recipes'].items():
        paths.update(SOURCE_ROOT + 'manifests/recipe-exports/' + ref + '/' + name for name in entry['files'])
    require(0 < len(paths) <= 4096 and all(p in blobs and blobs[p][0] in ('100644', '100755') for p in paths),
            'PICO_V3_GIT_SOURCE_SET')
    # The object IDs select immutable Git blobs; SHA256 remains the external byte identity.
    ordered = sorted(paths)
    data = subprocess.check_output(['git', '-C', str(repo), 'cat-file', '--batch'],
                                  input=('\n'.join(blobs[p][1] for p in ordered) + '\n').encode(), timeout=30)
    result, offset = {}, 0
    for path in ordered:
        end = data.index(b'\n', offset)
        identifier, kind, length = data[offset:end].split()
        size = int(length)
        require(kind == b'blob' and identifier.decode() == blobs[path][1] and 0 <= size <= 16 * 1024 * 1024,
                'PICO_V3_GIT_BLOB')
        start = end + 1
        require(len(data) > start + size and data[start + size:start + size + 1] == b'\n', 'PICO_V3_GIT_BLOB')
        result[path] = hashlib.sha256(data[start:start + size]).hexdigest()
        offset = start + size + 1
    require(offset == len(data), 'PICO_V3_GIT_BLOB')
    return result


def verify_producer_files(repo, spec):
    current = spec.get('dependencySourceRevision')
    producers = spec.get('producerRevisions')
    require(hex_digest(current, 40) and type(producers) is dict and current in producers and
            0 < len(producers) <= 64, 'PICO_V3_PRODUCERS')
    for revision, producer in producers.items():
        require(type(producer) is dict and producer.get('sourceRevision') == revision and
                type(producer.get('sourceFiles')) is dict and
                producer.get('sourceFilesSha256') == object_hash(producer['sourceFiles']), 'PICO_V3_SOURCE_MAP')
        require(producer['sourceFiles'] == git_map(repo, revision), 'PICO_V3_HISTORICAL_SOURCE_MAP')
    files = producers[current]['sourceFiles']
    require(set(files) == set(legacy.producer_paths(repo)) and
            all((repo / path).is_file() and not (repo / path).is_symlink() and
                (repo / path).resolve() == repo / path and digest_file(repo / path) == digest
                for path, digest in files.items()), 'PICO_V3_CURRENT_SOURCE_MAP')
    require(files.get(SOURCE_ROOT + 'recipes/qt/patches/qt-pico-android-runtime.patch') ==
            digest_file(repo / 'android/common/conan/patches/qt-pico-android-runtime.patch'), 'PICO_V3_RUNTIME_PATCH')


def semantic_node(nodes, node_id, active=(), memo=None):
    """Hash a dependency DAG once per node; cached subtrees retain depth checks."""
    memo = {} if memo is None else memo
    def visit(identifier, ancestors):
        require(identifier not in ancestors and len(ancestors) < 64, 'PICO_V3_DEPENDENCY_CYCLE')
        if identifier in memo:
            digest, height = memo[identifier]
            require(len(ancestors) + height <= 64, 'PICO_V3_DEPENDENCY_DEPTH')
            return digest, height
        node = nodes[identifier]
        children, heights = [], []
        for child, edge in node['dependencies'].items():
            require(child in nodes, 'PICO_V3_DEPENDENCY')
            digest, height = visit(child, ancestors + (identifier,))
            children.append({'edge': {k:v for k,v in edge.items() if k not in ('ref','skip')}, 'node':digest})
            heights.append(height)
        identity = {k:node.get(k) for k in (*BOUND_FIELDS, 'prev') if k != 'dependencies'}
        # Only reuse comparison normalizes an identical native Linux tool package's role.
        # Actual graph context still matches its exact readiness context separately.
        if node.get('context') in ('host','build') and node.get('settings', {}).get('os') == 'Linux' and node['settings'].get('arch') == 'x86_64':
            identity['context'] = 'linux-x86_64-host-or-build'
        height = 1 + max(heights, default=0)
        digest = object_hash({'identity':identity, 'dependencies':sorted(children, key=lambda x:json.dumps(x, sort_keys=True))})
        memo[identifier] = digest, height
        return digest, height
    return visit(node_id, active)[0]


def verify(spec, checked_path, phase, expected_source, closure, index, repo):
    require(spec.get('contract') == 'overte-pico-qualified-inputs-v3' and hex_digest(expected_source, 40),
            'PICO_V3_APPLICATION_SOURCE')
    current = spec['dependencySourceRevision']
    producers = spec['producerRevisions']
    require(set(spec.get('phases', {})) == set(PHASES), 'PICO_V3_FINAL_PHASES')
    origins, evidence, semantic_caches = {}, [], {}
    require(type(spec.get('coldOrigins', [])) is list and len(spec.get('coldOrigins', [])) <= 192 and
            type(spec.get('localBuilds', [])) is list and len(spec.get('localBuilds', [])) <= 256, 'PICO_V3_EVIDENCE_LIMIT')
    graph_budget = [0, 0]

    def bound_graph(nodes):
        graph_budget[0] += len(nodes)
        graph_budget[1] += sum(len(node.get('dependencies', {})) for node in nodes.values())
        require(graph_budget[0] <= 32768 and graph_budget[1] <= 262144, 'PICO_V3_GRAPH_BUDGET')

    def semantic(nodes, node_id):
        # Retaining the object prevents id reuse between different immutable parsed graphs.
        _, memo = semantic_caches.setdefault(id(nodes), (nodes, {}))
        return semantic_node(nodes, node_id, memo=memo)

    def pinned(item, name):
        require(type(item) is dict and type(item.get(name)) is str, 'PICO_V3_ARTIFACT_REQUIRED')
        path = checked_path(item[name])
        require(hex_digest(item.get('bindings', {}).get(name)) and
                digest_file(path) == item['bindings'][name], 'PICO_V3_ARTIFACT_BINDING')
        return path

    def producer(item):
        revision = item.get('sourceRevision')
        require(revision in producers and item.get('producerSourceFilesSha256') ==
                producers[revision]['sourceFilesSha256'], 'PICO_V3_INVOCATION_PRODUCER')
        return revision, producers[revision]['sourceFiles']

    def source_inputs(item):
        revision, files = producer(item)
        ledger, recipes = pinned(item, 'sourceClosure'), pinned(item, 'recipeIndex')
        require(digest_file(ledger) == files.get(MANIFEST) and digest_file(recipes) == files.get(INDEX),
                'PICO_V3_LEDGER_PRODUCER')
        source_ledger, recipe_index = read_sbom(ledger), read_sbom(recipes)
        for node in source_ledger['nodes']:
            exported = node['recipe']['exported_files']
            require(all(files.get(path) == digest for path, digest in exported.items()), 'PICO_V3_RECIPE_PRODUCER')
            entry = recipe_index['recipes'].get(node['reference'])
            require(type(entry) is dict and entry.get('rrev') == node['recipe_revision'] and
                    all(exported.get(SOURCE_ROOT + 'manifests/recipe-exports/' + node['reference'] + '/' + path) == digest
                        for path, digest in entry['files'].items()), 'PICO_V3_RECIPE_INDEX')
        return revision, files, ledger, recipes

    def inventory(nodes, item, cp, rows):
        return dict(contract='overte-sh009-conan-inventory-v1',
                    status='CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING', phase=item['phase'],
                    sourceRevision=item['sourceRevision'], packages=rows,
                    recipeIndexSha256=item['bindings']['recipeIndex'],
                    sourceClosureSha256=item['bindings']['sourceClosure'],
                    resultSha256=item['bindings']['actualGraph'], expectedGraphSha256=item['bindings']['expectedGraph'],
                    jobs=int(cp['jobs']))

    def configuration(item):
        names = item.get('buildConfigurationIds', [])
        configs = item.get('buildConfigurations', {})
        require(type(names) is list and len(names) == len(set(names)) and type(configs) is dict and
                set(names) == set(configs), 'PICO_V3_CONFIGURATION_SET')
        for config in configs.values():
            require(type(config) is dict and hex_digest(config.get('sourceRevision'), 40) and
                    config.get('sourcePath') == 'android/vr/pico/conan/openxr-16k', 'PICO_V3_CONFIGURATION_SOURCE')
            require(subprocess.check_output(['git', '-C', str(repo), 'cat-file', '-t',
                config['sourceRevision']], timeout=10).strip() == b'commit', 'PICO_V3_CONFIGURATION_COMMIT')
            value = subprocess.check_output(['git', '-C', str(repo), 'show',
                config['sourceRevision'] + ':' + config['sourcePath']], timeout=10)
            require(hashlib.sha256(value).hexdigest() == config.get('sha256') and
                    digest_file(checked_path(config['stagedPath'])) == config['sha256'], 'PICO_V3_CONFIGURATION_BYTES')
        return names, configs, object_hash(configs)

    def origin_matches(nodes, node_id):
        return [record for record in origins.get(legacy.key(nodes[node_id]), [])
                if semantic(nodes, node_id) == semantic(record['nodes'], record['nodeId'])]

    def prove(nodes, node_id, item, receipt_hash, active=(), memo=None):
        require(node_id not in active and len(active) < 64, 'PICO_V3_DEPENDENCY_CYCLE')
        memo = {} if memo is None else memo
        if node_id in memo:
            require(len(active) + memo[node_id]['height'] <= 64, 'PICO_V3_DEPENDENCY_DEPTH')
            return memo[node_id]
        node = nodes[node_id]
        # Every consumed dependency, including dependencies of new Build nodes,
        # must itself resolve to actual Build evidence. A skipped child cannot qualify a parent.
        dependencies = []
        for child in node['dependencies']:
            require(child in nodes and nodes[child].get('binary') != 'Skip', 'PICO_V3_UNPROVEN_DEPENDENCY')
            dependencies.append(prove(nodes, child, item, receipt_hash, active + (node_id,), memo))
        if node['binary'] == 'Build':
            record = dict(nodes=nodes, nodeId=node_id, sourceRevision=item['sourceRevision'],
                          receiptSha256=receipt_hash, checkpointSha256=item['bindings']['checkpoint'],
                          dependencies=dependencies, height=1 + max((child['height'] for child in dependencies), default=0))
            origins.setdefault(legacy.key(node), []).append(record)
            memo[node_id] = record
            return record
        require(node['binary'] == 'Cache', 'PICO_V3_BINARY')
        matches = origin_matches(nodes, node_id)
        require(matches, 'PICO_V3_UNPROVEN_CACHE')
        memo[node_id] = matches[0]
        return matches[0]

    for item in spec.get('coldOrigins', []):
        source, files, ledger, recipes = source_inputs(item)
        actual, readiness, checkpoint = [pinned(item, name) for name in ('actualGraph', 'expectedGraph', 'checkpoint')]
        joined = verify_sources(ledger, actual, readiness, checkpoint, source, item['phase'],
                                item['bindings']['expectedGraph'], item['bindings']['sourceClosure'], item['bindings']['recipeIndex'])
        nodes = read_sbom(actual)['graph']['nodes']
        cp = read_checkpoint(checkpoint)
        bound_graph(nodes)
        require(cp['attempt_root'] == item.get('attemptRoot'), 'PICO_V3_ORIGIN_ATTEMPT')
        proof_memo = {}
        for row in joined['packages']:
            prove(nodes, row['nodeId'], item, None, memo=proof_memo)

    def invocation(item, final=False):
        source, files, ledger, recipes = source_inputs(item)
        actual_path, ready_path, cp_path, receipt_path = [pinned(item, name) for name in
            ('actualGraph', 'expectedGraph', 'checkpoint', 'receipt')]
        actual = read_sbom(actual_path)['graph']['nodes']
        planned = read_sbom(ready_path)['graph']['nodes']
        cp, receipt = read_checkpoint(cp_path), read_sbom(receipt_path)
        require(item.get('phase') in PHASES and cp['name'] == item['phase'] and cp['source_commit'] == source and
                cp['attempt_root'] == item.get('attemptRoot') and cp['result_sha256'] == digest_file(actual_path) and
                cp['manifest_sha256'] == digest_file(ledger) and cp['recipe_index_sha256'] == digest_file(recipes),
                'PICO_V3_CHECKPOINT')
        require(receipt.get('contract') in ('overte-pico-local-producer-receipt-v1', 'overte-pico-local-producer-receipt-v3') and
                receipt.get('exitCode') == 0 and receipt.get('network') == 'none' and receipt.get('sourceRevision') == source and
                receipt.get('producerSourceFiles') == files and receipt.get('resultSha256') == digest_file(actual_path) and
                receipt.get('expectedGraphSha256') == digest_file(ready_path) and receipt.get('jobs') == int(cp['jobs']),
                'PICO_V3_WORKER_RECEIPT')
        names, configs, config_hash = configuration(item)
        require(receipt.get('buildConfigurationIds', []) == names and receipt.get('buildConfigurations', {}) == configs,
                'PICO_V3_CONFIGURATION_RECEIPT')
        if source == current:
            require(receipt['contract'] == 'overte-pico-local-producer-receipt-v3', 'PICO_V3_CURRENT_RECEIPT')
        if receipt['contract'] == 'overte-pico-local-producer-receipt-v3':
            for field, artifact in (('checkpointSha256', 'checkpoint'), ('sourceClosureSha256', 'sourceClosure'),
                                    ('recipeIndexSha256', 'recipeIndex'), ('buildLogSha256', 'buildLog'),
                                    ('workerExitSha256', 'workerExit'), ('invocationSha256', 'invocation')):
                require(receipt.get(field) == digest_file(pinned(item, artifact)), 'PICO_V3_EXECUTION_BINDING')
            require(receipt.get('producerSourceFilesSha256') == item['producerSourceFilesSha256'] and
                    receipt.get('configurationSha256') == config_hash, 'PICO_V3_EXECUTION_PRODUCER')
            require(pinned(item, 'workerExit').read_bytes().strip() == b'0', 'PICO_V3_WORKER_EXIT')
            execution = read_sbom(pinned(item, 'invocation'))
            expected_bindings = {name:item['bindings'][name] for name in
                                ('actualGraph', 'expectedGraph', 'checkpoint', 'sourceClosure', 'recipeIndex', 'buildLog', 'workerExit')}
            require(execution.get('sourceRevision') == source and execution.get('producerSourceFilesSha256') ==
                    item['producerSourceFilesSha256'] and execution.get('configurationSha256') == config_hash and
                    execution.get('phase') == item['phase'] and execution.get('attemptRoot') == item['attemptRoot'] and
                    execution.get('bindings') == expected_bindings and execution.get('exitCode') == 0 and
                    execution.get('network') == 'none' and execution.get('jobs') == int(cp['jobs']) and
                    type(execution.get('command')) is list and execution['command'] and
                    all(type(arg) is str and arg for arg in execution['command']), 'PICO_V3_INVOCATION')
        require(type(actual) is dict and '0' in actual and 1 < len(actual) <= 1024 and set(actual) == set(planned),
                'PICO_V3_NODE_SET')
        rows = []
        for node_id, node in actual.items():
            expected = planned[node_id]
            require(type(node_id) is str and node_id.isascii() and node_id.isdigit() and len(node_id) <= 4 and
                    str(int(node_id)) == node_id and node.get('id') == expected.get('id') == node_id, 'PICO_V3_NODE_ID')
            require(node.get('remote') is None and node.get('binary_remote') is None, 'PICO_V3_REMOTE')
            if node_id == '0':
                require(all(node.get(k) == expected.get(k) for k in ('context','settings','options')), 'PICO_V3_CONSUMER')
            else:
                require(all(k in node and k in expected and node[k] == expected[k] for k in BOUND_FIELDS if k != 'dependencies'),
                        'PICO_V3_IDENTITY')
                require(expected.get('binary') == 'Build', 'PICO_V3_READINESS')
            require(type(node.get('dependencies')) is dict and set(node['dependencies']) <= set(actual) and
                    set(node['dependencies']) == set(expected.get('dependencies', {})) and
                    all({k:v for k,v in edge.items() if k != 'skip'} ==
                        {k:v for k,v in expected['dependencies'][child].items() if k != 'skip'}
                        for child, edge in node['dependencies'].items()), 'PICO_V3_EDGES')
            if node_id == '0': continue
            if node.get('binary') == 'Skip' and not final: continue
            require(hex_digest(node.get('rrev'),32) and hex_digest(node.get('package_id'),40) and
                    hex_digest(node.get('prev'),32) and node['ref'].endswith('#' + node['rrev']) and
                    node['context'] in ('host','build') and bool(node.get('license')), 'PICO_V3_PACKAGE_REVISION')
            rows.append(dict(nodeId=node_id, **{k:node[k] for k in BOUND_FIELDS}, prev=node['prev'], observedBinary=node['binary']))
        bound_graph(actual)
        joined = join_sources(inventory(actual, item, cp, rows), read_sbom(ledger))
        proof_memo = {}
        for row in joined['packages']:
            production = prove(actual, row['nodeId'], item, item['bindings']['receipt'], memo=proof_memo)
            row['productionSourceRevision'] = production['sourceRevision']
            row['productionSourceFilesSha256'] = producers[production['sourceRevision']]['sourceFilesSha256']
            row['productionReceiptSha256'] = production['receiptSha256']
            row['productionCheckpointSha256'] = production['checkpointSha256']
        evidence.append(item['bindings']['receipt'])
        return joined

    for item in spec.get('localBuilds', []): invocation(item)
    finals = {}
    for name in PHASES:
        item = spec['phases'][name]
        require(item.get('phase') == name and item.get('sourceRevision') == current and
                item.get('attemptRoot') == spec['attemptRoot'], 'PICO_V3_FINAL_PRODUCER')
        finals[name] = invocation(item, final=True)
    require(digest_file(closure) == spec['phases'][phase]['bindings']['sourceClosure'] and
            digest_file(index) == spec['phases'][phase]['bindings']['recipeIndex'], 'PICO_V3_FINAL_LEDGER')
    result = finals[phase]
    result.update(sourceRevision=expected_source, dependencySourceRevision=current,
                  producerSourceFilesSha256=producers[current]['sourceFilesSha256'],
                  qualification='PICO_V3_MIXED_PRODUCTION_AND_VERIFIED_REUSE_NOT_COLD_BUILD',
                  invocationReceiptSha256=evidence)
    return result
