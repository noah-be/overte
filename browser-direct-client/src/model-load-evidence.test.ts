// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ModelLoadEvidence } from './model-load-evidence';

test('failed model evidence follows its actual owner and does not leak a retired root into its replacement', () => {
  const evidence = new ModelLoadEvidence(), retired = {}, current = {};
  evidence.failed(retired, new Error('No geometry was returned for this model.'));
  const state = { id: 'actual-entity', name: 'Actual model', modelURL: 'atp:/hub/actual.fbx', loaded: false, failed: true, shadersReady: false };
  assert.equal(evidence.snapshot([{ ...state, owner: retired }]).rows[0].error, 'No geometry was returned for this model.');
  const fresh = evidence.snapshot([{ ...state, owner: current, failed: false }]);
  assert.equal(fresh.rows[0].error, undefined); assert.equal(fresh.pending, 1); assert.equal(fresh.failed, 0);
  assert.equal(evidence.snapshot([{ ...state, owner: current, failed: false, loaded: true, shadersReady: true }]).loaded, 1);
  // A model can have returned its geometry before a later shader step fails.
  const shaderFailure = evidence.snapshot([{ ...state, owner: current, loaded: true, failed: true }]);
  assert.equal(shaderFailure.pending, 0); assert.equal(shaderFailure.loaded, 1); assert.equal(shaderFailure.failed, 1);
});

test('model evidence bounds rows and text while preserving totals and removing URL credentials and private query values', () => {
  const evidence = new ModelLoadEvidence(), root = {};
  evidence.failed(root, new Error('Cannot fetch https://visitor:PRIVATE@asset.example/a.fbx?q=PRIVATE#PRIVATE'));
  const values = Array.from({ length: 160 }, (_, index) => ({ id: String(index), name: 'x'.repeat(1024), owner: root,
    modelURL: 'https://visitor:PRIVATE@asset.example/a.fbx?q=PRIVATE#PRIVATE', loaded: false, failed: true, shadersReady: false }));
  const result = evidence.snapshot(values, 10000);
  assert.equal(result.total, 160); assert.equal(result.failed, 160); assert.equal(result.retained, 128); assert.equal(result.omitted, 32);
  assert.equal(result.rows[0].name.length, 256); assert.ok(!JSON.stringify(result).includes('PRIVATE'));
  assert.equal(result.rows[0].modelURL, 'https://asset.example/a.fbx');
  evidence.failed(root, new Error('token PRIVATE')); assert.equal(evidence.snapshot(values, 1).rows[0].error, '[Sensitive failure reason omitted]');
});

test('loaded geometry reports its unavailable declared texture separately and clears on owner replacement', () => {
  const evidence = new ModelLoadEvidence(), root = {}, next = {};
  const sourceURL = 'https://asset.example/original/bridges_d.psd';
  evidence.incomplete(root, Array.from({ length: 50 }, () => ({ sourceURL, property: 'albedoMap', error: 'Image unavailable' })));
  const state = { id: 'actual-dock', modelURL: 'atp:/actual-dock.fst', loaded: true, failed: false, shadersReady: true };
  const result = evidence.snapshot([{ ...state, owner: root }]);
  assert.equal(result.loaded, 1); assert.equal(result.failed, 0); assert.equal(result.incompleteModels, 1); assert.equal(result.unavailableTextures, 1);
  assert.deepEqual(result.rows[0].unavailableTextures, [{ sourceURL, property: 'albedoMap', error: 'Image unavailable' }]);
  const replacement = evidence.snapshot([{ ...state, owner: next }]);
  assert.equal(replacement.unavailableTextures, 0); assert.equal(replacement.rows[0].incompleteTextures, false);
});
