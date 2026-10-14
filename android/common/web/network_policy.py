#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Explicit browser HTTP capability, including actual packaged XML selection.

This verifies Android transport configuration, not native Qt authentication or
device WebView behavior. Those need independent source/artifact qualifications.
"""
import json
from pathlib import PurePosixPath
import re
import xml.etree.ElementTree as ET

RESOURCE_NAME = 'overte_embedded_web_network_security_config'
CAPABILITY_ID = 'overte.android.embedded-web.http-https.v1'
METADATA_NAME = 'org.overte.web.NETWORK_CAPABILITY'
ANDROID = '{http://schemas.android.com/apk/res/android}'
EXPECTED_CAPABILITY = {
    'schema': 1, 'id': CAPABILITY_ID,
    'documentSchemes': ['http', 'https'],
    'androidCleartextScope': 'application',
    'tlsTrustAnchors': ['system'],
    'requiresIndependentCredentialHttps': True,
}


def xml(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 256 * 1024:
        raise ValueError('invalid or oversized network policy XML')
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)', text, re.I):
        raise ValueError('network policy XML declarations are forbidden')
    return ET.fromstring(text)


def capability(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate capability key')
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=unique)
    if value != EXPECTED_CAPABILITY or type(value.get('schema')) is not int or \
            type(value.get('requiresIndependentCredentialHttps')) is not bool:
        raise ValueError('unreviewed embedded browser network capability')
    return value


def selected_config(manifest):
    root = xml(manifest)
    app = root.find('application')
    if app is None or app.get(ANDROID + 'usesCleartextTraffic') != 'true':
        raise ValueError('HTTP capability requires an explicit true application flag')
    markers = [node for node in app.findall('meta-data')
               if node.get(ANDROID + 'name') == METADATA_NAME]
    if len(markers) != 1 or markers[0].get(ANDROID + 'value') != CAPABILITY_ID or \
            markers[0].get(ANDROID + 'resource') is not None:
        raise ValueError('missing or unreviewed browser network capability marker')
    reference = app.get(ANDROID + 'networkSecurityConfig')
    if not reference:
        raise ValueError('HTTP capability requires an explicit Network Security Config')
    return reference


def validate_config(config):
    root = xml(config)
    if root.tag != 'network-security-config' or root.attrib or len(root) != 1:
        raise ValueError('unreviewed network policy override')
    base = root[0]
    if base.tag != 'base-config' or base.attrib != {'cleartextTrafficPermitted': 'true'} or len(base) != 1:
        raise ValueError('browser HTTP scope must be explicit at application level')
    anchors = base[0]
    if anchors.tag != 'trust-anchors' or anchors.attrib or len(anchors) != 1:
        raise ValueError('unreviewed TLS trust policy')
    cert = anchors[0]
    if cert.tag != 'certificates' or cert.attrib != {'src': 'system'} or len(cert):
        raise ValueError('browser TLS must use system certificate authorities only')


def validate_source(manifest, config, capability_text):
    grant = capability(capability_text)
    if selected_config(manifest) != '@xml/' + RESOURCE_NAME:
        raise ValueError('source manifest selects a different network resource')
    validate_config(config)
    return grant


def packaged_config_paths(manifest, resource_inventory):
    """Resolve actual AAPT resource IDs/files, including optimized res/a.xml names.

    Every configuration variant must be decoded and validated, so a qualifier
    cannot silently replace the default trust/HTTP policy.
    """
    reference = selected_config(manifest)
    current = None
    entries = []
    for line in resource_inventory.splitlines():
        match = re.match(r'^\s*resource\s+(0x[0-9a-fA-F]{8})\s+(?:[\w.]+:)?xml/' + RESOURCE_NAME + r'\s*$', line)
        if re.match(r'^\s*resource\s+', line):
            current = None
        if match:
            current = {'id': match[1].lower(), 'paths': []}
            entries.append(current)
        elif current is not None:
            file_match = re.search(r'\(file\)\s+(\S+)\s+type=XML\s*$', line)
            if file_match:
                name = file_match[1]
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or '\\' in name or \
                        not re.fullmatch(r'res/[A-Za-z0-9_./-]+\.xml', name):
                    raise ValueError('unsafe packaged network resource path')
                current['paths'].append(name)
    if len(entries) != 1 or not entries[0]['paths']:
        raise ValueError('missing or ambiguous packaged browser network resource')
    if reference != '@xml/' + RESOURCE_NAME:
        resource_id = re.fullmatch(r'@(?:ref/)?(0x[0-9a-fA-F]{8})', reference)
        if not resource_id or resource_id[1].lower() != entries[0]['id']:
            raise ValueError('packaged manifest selects a different network resource ID')
    return sorted(set(entries[0]['paths']))


def validate_artifact(manifest, inventory, configs, capability_text):
    grant = capability(capability_text)
    paths = packaged_config_paths(manifest, inventory)
    if set(configs) != set(paths):
        raise ValueError('not every packaged network configuration was decoded')
    for path in paths:
        validate_config(configs[path])
    return grant
