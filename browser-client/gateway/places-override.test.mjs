// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile, mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { adaptPlacesScript, adaptPlacesUI, preparePlacesOverride } from './places-override.mjs';

const appSource = await readFile(new URL('../../scripts/system/places/places.js', import.meta.url), 'utf8');
const uiSource = await readFile(new URL('../../scripts/system/places/placesHtml.js', import.meta.url), 'utf8');
const channel = 'browser-places-11111111-1111-1111-1111-111111111111';
const options = { channel, homeDomain: 'overte://overte_hub' };
function signal() { const listeners = []; return { connect(fn) { listeners.push(fn); }, disconnect(fn) { const index = listeners.indexOf(fn); if (index >= 0) listeners.splice(index, 1); }, emit(...args) { listeners.slice().forEach(fn => fn(...args)); } }; }
function fixture(adapterOptions = options) {
    let clock = 1000;
    const sent = [], ui = [], lookups = [], clicked = signal(), webEventReceived = signal(), messageReceived = signal();
    const tablet = { screenChanged: signal(), webEventReceived, fromQml: signal(), emitScriptEvent: message => ui.push(message),
        addButton: () => ({ clicked, editProperties() {} }), gotoWebScreen() {}, gotoHomeScreen() {} };
    const location = { hostChanged: signal(), href: 'overte://overte_hub',
        handleLookupString: target => lookups.push(target), goBack: () => lookups.push('back'), goForward: () => lookups.push('forward') };
    const window = {}; Object.defineProperty(window, 'location', { set: target => lookups.push(target) });
    const context = { Date: class { getTime() { return clock; } }, Script: { resolvePath: () => 'file:///installed/places/', scriptEnding: signal() },
        Tablet: { getTablet: () => tablet }, PlatformInfo: { has3DHTML: () => true }, Window: window, location,
        Messages: { subscribe() {}, unsubscribe() {}, messageReceived, sendLocalMessage: (sourceChannel, text) => sent.push({ channel: sourceChannel, ...JSON.parse(text) }) },
        LocationBookmarks: { getHomeLocationAddress: () => '' } };
    vm.runInNewContext(adaptPlacesScript(appSource, adapterOptions), context); clicked.emit(); sent.length = 0;
    return { sent, ui, lookups, messageReceived, context, action(action, address) { clock += 300; webEventReceived.emit(JSON.stringify({ channel: 'com.overte.places', action, address })); } };
}

test('generated Places code preserves hostile home strings without script-tag or line-separator injection', () => {
    const homeDomain = 'overte://example.invalid/";globalThis.injected=true;//</script><script>&\u2028\u2029';
    const adapted = adaptPlacesScript(appSource, { ...options, homeDomain });
    assert.equal(adapted.includes('</script>'), false);
    assert.equal(adapted.includes('\u2028'), false);
    assert.equal(adapted.includes('\u2029'), false);
    const f = fixture({ ...options, homeDomain });
    f.action('GO_HOME');
    assert.equal(f.sent.at(-1).address, homeDomain);
    assert.equal(f.context.injected, undefined);
    assert.deepEqual(f.lookups, []);
});

test('actual Places TELEPORT/Home/history handlers request admission before any native location lookup', () => {
    const f = fixture(); f.action('TELEPORT', '178.105.253.182:40114/1,2,3/0,0,0,1'); f.action('GO_HOME'); f.action('GO_BACK'); f.action('GO_FORWARD');
    assert.deepEqual(f.lookups, []);
    assert.deepEqual(f.sent.map(({ channel: _channel, ...request }) => request), [
        { kind: 'target', address: '178.105.253.182:40114/1,2,3/0,0,0,1' },
        { kind: 'target', address: 'overte://overte_hub' }, { kind: 'history', direction: 'back' }, { kind: 'history', direction: 'forward' },
    ]);
});

test('Places history availability comes only from its private owner-local channel', () => {
    const f = fixture();
    const data = JSON.stringify({ kind: 'historyState', canGoBack: true, canGoForward: false });
    f.messageReceived.emit(channel, data, 'sender', false); assert.equal(f.ui.length, 0);
    f.messageReceived.emit('another-owner', data, 'sender', true); assert.equal(f.ui.length, 0);
    f.messageReceived.emit(channel, data, 'sender', true);
    assert.deepEqual(JSON.parse(JSON.stringify(f.ui.at(-1))), { channel: 'com.overte.places', action: 'BROWSER_HISTORY', canGoBack: true, canGoForward: false });
});

test('the real Places UI disables unavailable history controls without replacing its app', () => {
    let listener; const back = { style: {} }, forward = { style: {} };
    const document = { querySelector: selector => selector.includes('goBack') ? back : forward,
        getElementById: () => ({ style: {} }), addEventListener() {} };
    vm.runInNewContext(adaptPlacesUI(uiSource), { window: { location: { protocol: 'file:', host: '', pathname: '/places.html' } }, document,
        EventBridge: { scriptEventReceived: { connect(fn) { listener = fn; } }, emitWebEvent() {} } });
    listener({ channel: 'com.overte.places', action: 'BROWSER_HISTORY', canGoBack: false, canGoForward: true });
    assert.equal(back.disabled, true); assert.equal(forward.disabled, false);
});

test('unrecognized or additional native navigation paths fail closed during source adaptation', () => {
    assert.throws(() => adaptPlacesScript(appSource.replace('location.goBack();', 'location.handleUnknownHistory();'), options), /supported navigation/);
    assert.throws(() => adaptPlacesScript(appSource.replace('(function() {', '(function() {\nWindow.location = "unreviewed";'), options), /unreviewed native navigation/);
    assert.throws(() => adaptPlacesUI(uiSource.replace('EventBridge.scriptEventReceived.connect', 'changedAPI.connect')), /supported navigation/);
});

test('prepared Places adapters bind only actual version-matched installed files', async () => {
    const directory = await mkdtemp(join(tmpdir(), 'places-adapter-'));
    try {
        const installed = join(directory, 'installed'); await mkdir(join(installed, 'system/places'), { recursive: true });
        await writeFile(join(installed, 'defaultScripts.js'), '// installed scripts');
        await writeFile(join(installed, 'system/places/places.js'), appSource); await writeFile(join(installed, 'system/places/placesHtml.js'), uiSource);
        const worker = join(directory, 'worker'); await mkdir(worker);
        const overrides = await preparePlacesOverride(worker, { ...options, defaultScriptsURL: pathToFileURL(join(installed, 'defaultScripts.js')).href });
        assert.equal(overrides.length, 2);
        assert.ok((await readFile(overrides[0].source, 'utf8')).includes('browserPlacesNavigate'));
        assert.equal(overrides[0].target, join(installed, 'system/places/places.js'));
        assert.equal(await readFile(join(installed, 'system/places/places.js'), 'utf8'), appSource);
    } finally { await rm(directory, { recursive: true, force: true }); }
});
