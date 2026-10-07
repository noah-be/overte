// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { browserIdentity, domainEndpoint } from './local-tablet-data';

test('domain selection preserves the direct server endpoint and rejects executable or credential-bearing addresses', () => {
    assert.equal(domainEndpoint('  https://domain.example:40101/browser  '), 'https://domain.example:40101/browser');
    assert.equal(domainEndpoint('ws://127.0.0.1:40107'), 'ws://127.0.0.1:40107');
    for (const value of ['', 'domain.example', 'javascript:alert(1)', 'file:///etc/passwd', 'https://user:password@example.com', 'https://example.com/#key'])
        assert.throws(() => domainEndpoint(value));
});
test('avatar preferences preserve the actual asset and reject invalid names, scale and script URLs', () => {
    assert.deepEqual(browserIdentity(' Alice ', 'atp:/avatars/alice.fst', 1.2), { displayName: 'Alice', skeletonModelURL: 'atp:/avatars/alice.fst', scale: 1.2 });
    assert.equal(browserIdentity('Visitor', 'qrc:/meshes/defaultAvatar_full.fst', 1).skeletonModelURL, 'qrc:/meshes/defaultAvatar_full.fst');
    assert.throws(() => browserIdentity('', '', 1)); assert.throws(() => browserIdentity('Name\nInjected', '', 1));
    assert.throws(() => browserIdentity('Alice', 'javascript:alert(1)', 1)); assert.throws(() => browserIdentity('Alice', 'https://user:secret@example.org/a.fst', 1));
    assert.throws(() => browserIdentity('Alice', '', NaN)); assert.throws(() => browserIdentity('Alice', '', 0));
});
