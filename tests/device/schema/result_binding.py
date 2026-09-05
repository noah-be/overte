"""SH-004: accept existing runner output only with exact complete identity binding."""
# SPDX-License-Identifier: Apache-2.0
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from terminal_evidence import EvidenceError, digest, fields, hex_value, read_document, require


def identifier(value):
    import re
    return type(value) is str and re.fullmatch(r'[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*', value) is not None and len(value) <= 80


def names(value):
    return type(value) is list and 0 < len(value) <= 256 and all(identifier(v) for v in value) and len(set(value)) == len(value)


def validate(root, source_sha, artifact_sha, expected_adapter, expected_platform, required_modules, physical):
    require(hex_value(source_sha, 40) and hex_value(artifact_sha, 64), 'EXPECTED_IDENTITY')
    require(identifier(expected_adapter) and expected_platform in ('android', 'ios', 'pico4'), 'EXPECTED_PRODUCT')
    require(names(required_modules) and type(physical) is bool, 'EXPECTED_SCOPE')
    catalog, _ = read_document(Path(__file__).resolve().parents[1] / 'catalog.json')
    known = {item['id']: item for item in catalog['modules']}
    require(all(item in known for item in required_modules), 'UNKNOWN_MODULE')
    root = Path(root)
    identity, _ = read_document(root / 'result-identity.json')
    fields(identity, ('contract', 'sourceRevision', 'artifactSha256', 'runSha256', 'summarySha256', 'junitSha256'))
    require(identity['contract'] == 'overte-sh004-result-v1', 'RESULT_CONTRACT')
    require(identity['sourceRevision'] == source_sha, 'STALE_SOURCE')
    require(identity['artifactSha256'] == artifact_sha, 'WRONG_ARTIFACT')
    run, run_raw = read_document(root / 'run-manifest.json')
    summary, summary_raw = read_document(root / 'summary.json')
    require(identity['runSha256'] == digest(run_raw) and identity['summarySha256'] == digest(summary_raw), 'RESULT_BYTES')
    fields(run, ('schemaVersion', 'adapter', 'suite', 'platform', 'physical', 'requireComplete',
                 'capabilities', 'modules', 'startedEpochMs', 'finishedEpochMs', 'durationSeconds', 'status'))
    require(type(run['schemaVersion']) is int and run['schemaVersion'] == 1, 'RUN_VERSION')
    require(run['adapter'] == expected_adapter and run['platform'] == expected_platform, 'WRONG_PRODUCT')
    require(run['physical'] is physical and run['requireComplete'] is True, 'INCOMPLETE_OR_WRONG_DEVICE_CLASS')
    require(identifier(run['suite']) and names(run['modules']) and set(run['modules']) == set(required_modules), 'MODULE_SET')
    require(names(run['capabilities']), 'CAPABILITIES')
    registry, _ = read_document(Path(__file__).resolve().parents[1] / 'capabilities.json')
    require(set(run['capabilities']) <= set(registry['capabilities']), 'UNKNOWN_CAPABILITY')
    require(all(set(known[item]['requires']) <= set(run['capabilities']) for item in required_modules), 'MISSING_OPERATION')
    require(run['status'] == 'passed', 'FAILED_RUN')
    start, finish, duration = run['startedEpochMs'], run['finishedEpochMs'], run['durationSeconds']
    require(type(start) is int and type(finish) is int and 0 < start <= finish, 'RUN_TIME')
    require(type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration <= 7200
            and abs((finish-start)/1000-duration) <= 5, 'RUN_DURATION')
    fields(summary, ('schemaVersion', 'adapter', 'suite', 'status', 'results'))
    require(type(summary['schemaVersion']) is int and summary['schemaVersion'] == 1 and
            summary['adapter'] == expected_adapter and summary['suite'] == run['suite'] and summary['status'] == 'passed', 'SUMMARY_HEADER')
    require(type(summary['results']) is list and len(summary['results']) == len(required_modules), 'RESULT_COUNT')
    seen = set()
    for result in summary['results']:
        fields(result, ('id', 'description', 'status', 'returncode', 'durationSeconds'))
        require(result['id'] in required_modules and result['id'] not in seen, 'RESULT_MODULE')
        seen.add(result['id'])
        require(result['status'] == 'passed' and type(result['returncode']) is int and result['returncode'] == 0, 'FAILED_OR_SKIPPED_RESULT')
        require(result['description'] == known[result['id']]['description'], 'RESULT_DESCRIPTION')
        require(type(result['durationSeconds']) in (int, float) and math.isfinite(result['durationSeconds'])
                and 0 <= result['durationSeconds'] <= duration + 5, 'MODULE_DURATION')
    junit_path = root / 'junit.xml'
    require(junit_path.is_file() and not junit_path.is_symlink(), 'MISSING_JUNIT')
    with junit_path.open('rb') as stream:
        xml = stream.read(262145)
    require(0 < len(xml) <= 262144 and digest(xml) == identity['junitSha256'], 'JUNIT_BYTES')
    require(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper(), 'XML_DECLARATION')
    try:
        tree = ET.fromstring(xml)
    except ET.ParseError as error:
        raise EvidenceError('INVALID_JUNIT') from error
    cases = list(tree.iter('testcase'))
    require(tree.tag == 'testsuite' and set(tree.attrib) == {'name', 'tests', 'failures', 'errors', 'skipped', 'time'}, 'JUNIT_ROOT')
    require(tree.get('name') == 'device-' + run['suite'] and tree.get('tests') == str(len(required_modules))
            and all(tree.get(key) == '0' for key in ('failures', 'errors', 'skipped')), 'JUNIT_COUNTS')
    require(len(cases) == len(required_modules), 'JUNIT_COUNT')
    require(not any(list(tree.iter(tag)) for tag in ('failure', 'error', 'skipped')), 'JUNIT_NONPASS')
    require({case.get('name') for case in cases} == set(required_modules), 'JUNIT_MODULE_SET')
    for element in tree.iter():
        require(element.tag in ('testsuite', 'testcase', 'system-out'), 'JUNIT_EXTRA_CONTENT')
        require(not element.tail or not element.tail.strip(), 'JUNIT_EXTRA_CONTENT')
        if element.tag == 'testcase':
            require(set(element.attrib) == {'classname', 'name', 'time'} and element.get('classname') == 'overte.device', 'JUNIT_CASE')
        if element.tag == 'system-out':
            require(not element.attrib and element.text in (None, '', 'OVT_REDACTED'), 'JUNIT_PRIVATE_TEXT')
        else:
            require(not element.text or not element.text.strip(), 'JUNIT_PRIVATE_TEXT')
        if 'time' in element.attrib:
            try:
                measured = float(element.get('time'))
            except ValueError as error:
                raise EvidenceError('JUNIT_TIME') from error
            require(math.isfinite(measured) and 0 <= measured <= duration + 5, 'JUNIT_TIME')
    return {'contract': 'overte-sh004-result-v1', 'status': 'RESULT_BOUND_NOT_NODE_ACCEPTED',
            'sourceRevision': source_sha, 'artifactSha256': artifact_sha, 'moduleCount': len(required_modules)}
