"""Join completed, readiness-bound package records to the exact source ledger."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import PurePosixPath
from urllib.parse import urlsplit
from artifact_identity import digest_file, hex_digest, require
from conan_inventory import verify_phase
from sbom_validation import read_sbom


def _relative(value):
    require(type(value) is str and value and '\\' not in value and
            not PurePosixPath(value).is_absolute() and
            all(part not in ('', '.', '..') for part in value.split('/')), 'SOURCE_LEDGER_PATH')
    return value


def join_sources(inventory, closure):
    require(inventory.get('contract') == 'overte-sh009-conan-inventory-v1' and
            inventory.get('status') == 'CONAN_PHASE_BOUND_CONTENT_VERIFICATION_PENDING', 'SOURCE_PHASE_REQUIRED')
    require(closure.get('schema_version') == 1 and type(closure.get('nodes')) is list and
            0 < len(closure['nodes']) <= 1024 and closure.get('node_count') == len(closure['nodes']),
            'SOURCE_LEDGER_NODES')
    require(closure.get('recipe_export_index', {}).get('sha256') == inventory.get('recipeIndexSha256') and
            hex_digest(inventory.get('recipeIndexSha256')), 'SOURCE_RECIPE_INDEX')
    nodes = {}
    for node in closure['nodes']:
        require(type(node) is dict and type(node.get('reference')) is str and node['reference'] and
                node['reference'] not in nodes, 'SOURCE_REFERENCE')
        nodes[node['reference']] = node
    packages = inventory.get('packages')
    require(type(packages) is list and 0 < len(packages) <= 1024, 'SOURCE_PACKAGES')
    rows, seen = [], set()
    for package in packages:
        require(type(package) is dict and type(package.get('nodeId')) is str and
                package['nodeId'] not in seen, 'SOURCE_PACKAGE_ID')
        seen.add(package['nodeId'])
        reference, separator, revision = package.get('ref', '').rpartition('#')
        require(separator and reference in nodes and revision == package.get('rrev'), 'SOURCE_PACKAGE_REFERENCE')
        node = nodes[reference]
        require(node.get('recipe_revision') == revision and hex_digest(revision, 32), 'SOURCE_RECIPE_REVISION')
        contexts = node.get('contexts')
        require(type(contexts) is list and any(type(item) is dict and item.get('graph') == inventory.get('phase')
                                             for item in contexts), 'SOURCE_PHASE_CONTEXT')
        recipe = node.get('recipe')
        require(type(recipe) is dict and type(recipe.get('exported_files')) is dict and
                0 < len(recipe['exported_files']) <= 4096, 'SOURCE_RECIPE_FILES')
        for path, digest in recipe['exported_files'].items():
            _relative(path)
            require(hex_digest(digest), 'SOURCE_RECIPE_DIGEST')
        recipe_path = _relative(recipe.get('path'))
        require(hex_digest(recipe.get('sha256')) and
                recipe['exported_files'].get(recipe_path) == recipe['sha256'], 'SOURCE_RECIPE_MAIN')
        sources = node.get('sources')
        require(type(sources) is list and len(sources) <= 128, 'SOURCE_OBJECTS')
        classification = node.get('classification')
        require(classification in ('source-bearing', 'virtual-system') and
                bool(sources) == (classification == 'source-bearing'), 'SOURCE_CLASSIFICATION')
        objects, source_ids = [], set()
        for source in sources:
            require(type(source) is dict and type(source.get('id')) is str and source['id'] and
                    source['id'] not in source_ids and hex_digest(source.get('sha256')), 'SOURCE_OBJECT_IDENTITY')
            source_ids.add(source['id'])
            url = source.get('canonical_url')
            require(type(url) is str and len(url) <= 8192, 'SOURCE_URL')
            parsed = urlsplit(url)
            require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password,
                    'SOURCE_URL')
            license_record = source.get('license')
            require(type(license_record) is dict and hex_digest(license_record.get('sha256')) and
                    type(license_record.get('spdx')) is str and 0 < len(license_record['spdx']) <= 1024,
                    'SOURCE_LICENSE_RECORD')
            objects.append({'id': source['id'], 'sha256': source['sha256'], 'canonicalUrl': url,
                            'licensePath': _relative(license_record.get('path')),
                            'licenseSha256': license_record['sha256'],
                            'declaredLicenseLabel': license_record['spdx']})
        row = dict(package, sourceClassification=classification, sourceObjects=objects,
                   recipeFiles=dict(recipe['exported_files']))
        if classification == 'virtual-system':
            binding = node.get('system_binding')
            require(type(binding) is dict and hex_digest(binding.get('toolchain_sha256')) and
                    type(binding.get('provider')) is str and binding['provider'], 'SOURCE_SYSTEM_BINDING')
            row['systemBinding'] = {'provider': binding['provider'],
                                    'toolchainPath': _relative(binding.get('toolchain_path')),
                                    'toolchainSha256': binding['toolchain_sha256']}
        rows.append(row)
    result = dict(inventory, packages=rows)
    result.update(contract='overte-sh009-conan-source-join-v1',
                  status='CONAN_SOURCE_METADATA_BOUND_PAYLOAD_VERIFICATION_PENDING')
    return result


def verify_sources(closure_path, *phase_arguments):
    inventory = verify_phase(*phase_arguments)
    require(digest_file(closure_path) == inventory['sourceClosureSha256'], 'SOURCE_CLOSURE_HASH')
    result = join_sources(inventory, read_sbom(closure_path))
    require(digest_file(closure_path) == inventory['sourceClosureSha256'], 'SOURCE_CLOSURE_CHANGED')
    return result
