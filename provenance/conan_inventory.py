"""Bind completed Conan phase metadata to an independently pinned readiness graph."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from artifact_identity import IdentityError, digest_file, hex_digest, require
from sbom_validation import read_sbom as read_bounded_json

BOUND_FIELDS = ('ref', 'rrev', 'package_id', 'context', 'settings', 'options', 'license', 'dependencies')


def phase_inventory(actual, expected, source, phase):
    require(hex_digest(source, 40) and phase in ('bootstrap', 'host-tools', 'target'), 'CONAN_PHASE_IDENTITY')
    try:
        actual_nodes, expected_nodes = actual['graph']['nodes'], expected['graph']['nodes']
    except (KeyError, TypeError) as error:
        raise IdentityError('CONAN_GRAPH') from error
    require(type(actual_nodes) is dict and type(expected_nodes) is dict and
            1 < len(actual_nodes) <= 1024 and set(actual_nodes) == set(expected_nodes) and '0' in actual_nodes,
            'CONAN_NODE_SET')
    require(all(type(key) is str and key.isascii() and key.isdigit() and
                len(key) <= 4 and str(int(key)) == key for key in actual_nodes), 'CONAN_NODE_ID')
    rows = []
    for node_id in sorted(actual_nodes, key=lambda value: (len(value), value)):
        node, pinned = actual_nodes[node_id], expected_nodes[node_id]
        require(type(node) is dict and type(pinned) is dict and node.get('id') == pinned.get('id') == node_id,
                'CONAN_NODE_ID')
        dependencies = node.get('dependencies')
        require(type(dependencies) is dict and set(dependencies) <= set(actual_nodes) and
                dependencies == pinned.get('dependencies'), 'CONAN_DEPENDENCIES')
        if node_id == '0':
            require(all(node.get(field) == pinned.get(field) for field in ('context', 'settings', 'options')),
                    'CONAN_CONSUMER_MISMATCH')
            continue # Consumer has no built package/PREV; its full edge map is still bound.
        require(all(field in node and field in pinned and node[field] == pinned[field] for field in BOUND_FIELDS),
                'CONAN_PINNED_PACKAGE_MISMATCH')
        require(node.get('binary') == 'Build' and pinned.get('binary') == 'Build' and
                node.get('remote') is None and node.get('binary_remote') is None, 'CONAN_BINARY_OR_REMOTE')
        require(hex_digest(node.get('rrev'), 32) and hex_digest(node.get('package_id'), 40) and
                hex_digest(node.get('prev'), 32), 'CONAN_PACKAGE_REVISION')
        require(type(node.get('ref')) is str and node['ref'].endswith('#' + node['rrev']) and
                node.get('context') in ('host', 'build'), 'CONAN_PACKAGE_REF')
        license_id = node['license']
        require((type(license_id) is str and bool(license_id)) or
                (type(license_id) is list and bool(license_id) and
                 all(type(item) is str and item for item in license_id)), 'CONAN_LICENSE_METADATA')
        # No cache/build/source filesystem paths or private environment copied.
        rows.append(dict(nodeId=node_id, **{field: node[field] for field in BOUND_FIELDS}, prev=node['prev']))
    return {'contract': 'overte-sh009-conan-inventory-v1',
            'status': 'CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING',
            'phase': phase, 'sourceRevision': source, 'packages': rows}


def read_checkpoint(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'CONAN_CHECKPOINT_FILE')
    with path.open('rb') as stream:
        data = stream.read(8193)
    require(0 < len(data) <= 8192, 'CONAN_CHECKPOINT_SIZE')
    result = {}
    try:
        for line in data.decode('utf-8').splitlines():
            key, value = line.split('=', 1)
            require(key and key not in result and value, 'CONAN_CHECKPOINT_FIELD')
            result[key] = value
    except (UnicodeError, ValueError) as error:
        raise IdentityError('CONAN_CHECKPOINT_FORMAT') from error
    require(set(result) == {'attempt_root', 'name', 'source_commit', 'manifest_sha256',
                            'recipe_index_sha256', 'result_sha256', 'jobs'}, 'CONAN_CHECKPOINT_FIELDS')
    require(result['jobs'].isdigit() and 1 <= int(result['jobs']) <= 16, 'CONAN_CHECKPOINT_JOBS')
    return result


def verify_phase(actual_path, expected_path, checkpoint_path, source, phase,
                 expected_graph_sha256, expected_manifest_sha256, expected_recipe_index_sha256):
    require(all(hex_digest(value) for value in
                (expected_graph_sha256, expected_manifest_sha256, expected_recipe_index_sha256)), 'CONAN_EXPECTED_HASH')
    require(digest_file(expected_path) == expected_graph_sha256, 'CONAN_EXPECTED_GRAPH_HASH')
    checkpoint = read_checkpoint(checkpoint_path)
    actual_digest = digest_file(actual_path)
    require(checkpoint['name'] == phase and checkpoint['source_commit'] == source and
            checkpoint['manifest_sha256'] == expected_manifest_sha256 and
            checkpoint['recipe_index_sha256'] == expected_recipe_index_sha256 and
            checkpoint['result_sha256'] == actual_digest, 'CONAN_CHECKPOINT_BINDING')
    result = phase_inventory(read_bounded_json(actual_path), read_bounded_json(expected_path), source, phase)
    require(digest_file(actual_path) == actual_digest and digest_file(expected_path) == expected_graph_sha256,
            'CONAN_INPUT_CHANGED')
    result.update(resultSha256=actual_digest, expectedGraphSha256=expected_graph_sha256,
                  sourceClosureSha256=expected_manifest_sha256, recipeIndexSha256=expected_recipe_index_sha256,
                  jobs=int(checkpoint['jobs']))
    return result
