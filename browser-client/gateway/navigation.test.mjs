// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { admittedNavigationTarget, managedNavigationSelection, validateNativeNavigation } from './navigation.mjs';
import { publicPlaceSelection, viewpointPath } from './public-places.mjs';

const nonce = '11111111-1111-1111-1111-111111111111';
const names = ['overte_hub'];
const domain = 'overte://127.0.0.2:45102';
const place = { name: 'overte_hub', nativeDomain: 'overte://178.105.253.182:40114/1,2,3/0,0,0,1' };

test('native navigation is bound to the exact current approval and canonical nonce', () => {
    assert.deepEqual(validateNativeNavigation({ type: 'navigationHistoryRequest', nonce, permissionRevision: 4, direction: 'back' }, 4),
        { type: 'navigationHistory', nonce, permissionRevision: 4, direction: 'back' });
    for (const extra of [{ nonce: nonce.toUpperCase().replace('11111111', 'AAAAAAAA') }, { permissionRevision: 3 }, { direction: 'other' }]) {
        assert.throws(() => validateNativeNavigation({ type: 'navigationHistoryRequest', nonce, permissionRevision: 4, direction: 'back', ...extra }, 4));
    }
    assert.equal(validateNativeNavigation({ type: 'navigationRequest', nonce, permissionRevision: 4, address: 'hifi://overte_hub' }, 4).address, 'hifi://overte_hub');
    for(const address of [null,{},'x'.repeat(1025)])assert.throws(()=>validateNativeNavigation({type:'navigationRequest',nonce,permissionRevision:4,address},4),'Malformed target metadata remains a protocol violation');
});

test('viewpoints contain only finite bounded positions and normalized quaternions', () => {
    assert.equal(viewpointPath('/1e2,-2.5,+3/0,0,0,-1'), '/100,-2.5,3/0,0,0,-1');
    assert.equal(viewpointPath('/1,2,3'), '/1,2,3');
    assert.equal(publicPlaceSelection('overte://overte_hub/1,2,3/0,0,0,1', names), 'overte_hub');
    for (const path of ['/NaN,1,2', '/1,2,32768', '/1,2,3/0,0,0,0', '/1,2,3/0,0,0,1/extra', '/1,2,3/1,2,3,4', '/1%2C2%2C3', '/1,2,3/file']) assert.throws(() => viewpointPath(path));
});

test('managed bookmark positions retain the configured domain policy and cannot change authority', () => {
    assert.deepEqual(managedNavigationSelection('hifi://127.0.0.2:45102/5,1.5,3/0,0,0,1', [domain]),
        { configuredDomain: domain, domain: domain + '/5,1.5,3/0,0,0,1' });
    assert.equal(managedNavigationSelection('overte://127.0.0.3:45102', [domain]), null);
    assert.equal(managedNavigationSelection('overte://127.0.0.2:45103', [domain]), null);
    assert.throws(() => managedNavigationSelection(domain + '/1,2,Infinity', [domain]));
    assert.throws(() => managedNavigationSelection(domain + '?newDomain=remote', [domain]));
});

test('directory IP navigation maps only freshly resolved configured places, preserving a validated viewpoint', async () => {
    const calls = []; const resolve = async (name, configured) => { calls.push(name); assert.deepEqual(configured, names); return place; };
    const configuration = { domains: [domain], publicPlaces: names, resolve };
    assert.equal(await admittedNavigationTarget('178.105.253.182:40114/5,6,7/0,0,0,1', configuration), 'overte://overte_hub/5,6,7/0,0,0,1');
    assert.deepEqual(calls, ['overte_hub']);
    assert.equal(await admittedNavigationTarget('overte_hub', configuration), 'overte://overte_hub');
    await assert.rejects(admittedNavigationTarget('178.105.253.183:40114/5,6,7', configuration), /not enabled/);
    await assert.rejects(admittedNavigationTarget('178.105.253.182:40115/5,6,7', configuration), /not enabled/);
    await assert.rejects(admittedNavigationTarget('overte_hub/Infinity,2,3', configuration), /position/);
    await assert.rejects(admittedNavigationTarget('https://overte_hub', configuration), /Only Overte/);
});
