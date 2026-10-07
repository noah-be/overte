// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { Vector3 } from 'three';
import { selectZoneSkybox, zoneContains, zoneMode } from './world-zones';
import { validateSkyboxEXR } from './skybox-exr-bounds';
import type { Entity } from './world-data';

const zone = (id: string, size: number, mode: string): Entity => ({ id, type: 'Zone', position: { x: 0, y: 0, z: 0 },
    dimensions: { x: size, y: size, z: size }, shapeType: 'box', skyboxMode: mode, skybox: { url: 'atp:/actual-sky.exr' } });

test('native smaller volume wins; inherit and disabled are independent of asset URL', () => {
    const big = zone('{11111111-1111-1111-1111-111111111111}', 20, 'enabled');
    const small = zone('{22222222-2222-2222-2222-222222222222}', 2, 'inherit');
    const entities = new Map([[big.id, big], [small.id, small]]);
    assert.equal(selectZoneSkybox(entities, new Vector3())?.entity.id, big.id);
    small.skyboxMode = 'disabled';
    assert.equal(selectZoneSkybox(entities, new Vector3())?.mode, 'disabled');
    small.skyboxMode = 'enabled';
    assert.equal(selectZoneSkybox(entities, new Vector3())?.entity.id, small.id);
    small.visible = false;
    assert.equal(selectZoneSkybox(entities, new Vector3())?.entity.id, big.id);
});

test('equal native volumes use canonical UUID order regardless of insertion order', () => {
    const first = zone('{00000001-0000-0000-0000-000000000000}', 2, 'enabled');
    const second = zone('{00000002-0000-0000-0000-000000000000}', 2, 'enabled');
    assert.equal(selectZoneSkybox(new Map([[second.id, second], [first.id, first]]), new Vector3())?.entity.id, first.id);
    assert.equal(zoneMode(undefined), 'inherit'); assert.equal(zoneMode(1), 'disabled'); assert.equal(zoneMode(2), 'enabled');
});

test('rotated native containment honors registration and actual shape, not an AABB substitute', () => {
    const value: Entity = { ...zone('rotated', 2, 'enabled'), dimensions: { x: 4, y: 2, z: 2 },
        registrationPoint: { x: 0, y: 0.5, z: 0.5 }, rotation: { x: 0, y: Math.SQRT1_2, z: 0, w: Math.SQRT1_2 } };
    assert.equal(zoneContains(value, new Map(), { x: 0, y: 0, z: -3 }), true);
    assert.equal(zoneContains(value, new Map(), { x: 3, y: 0, z: 0 }), false);
    const sphere = { ...zone('sphere', 2, 'enabled'), shapeType: 'ellipsoid' };
    assert.equal(zoneContains(sphere, new Map(), { x: 0.9, y: 0.9, z: 0 }), false);
    assert.equal(zoneContains(sphere, new Map(), { x: 0.9, y: 0, z: 0 }), true);
    assert.equal(zoneContains({ ...sphere, shapeType: 'compound' }, new Map(), new Vector3()), false);
});

function exrWindow(width: number, height: number): ArrayBuffer {
    const key = new TextEncoder().encode('dataWindow\0box2i\0'), bytes = new Uint8Array(8 + key.length + 4 + 16 + 1), view = new DataView(bytes.buffer);
    view.setUint32(0, 20000630, true); view.setUint32(4, 2, true); bytes.set(key, 8);
    const offset = 8 + key.length; view.setUint32(offset, 16, true); view.setInt32(offset + 12, width - 1, true); view.setInt32(offset + 16, height - 1, true);
    return bytes.buffer;
}

test('OpenEXR image bounds refuse allocations before decode without lowering actual resolution', () => {
    assert.doesNotThrow(() => validateSkyboxEXR(exrWindow(4096, 2048), 16384));
    assert.throws(() => validateSkyboxEXR(exrWindow(32768, 16384), 16384), /image bounds/);
    assert.throws(() => validateSkyboxEXR(exrWindow(8192, 8192), 16384), /image bounds/);
    assert.throws(() => validateSkyboxEXR(new ArrayBuffer(8), 16384), /header/);
    const multipart = exrWindow(4, 2); new DataView(multipart).setUint32(4, 2 | (1 << 12), true);
    assert.throws(() => validateSkyboxEXR(multipart, 16384), /Multipart/);
});
