// SPDX-License-Identifier: Apache-2.0
// Exercise the real shipped event handler with native boundaries stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
let handler;
const jumps = [];
const signal = { connect() {}, disconnect() {} };
const tablet = {
    addButton: () => ({ clicked: signal }),
    webEventReceived: { connect(fn) { handler = fn; } },
    screenChanged: signal
};
const globals = { findableBy: 'friends', username: 'fixture' };
const context = {
    Script: { getExternalPath() { return 'about:blank'; }, ExternalPaths: {},
        resourcesPath() { return ''; }, scriptEnding: signal },
    Account: { metaverseServerURL: 'https://example.invalid' },
    GlobalServices: globals,
    Tablet: { getTablet: () => tablet },
    location: { goToUser: value => jumps.push(value) }
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../scripts/system/tablet-users.js'), 'utf8'), context);
handler({ type: 'jump-to', data: {} });
assert.deepEqual(jumps, [], 'missing username must not trigger navigation');
handler(JSON.stringify({ type: 'jump-to', data: { username: 'fixture-user' } }));
assert.deepEqual(jumps, ['fixture-user']);
handler({ type: 'toggle-visibility', data: {} });
assert.equal(globals.findableBy, 'friends', 'missing visibility must preserve the current setting');
handler({ type: 'toggle-visibility', data: { visibility: 'none' } });
assert.equal(globals.findableBy, 'none');
console.log('PASS: shipped users handler preserves absent fields and accepts provided fields');
