// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runInNewContext } from 'node:vm';
import { observeLocalNotices } from './local-notice-evidence.mjs';

test('batched notices preserve original failed-model text before replacement and history eviction', () => {
    const notice = { textContent: 'Latest notice' }, window = {}; let notify;
    class Observer {
        constructor(callback) { notify = callback; }
        observe(target, settings) { assert.equal(target, notice); assert.equal(settings.childList, true); }
    }
    const document = { readyState: 'complete', getElementById: () => notice };
    runInNewContext(`(${observeLocalNotices.toString()})();`, { window, document, MutationObserver: Observer, URL, performance });
    const record = text => ({ type: 'childList', target: notice, addedNodes: [{ textContent: text }] });
    notify([record('Could not load Actual Hub model: No geometry'), record('Loaded next model')]);
    for (let index = 0; index < 200; index++) notify([record('Loaded model')]);
    const result = window.overteLocalNoticeEvidence();
    assert.equal(result.firstEntityFailure.message, 'Could not load Actual Hub model: No geometry');
    assert.equal(result.retained, 128); assert.equal(result.evicted, 75);
    notify([record('Could not load model: https://visitor:PRIVATE@assets.example/a.fbx?q=PRIVATE#PRIVATE')]);
    assert.equal(window.overteLocalNoticeEvidence().events.at(-1).message, 'Could not load model: https://assets.example/a.fbx');
    assert.ok(!JSON.stringify(window.overteLocalNoticeEvidence()).includes('PRIVATE'));
});
