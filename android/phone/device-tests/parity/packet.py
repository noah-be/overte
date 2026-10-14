#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Prepare and check operator evidence packets; never establish device acceptance."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

HERE = Path(__file__).resolve().parent
KINDS = {'screenshot', 'screen-recording', 'audio-recording', 'result-file',
         'sanitized-log', 'peer-observation', 'installation-binding'}
MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def read(path):
    require(path.is_file() and path.stat().st_size <= 1024 * 1024, 'packet size limit')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=pairs)


def source(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{40}', value), 'full source SHA required')


def digest(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'SHA256 required')


def utc(value):
    require(isinstance(value, str) and value.endswith('Z'), 'UTC timestamp required')
    datetime.fromisoformat(value[:-1] + '+00:00')


def journeys():
    definition = read(HERE / 'journeys.json')
    require(definition['schemaVersion'] == 1 and definition['product'] == 'android-phone', 'journey contract')
    entries = definition['journeys']
    require(len(entries) == 14 and {j['issue'] for j in entries} == set(range(1124, 1138)), 'fourteen milestone journeys required')
    require(len({j['id'] for j in entries}) == len(entries), 'duplicate journey')
    for journey in entries:
        require(journey['entry'] and journey['cleanup'] and journey['steps'], 'incomplete journey')
        steps = journey['steps']
        require(len({s['id'] for s in steps}) == len(steps), 'duplicate observation')
        for step in steps:
            require(step['action'] and step['expected'] and step['evidenceKinds']
                    and set(step['evidenceKinds']) <= KINDS, 'incomplete observation')
    return entries


def template(source_sha, artifact_sha, started):
    source(source_sha)
    digest(artifact_sha)
    utc(started)
    return {'schemaVersion': 1, 'scope': 'operator-packet-completeness-only',
            'sourceRevisionApp': source_sha, 'artifactSha256': artifact_sha,
            'utcStarted': started, 'environment': {'osVersion': '', 'browserProviderVersion': '',
                'buildConfiguration': '', 'referenceMp4Sha256': ''},
            'installationBinding': None,
            'journeys': {j['id']: {'issue': j['issue'], 'observations': {
                step['id']: {'status': 'pending', 'utc': '', 'note': '', 'evidence': []}
                for step in j['steps']}} for j in journeys()}}


def review(packet, artifact, expected_source, expected_artifact, evidence_root):
    source(expected_source)
    digest(expected_artifact)
    require(packet.keys() == {'schemaVersion', 'scope', 'sourceRevisionApp', 'artifactSha256',
        'utcStarted', 'environment', 'installationBinding', 'journeys'}, 'packet fields')
    require(packet['schemaVersion'] == 1 and packet['scope'] == 'operator-packet-completeness-only', 'packet scope')
    require(packet['sourceRevisionApp'] == expected_source and packet['artifactSha256'] == expected_artifact,
            'independent source/artifact expectations mismatch')
    require(artifact.is_file() and not artifact.is_symlink() and sha(artifact) == expected_artifact,
            'actual candidate bytes mismatch')
    utc(packet['utcStarted'])
    env = packet['environment']
    require(env.keys() == {'osVersion', 'browserProviderVersion', 'buildConfiguration', 'referenceMp4Sha256'},
            'environment fields')
    require(all(isinstance(v, str) and 0 < len(v) <= 256 for v in env.values()), 'environment missing')
    digest(env['referenceMp4Sha256'])
    root = evidence_root.resolve(strict=True)
    require(root.is_dir(), 'evidence directory required')
    files = {}

    def attachment(value):
        require(isinstance(value, dict) and value.keys() == {'path', 'sha256', 'kind'}, 'evidence fields')
        name = value['path']
        require(isinstance(name, str) and name and '\\' not in name and '\x00' not in name, 'evidence path')
        relative = PurePosixPath(name)
        require(not relative.is_absolute() and '..' not in relative.parts
                and relative.as_posix() == name and name != '.', 'evidence path escape')
        path = root / name
        require(not path.is_symlink() and path.resolve(strict=True).is_relative_to(root)
                and path.is_file(), 'evidence file escape or missing')
        # Parent symlinks also fail, even if their present target remains inside.
        require(all(not p.is_symlink() for p in [path, *list(path.parents)[:len(relative.parts)-1]]),
                'symlinked evidence path')
        require(0 < path.stat().st_size <= MAX_FILE, 'empty or oversized evidence')
        digest(value['sha256'])
        require(value['kind'] in KINDS, 'unknown evidence kind')
        if path not in files:
            files[path] = (path.stat().st_size, sha(path))
        require(files[path][1] == value['sha256'] and sum(v[0] for v in files.values()) <= MAX_TOTAL,
                'evidence bytes or total budget mismatch')
        return value['kind']

    require(packet['installationBinding'] is not None, 'actual installed-artifact binding attachment required')
    require(attachment(packet['installationBinding']) == 'installation-binding', 'installation binding kind')
    definitions = journeys()
    require(packet['journeys'].keys() == {j['id'] for j in definitions}, 'journey coverage mismatch')
    counts = dict.fromkeys(('pending', 'blocked', 'failed', 'observed'), 0)
    for journey in definitions:
        data = packet['journeys'][journey['id']]
        require(data.keys() == {'issue', 'observations'} and data['issue'] == journey['issue'], 'issue binding')
        require(data['observations'].keys() == {s['id'] for s in journey['steps']}, 'observation coverage mismatch')
        for step in journey['steps']:
            record = data['observations'][step['id']]
            require(record.keys() == {'status', 'utc', 'note', 'evidence'}, 'observation fields')
            require(record['status'] in counts and isinstance(record['note'], str)
                    and len(record['note']) <= 4096, 'observation status or note')
            require(isinstance(record['evidence'], list) and len(record['evidence']) <= 32, 'evidence list limit')
            kinds = {attachment(e) for e in record['evidence']}
            if record['status'] != 'pending':
                utc(record['utc'])
                require(record['note'].strip(), 'actual observation note required')
            if record['status'] == 'observed':
                require(set(step['evidenceKinds']) <= kinds, 'required evidence kind missing')
            counts[record['status']] += 1
    return {'scope': 'packet-completeness-only', 'deviceAcceptance': False,
            'readyForHumanReview': counts['observed'] == sum(counts.values()),
            'observations': counts, 'verifiedAttachmentCount': len(files)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list')
    create = commands.add_parser('template')
    create.add_argument('--source-sha', required=True)
    create.add_argument('--artifact-sha256', required=True)
    create.add_argument('--utc', required=True)
    create.add_argument('--output', required=True, type=Path)
    check = commands.add_parser('review')
    check.add_argument('--packet', required=True, type=Path)
    check.add_argument('--artifact', required=True, type=Path)
    check.add_argument('--expected-source', required=True)
    check.add_argument('--expected-artifact-sha256', required=True)
    check.add_argument('--evidence-root', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'list':
            for journey in journeys():
                print(f"#{journey['issue']} {journey['id']}: {journey['entry']}")
        elif args.command == 'template':
            data = template(args.source_sha, args.artifact_sha256, args.utc)
            with args.output.open('x') as output:
                json.dump(data, output, indent=2)
                output.write('\n')
        else:
            result = review(read(args.packet), args.artifact, args.expected_source,
                            args.expected_artifact_sha256, args.evidence_root)
            print(json.dumps(result, indent=2))
            return 0 if result['readyForHumanReview'] else 2
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
