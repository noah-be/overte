// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { PUBLIC_PLACE_ENDPOINT, publicPlaceNames, isPublicIPv4, publicPlaceSelection,
    validatePublicPlace, resolvePublicPlace, validatePublicPermissions } from './public-places.mjs';
import { EXPOSED_PERMISSION_KEYS } from './validation.mjs';

const fixture = () => ({ status: 'success', data: { place: { name: 'reviewed_place', visibility: 'open',
    path: '/154.69,-98.296,-397.899/0,0.996917,0,0.0784577',
    domain: { id: '33333333-3333-3333-3333-333333333333', network_address: '178.105.253.182', network_port: 40114, active: true, capacity: 0,
        protocol_version: 'ViLohxhZMTalcuUKwgs63g==', version: 'fixture' } } } });

test('only configured public names can select the fixed anonymous directory endpoint', async () => {
    assert.deepEqual(publicPlaceNames('reviewed_place,another-place'), ['reviewed_place', 'another-place']);
    for (const input of ['../admin', 'place,place', 'PLACE', 'https://elsewhere', 'name, other']) {
        assert.throws(() => publicPlaceNames(input));
    }
    assert.equal(publicPlaceSelection('hifi://reviewed_place/', ['reviewed_place']), 'reviewed_place');
    for (const address of ['overte://other', 'overte://reviewed_place:40102', 'overte://reviewed_place/path',
        'overte://reviewed_place?admin=1', 'overte://reviewed_place.attacker.example']) {
        assert.throws(() => publicPlaceSelection(address, ['reviewed_place']));
    }
    let calls = 0;
    const result = await resolvePublicPlace('reviewed_place', ['reviewed_place'], async (url, options) => {
        calls++; assert.equal(url.href, PUBLIC_PLACE_ENDPOINT + 'reviewed_place');
        assert.equal(options.redirect, 'error'); assert.ok(options.signal);
        return new Response(JSON.stringify(fixture()));
    });
    assert.equal(calls, 1); assert.equal(result.mode, 'public-native-guest');
    assert.equal(result.nativeDomain, 'overte://178.105.253.182:40114/154.69,-98.296,-397.899/0,0.996917,0,0.0784577');
    await assert.rejects(resolvePublicPlace('attacker', ['reviewed_place'], async () => { throw Error('Must never fetch'); }), /not enabled/);
});

test('public IPv4 guard rejects local, mapped, reserved and rebinding-style destinations', () => {
    for (const address of ['0.1.2.3', '10.0.0.1', '127.0.0.2', '100.64.1.1', '169.254.1.1', '172.16.0.1',
        '192.168.1.1', '192.0.0.1', '192.0.2.1', '192.88.99.1', '198.18.1.1', '198.51.100.2',
        '203.0.113.1', '224.0.0.1', '255.255.255.255', '::ffff:127.0.0.1', '127.1', '2130706433',
        'public.example', '178.105.253.182@localhost']) assert.equal(isPublicIPv4(address), false, address);
    for (const address of ['178.105.253.182', '1.1.1.1', '100.128.1.1', '172.32.1.1', '192.0.3.1']) assert.equal(isPublicIPv4(address), true);
});

test('directory metadata fails closed on private capacity-limited or malformed places', () => {
    const mutations = [
        value => { value.status = 'error'; }, value => { value.data.place.name = 'other'; },
        value => { value.data.place.visibility = 'friends'; }, value => { value.data.place.domain.active = false; },
        value => { value.data.place.domain.capacity = 1; }, value => { value.data.place.domain.capacity = '0'; },
        value => { value.data.place.domain.network_address = '127.0.0.1'; },
        value => { value.data.place.domain.network_address = 'public.example'; },
        value => { value.data.place.domain.network_port = 65536; },
        value => { value.data.place.domain.network_port = '40114'; },
        value => { value.data.place.domain.protocol_version = 'override'; },
        value => { value.data.place.domain.id = '00000000-0000-0000-0000-000000000000'; },
        value => { value.data.place.path = '//attacker.example'; },
        value => { value.data.place.path = '/1,2,3?url=https://attacker.example'; },
    ];
    for (const mutate of mutations) { const document = fixture(); mutate(document); assert.throws(() => validatePublicPlace(document, 'reviewed_place')); }
    assert.doesNotThrow(() => validatePublicPlace(fixture(), 'reviewed_place'));
});

test('directory reads are bounded and surface actual transport errors', async () => {
    for (const response of [new Response('', { status: 403 }), new Response('invalid'), new Response('x'.repeat(1024 * 1024 + 1))]) {
        await assert.rejects(resolvePublicPlace('reviewed_place', ['reviewed_place'], async () => response));
    }
});

test('public native approval preserves ordinary rights and rejects elevated or different-domain sessions', () => {
    const permissions = Object.fromEntries(EXPOSED_PERMISSION_KEYS.map(key => [key, ['id_can_connect', 'id_can_view_asset_urls', 'id_can_rez', 'id_can_write_to_asset_server'].includes(key)]));
    const address = 'overte://178.105.253.182:40114';
    const place = validatePublicPlace(fixture(), 'reviewed_place');
    const approve = (actual, connected, id = place.domainId) => validatePublicPermissions(actual, connected, address, id, place);
    const accepted = approve(permissions, address + '/1,2,3');
    assert.equal(accepted.id_can_rez, true);
    assert.equal(accepted.id_can_write_to_asset_server, true, 'Actual ordinary anonymous asset rights are retained');
    assert.equal(Object.hasOwn(accepted, 'id_can_connect_past_max_capacity'), false, 'Unobserved capacity rights cannot be invented');
    for (const key of ['id_can_adjust_locks', 'id_can_replace_content',
        'id_can_get_and_set_private_user_data', 'id_can_kick']) {
        assert.throws(() => approve({ ...permissions, [key]: true }, address));
    }
    assert.throws(() => approve({ ...permissions, id_can_view_asset_urls: false }, address));
    assert.throws(() => approve({ ...permissions, id_can_kick: undefined }, address));
    assert.throws(() => approve(permissions, 'overte://178.105.253.183:40114'));
    assert.throws(() => approve(permissions, 'overte://178.105.253.182:40115'));
    assert.doesNotThrow(() => approve(permissions, 'hifi://reviewed_place/1,2,3'));
    assert.throws(() => approve(permissions, 'overte://another_place'));
    assert.throws(() => approve(permissions, address, '44444444-4444-4444-4444-444444444444'));
    assert.throws(() => approve(permissions, 'overte://reviewed_place', null));
});
