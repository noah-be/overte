"""SH-009 bounded SPDX2.3/CycloneDX1.6 cross-document profile, not payload proof."""
# SPDX-License-Identifier: Apache-2.0
import json
from pathlib import Path
from artifact_identity import IdentityError, hex_digest, require

MAX_SBOM_BYTES = 16 * 1024 * 1024


def read_sbom(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'SBOM_REGULAR_FILE')
    with path.open('rb') as stream:
        data = stream.read(MAX_SBOM_BYTES + 1)
    require(0 < len(data) <= MAX_SBOM_BYTES, 'SBOM_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'SBOM_DUPLICATE_KEY')
            result[key] = value
        return result
    try:
        result = json.loads(data, object_pairs_hook=pairs,
                            parse_constant=lambda _: (_ for _ in ()).throw(IdentityError('SBOM_NONFINITE')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise IdentityError('SBOM_JSON') from error
    require(type(result) is dict, 'SBOM_OBJECT')
    return result


def _formats(spdx, cyclone):
    # Do not feed the SPDX file parser: its duplicate/control-character cleanup
    # must not silently normalize evidence. Parse our already-strict JSON dict.
    try:
        from spdx_tools.spdx.parser.jsonlikedict.json_like_dict_parser import JsonLikeDictParser
        from spdx_tools.spdx.validation.document_validator import validate_full_spdx_document
        from cyclonedx.schema import SchemaVersion
        from cyclonedx.validation.json import JsonStrictValidator
    except ImportError as error:
        raise IdentityError('SBOM_VALIDATOR_UNAVAILABLE') from error
    require(spdx.get('spdxVersion') == 'SPDX-2.3', 'SBOM_SPDX_VERSION')
    require(cyclone.get('bomFormat') == 'CycloneDX' and cyclone.get('specVersion') == '1.6', 'SBOM_CDX_VERSION')
    try:
        document = JsonLikeDictParser().parse(spdx)
        require(not validate_full_spdx_document(document, 'SPDX-2.3'), 'SBOM_SPDX_INVALID')
        require(JsonStrictValidator(SchemaVersion.V1_6).validate_str(json.dumps(cyclone)) is None, 'SBOM_CDX_INVALID')
    except IdentityError:
        raise
    except Exception as error:
        # Parser diagnostics can contain supplied URLs/identifiers. Never print them.
        raise IdentityError('SBOM_FORMAT_INVALID') from error


def _one(values, code):
    require(len(values) == 1, code)
    return values[0]


def _package_identity(purl, name, version):
    try:
        from packageurl import PackageURL
        parsed = PackageURL.from_string(purl)
        require(parsed.to_string() == purl and parsed.name == name and parsed.version == version, 'SBOM_PURL_IDENTITY')
    except IdentityError:
        raise
    except Exception as error:
        raise IdentityError('SBOM_PURL_IDENTITY') from error


def validate_pair(spdx, cyclone, expected_source, expected_artifact):
    require(hex_digest(expected_source, 40) and hex_digest(expected_artifact), 'SBOM_EXPECTED_IDENTITY')
    require(type(spdx) is dict and type(cyclone) is dict, 'SBOM_OBJECT')
    for value, key, limit in ((spdx, 'packages', 4096), (spdx, 'relationships', 65536),
                               (cyclone, 'components', 4095), (cyclone, 'dependencies', 4096)):
        items = value.get(key, [])
        require(type(items) is list and len(items) <= limit, 'SBOM_COLLECTION_LIMIT')
    # The official SPDX model parser ignores fields outside its model. Our
    # admitted profile must reject them instead of silently dropping evidence.
    allowed = {'spdxVersion', 'dataLicense', 'SPDXID', 'name', 'documentNamespace',
               'creationInfo', 'packages', 'relationships'}
    require(set(spdx) <= allowed, 'SBOM_SPDX_PROFILE')
    require(set(cyclone) <= {'$schema', 'bomFormat', 'specVersion', 'serialNumber', 'version',
                            'metadata', 'components', 'dependencies'}, 'SBOM_CDX_PROFILE')
    for package in spdx.get('packages', []):
        require(type(package) is dict and set(package) <= {
            'SPDXID', 'name', 'versionInfo', 'downloadLocation', 'filesAnalyzed',
            'licenseConcluded', 'licenseDeclared', 'copyrightText', 'externalRefs',
            'sourceInfo', 'checksums'}, 'SBOM_SPDX_PROFILE')
        require(package.get('filesAnalyzed') is False, 'SBOM_SPDX_PROFILE')
    _formats(spdx, cyclone)
    # This version deliberately admits a flat package-level pair only. Full file,
    # snippet, nested-component or external-document profiles need their own join.
    require(not spdx.get('files') and not spdx.get('snippets') and not spdx.get('externalDocumentRefs'), 'SBOM_PROFILE')
    packages = spdx.get('packages', [])
    root = cyclone.get('metadata', {}).get('component')
    require(type(root) is dict and 0 < len(packages) <= 4096, 'SBOM_PACKAGES')
    components = [root] + cyclone.get('components', [])
    require(len(components) <= 4096, 'SBOM_PACKAGES')
    s_ids, s_inventory, c_ids, c_inventory = {}, {}, {}, {}
    for package in packages:
        refs = [item.get('referenceLocator') for item in package.get('externalRefs', [])
                if item.get('referenceCategory') == 'PACKAGE-MANAGER' and item.get('referenceType') == 'purl']
        purl = _one(refs, 'SBOM_PURL')
        require(type(purl) is str and purl.startswith('pkg:') and purl not in s_inventory, 'SBOM_PURL')
        require(package.get('SPDXID') not in s_ids, 'SBOM_DUPLICATE_ID')
        s_ids[package['SPDXID']] = purl
        license_id = package.get('licenseDeclared')
        require(type(license_id) is str and license_id not in ('', 'NONE', 'NOASSERTION'), 'SBOM_LICENSE')
        s_inventory[purl] = (package.get('name'), package.get('versionInfo'), license_id)
        _package_identity(purl, package.get('name'), package.get('versionInfo'))
    for component in components:
        require(not component.get('components') and not component.get('pedigree'), 'SBOM_PROFILE')
        purl, ref = component.get('purl'), component.get('bom-ref')
        require(type(purl) is str and purl.startswith('pkg:') and purl not in c_inventory, 'SBOM_PURL')
        require(type(ref) is str and ref and ref not in c_ids, 'SBOM_DUPLICATE_ID')
        c_ids[ref] = purl
        license_item = _one(component.get('licenses', []), 'SBOM_LICENSE')
        license_id = license_item.get('expression') or license_item.get('license', {}).get('id')
        require(type(license_id) is str and license_id, 'SBOM_LICENSE')
        c_inventory[purl] = (component.get('name'), component.get('version'), license_id)
        _package_identity(purl, component.get('name'), component.get('version'))
    require(s_inventory == c_inventory, 'SBOM_PACKAGE_MISMATCH')
    require(all(type(name) is str and name and type(version) is str and version
                for name, version, _ in s_inventory.values()), 'SBOM_PACKAGE_IDENTITY')

    describes, s_edges = [], set()
    require(len(spdx.get('relationships', [])) <= 65536, 'SBOM_RELATION_LIMIT')
    for relation in spdx.get('relationships', []):
        origin, target, kind = relation.get('spdxElementId'), relation.get('relatedSpdxElement'), relation.get('relationshipType')
        if kind == 'DESCRIBES' and origin == 'SPDXRef-DOCUMENT':
            describes.append(target)
        else:
            require(kind == 'DEPENDS_ON' and origin in s_ids and target in s_ids, 'SBOM_RELATION_PROFILE')
            edge = (s_ids[origin], s_ids[target])
            require(edge not in s_edges, 'SBOM_DUPLICATE_EDGE')
            s_edges.add(edge)
    root_id = _one(describes, 'SBOM_ROOT')
    require(root_id in s_ids and s_ids[root_id] == root['purl'], 'SBOM_ROOT')
    s_root = next(package for package in packages if package['SPDXID'] == root_id)
    s_hash = _one([item.get('checksumValue') for item in s_root.get('checksums', [])
                   if item.get('algorithm') == 'SHA256'], 'SBOM_ARTIFACT_HASH')
    c_hash = _one([item.get('content') for item in root.get('hashes', [])
                   if item.get('alg') == 'SHA-256'], 'SBOM_ARTIFACT_HASH')
    require(s_hash == c_hash == expected_artifact, 'SBOM_ARTIFACT_MISMATCH')
    source = _one([item.get('value') for item in root.get('properties', [])
                   if item.get('name') == 'overte:sourceRevision'], 'SBOM_SOURCE')
    require(source == expected_source and s_root.get('sourceInfo') == 'overte-source-revision:' + expected_source, 'SBOM_SOURCE')
    c_edges, seen_refs = set(), set()
    require(len(cyclone.get('dependencies', [])) <= 4096, 'SBOM_RELATION_LIMIT')
    for dependency in cyclone.get('dependencies', []):
        ref = dependency.get('ref')
        require(ref in c_ids and ref not in seen_refs, 'SBOM_DEPENDENCY_REF')
        seen_refs.add(ref)
        for target in dependency.get('dependsOn', []):
            require(target in c_ids, 'SBOM_DEPENDENCY_REF')
            edge = (c_ids[ref], c_ids[target])
            require(edge not in c_edges, 'SBOM_DUPLICATE_EDGE')
            c_edges.add(edge)
            require(len(c_edges) <= 65536, 'SBOM_RELATION_LIMIT')
    require(seen_refs == set(c_ids) and s_edges == c_edges, 'SBOM_DEPENDENCY_MISMATCH')
    adjacent = {purl: [] for purl in s_inventory}
    for origin, target in s_edges:
        adjacent[origin].append(target)
    reached, pending = set(), [root['purl']]
    while pending:
        current = pending.pop()
        if current not in reached:
            reached.add(current)
            pending.extend(adjacent[current])
    require(reached == set(s_inventory), 'SBOM_DISCONNECTED_PACKAGE')
    return {'status': 'SBOM_PAIR_VALID_CONTENT_VERIFICATION_PENDING', 'packages': len(packages),
            'dependencies': len(s_edges), 'sourceRevision': expected_source, 'artifactSha256': expected_artifact}
