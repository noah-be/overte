#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Temporary-file native build evidence contracts; no domain, GPU or compiler."""
from pathlib import Path
import fcntl
import hashlib
import importlib.util
import json
import tempfile
import sys

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / 'browser-direct-client/lab'))
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value
snapshot = module('snapshot_contract', repo / 'browser-direct-client/lab/snapshot-runtime.py')
qualification = module('qualification_contract', repo / 'browser-direct-client/lab/qualify-native-build.py')
checks = []
def check(name, value):
    assert value, name
    checks.append(name)
def rejects(name, call, exception=RuntimeError):
    try:
        call()
    except exception:
        checks.append(name)
    else:
        raise AssertionError(name)

with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary)
    snapshot.REPO = root
    snapshot.BUILD = root / 'build/browser-direct/native'
    snapshot.ROOT = root / 'build/browser-direct/lab'
    snapshot.ACTIVE = snapshot.ROOT / 'runtime/native-runtime.json'
    snapshot.ACTIVE.parent.mkdir(parents=True)
    for target in ('domain-server', 'assignment-client'):
        path = snapshot.BUILD / target / target
        path.parent.mkdir(parents=True)
        path.write_bytes(target.encode())
    for relative in ('build/browser-direct/native/lib/libnative.so.1',
                     'build/browser-direct/native/domain-server/resources/shared.txt',
                     'domain-server/resources/original.txt',
                     'build/browser-direct/deps/prefix/lib/libtransport.so.1',
                     'build/browser-direct/deps/prefix/share/actual/metadata.txt'):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode())
    prefix = root / 'build/browser-direct/deps/prefix'
    (prefix / 'lib/libtransport.so').symlink_to('libtransport.so.1')
    (prefix / 'share/alias').symlink_to('actual', target_is_directory=True)
    source = {'source.cpp': hashlib.sha256(b'unchanged').hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()
    snapshot.source_fingerprint = lambda: (source, fingerprint)
    snapshot.read_state = lambda: {}
    snapshot.subprocess.check_output = lambda *a, **k: 'fixture-head\n'
    first = snapshot.candidate()
    check('candidate never selects a snapshot', not snapshot.ACTIVE.exists())
    selected = snapshot.capture()
    manifest = (Path(selected['snapshot']) / 'manifest.json').read_bytes()
    copied = json.loads(manifest)
    check('candidate matches actual copied runtime inventory', first['runtimeFiles'] == copied['runtimeFiles'])
    check('candidate matches copied hash including file/directory symlinks', first['runtimeSHA256'] == selected['runtimeSHA256'])
    active_before = snapshot.ACTIVE.read_bytes()
    repeated = snapshot.candidate()
    check('identical bytes match selected immutable runtime', repeated['matchesSelectedRuntime'])
    check('candidate preserves active selection and immutable manifest', snapshot.ACTIVE.read_bytes() == active_before and (Path(selected['snapshot']) / 'manifest.json').read_bytes() == manifest)
    with (root / 'build/browser-direct/native-build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rejects('candidate rejects concurrent build lock', snapshot.candidate, BlockingIOError)
    turns = iter(((source, fingerprint), ({'source.cpp': 'changed'}, 'changed')))
    snapshot.source_fingerprint = lambda: next(turns)
    rejects('candidate rejects source changes during hashing', snapshot.candidate)
    snapshot.source_fingerprint = lambda: (source, fingerprint)
    (snapshot.BUILD / 'domain-server/domain-server').unlink()
    rejects('candidate rejects missing compiled binary', snapshot.candidate)
    log = root / 'tests.log'
    report = root / 'tests.xml'
    success = '\n'.join(['Totals: 4 passed, 0 failed, 0 skipped'] * 6) + '\n100% tests passed, 0 tests failed out of 6\n'
    names = sorted(qualification.EXPECTED_TESTS)
    xml = '<testsuite>' + ''.join('<testcase name="' + name + '"/>' for name in names) + '</testsuite>'
    log.write_text(success)
    report.write_text(xml)
    check('six exact full programs pass strict log/JUnit gate', qualification.native_test_evidence(log, report)['passed'] == 6)
    log.write_text(success.replace('0 skipped', '1 skipped', 1))
    rejects('Qt method skip rejects build qualification', lambda: qualification.native_test_evidence(log, report))
    log.write_text(success.replace('4 passed', '0 passed', 1))
    rejects('zero executed Qt checks reject build qualification', lambda: qualification.native_test_evidence(log, report))
    log.write_text(success)
    report.write_text(xml.replace('/>', '><error/></testcase>', 1))
    rejects('JUnit error rejects build qualification', lambda: qualification.native_test_evidence(log, report))
    report.write_text(xml.replace(names[0], 'unclassified-program'))
    rejects('different test inventory rejects build qualification', lambda: qualification.native_test_evidence(log, report))
    report.write_text(xml)
    qualification.REPO = root
    qualification.ROOT = snapshot.ROOT
    evidence = root / 'build/browser-direct'
    before = evidence / 'before.json'
    built = evidence / 'candidate.json'
    build_log = evidence / 'build.log'
    test_log = evidence / 'tests.log'
    junit = evidence / 'tests.xml'
    output = snapshot.ROOT / 'runtime/build-qualification.json'
    before.write_text(json.dumps({'sourceFiles': source, 'sourceFingerprint': fingerprint}))
    built.write_text(json.dumps(repeated))
    build_log.write_text('fixture successful build\n')
    test_log.write_text(success)
    junit.write_text(xml)
    sys.argv = ['qualify', '--source-before', str(before), '--candidate', str(built),
                '--build-log', str(build_log), '--build-exit-code', '0', '--test-log', str(test_log),
                '--junit', str(junit), '--output', str(output)]
    qualification.snapshot.source_fingerprint = lambda: (source, fingerprint)
    later = dict(repeated, sourceFilesAtCapture={'source.cpp': 'changed'}, sourceFingerprintAtCapture='changed')
    qualification.snapshot.candidate = lambda: later
    rejects('late source change with identical runtime bytes rejects qualification', qualification.main)
    qualification.snapshot.candidate = lambda: repeated
    turns = iter(((source, fingerprint), ({'source.cpp': 'changed'}, 'changed')))
    qualification.snapshot.source_fingerprint = lambda: next(turns)
    rejects('source change immediately before final write rejects qualification', qualification.main)
    check('rejected source races never write qualification', not output.exists())
    qualification.snapshot.source_fingerprint = lambda: (source, fingerprint)
    qualification.main()
    check('successful same-byte qualification preserves original immutable manifest', output.exists() and (Path(selected['snapshot']) / 'manifest.json').read_bytes() == manifest)
print(json.dumps({'passed': len(checks), 'failed': 0, 'scope': 'temporary fake-file helper contracts; no native services or compiler invoked', 'checks': checks}))
