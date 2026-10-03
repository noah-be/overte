// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { Scene, Color, Texture, Mesh, BoxGeometry, MeshBasicMaterial, PerspectiveCamera, Group } from 'three';
import { WorldZoneSkybox } from './world-zone-skybox';
import { observeEntityRendering } from './entity-render-evidence';
import type { ZoneSkyboxSelection } from './world-zones';

const selection: ZoneSkyboxSelection = { entity: { id: 'zone', type: 'Zone' }, mode: 'enabled', source: 'atp:/real-sky.exr', color: [1, 1, 1] };
const turn = () => new Promise(resolve => setImmediate(resolve));

test('late skybox pixels after source revocation cannot publish and are disposed once', async () => {
    const scene = new Scene(); scene.background = new Color('blue'); const signal = new AbortController();
    let supply!: (texture: Texture) => void;
    const skybox = new WorldZoneSkybox(scene, { signal: signal.signal,
        load: () => new Promise(resolve => { supply = resolve; }), prepare: async () => {}, assertCurrent: () => {}, warn: () => {} });
    skybox.select(selection, new Map()); skybox.select(undefined, new Map());
    const texture = new Texture({ width: 4, height: 2 }); let disposal = 0; texture.addEventListener('dispose', () => disposal++);
    supply(texture); await turn();
    assert.equal(disposal, 1); assert.equal(skybox.diagnostics().state, 'default'); assert.equal(scene.children.length, 0);
    signal.abort();
});

test('skybox prepare revocation releases the installed map once and cannot mark ready', async () => {
    const scene = new Scene(), signal = new AbortController(); const texture = new Texture({ width: 4, height: 2 });
    let finish!: () => void, disposal = 0; texture.addEventListener('dispose', () => disposal++);
    const skybox = new WorldZoneSkybox(scene, { signal: signal.signal, load: async () => texture,
        prepare: () => new Promise(resolve => { finish = resolve; }), assertCurrent: () => {}, warn: () => {} });
    skybox.select(selection, new Map()); await turn(); assert.equal(scene.children.length, 1);
    skybox.select(undefined, new Map()); finish(); await turn();
    assert.equal(disposal, 1); assert.equal(scene.children.length, 0); assert.equal(skybox.diagnostics().state, 'default');
    signal.abort();
});

test('unsupported skybox layout remains an explicit failure with the actual authored color', async () => {
    const scene = new Scene(), signal = new AbortController(), warnings: string[] = [];
    const skybox = new WorldZoneSkybox(scene, { signal: signal.signal, load: async () => new Texture({ width: 6, height: 4 }),
        prepare: async () => {}, assertCurrent: () => {}, warn: message => warnings.push(message) });
    skybox.select(selection, new Map()); await turn();
    assert.equal(skybox.diagnostics().state, 'error'); assert.equal(skybox.diagnostics().renderedDraws, 0);
    assert.ok(warnings[0].includes('equirectangular')); assert.ok(scene.background instanceof Color); signal.abort();
});

test('bounded draw observer restores the actual mesh callback after owner abort', async () => {
    const signal = new AbortController(), camera = new PerspectiveCamera(), root = new Group(), mesh = new Mesh(new BoxGeometry(), new MeshBasicMaterial());
    root.add(mesh); const original = mesh.onAfterRender;
    const pending = observeEntityRendering(new Map([['actual', { id: 'actual', type: 'Model' }]]), new Map([['actual', root]]), camera,
        ['actual'], signal.signal, () => {}, 100);
    assert.notEqual(mesh.onAfterRender, original); signal.abort(); await assert.rejects(pending, { name: 'AbortError' });
    assert.equal(mesh.onAfterRender, original); mesh.geometry.dispose(); mesh.material.dispose();
});
