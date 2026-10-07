// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NavigationHistory } from './navigation-history.ts';

test('history records successful admission only and preserves the cursor after failed traversal', () => {
    const history = new NavigationHistory();
    history.commit(history.begin('overte://one'));
    history.commit(history.begin('overte://two'));
    const failed = history.traverse('back')!;
    history.cancel();
    assert.equal(history.commit(failed), false);
    assert.deepEqual(history.state, {canGoBack:true, canGoForward:false});
    const back = history.traverse('back')!;
    assert.equal(back.domain, 'overte://one');
    assert.equal(history.commit(back), true);
    assert.deepEqual(history.state, {canGoBack:false, canGoForward:true});
    history.commit(history.begin('overte://three'));
    assert.equal(history.traverse('forward'), undefined);
});
test('history refuses superseded completions, deduplicates reconnects and bounds entries', () => {
    const history = new NavigationHistory();
    const stale = history.begin('overte://stale');
    const current = history.begin('overte://current');
    assert.equal(history.commit(stale), false);
    history.commit(current);
    history.commit(history.begin('overte://current'));
    assert.equal(history.traverse('back'), undefined);
    for (let i = 0; i < 60; i++) history.commit(history.begin(`overte://world-${i}`));
    for (let i = 0; i < 49; i++) assert.equal(history.commit(history.traverse('back')!), true);
    assert.equal(history.traverse('back'), undefined);
    assert.equal(history.traverse('forward')?.domain, 'overte://world-11');
});

test('Back and Forward restore departure viewpoints without committing failed admissions', () => {
    const history = new NavigationHistory();
    const orientation = {x:0,y:1,z:0,w:0};
    assert.equal(history.rememberDeparture({position:{x:1,y:2,z:3},orientation}),false);
    history.commit(history.begin('overte://first/0,0,0/0,0,0,1'));
    assert.equal(history.rememberDeparture({position:{x:12.25,y:-4,z:9},orientation}),true);
    history.commit(history.begin('overte://second:1234'));
    assert.equal(history.rememberDeparture({position:{x:-1,y:3,z:7},orientation}),true);
    const back = history.traverse('back')!;
    assert.equal(back.domain,'overte://first/12.25,-4,9/0,1,0,0');
    history.cancel();
    assert.equal(history.commit(back),false);
    assert.deepEqual(history.state,{canGoBack:true,canGoForward:false});
    history.commit(history.traverse('back')!);
    assert.equal(history.traverse('forward')!.domain,'overte://second:1234/-1,3,7/0,1,0,0');
});

test('invalid or unauthorized viewpoint values cannot corrupt existing navigation entries', () => {
    const history = new NavigationHistory();
    history.commit(history.begin('overte://first'));
    for (const pose of [
        {position:{x:NaN,y:0,z:0},orientation:{x:0,y:0,z:0,w:1}},
        {position:{x:32768,y:0,z:0},orientation:{x:0,y:0,z:0,w:1}},
        {position:{x:0,y:0,z:0},orientation:{x:0,y:0,z:0,w:2}},
    ]) assert.equal(history.rememberDeparture(pose),false);
    history.commit(history.begin('overte://second'));
    assert.equal(history.traverse('back')!.domain,'overte://first');
});
