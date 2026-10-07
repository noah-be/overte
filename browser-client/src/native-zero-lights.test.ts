// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { Material, MeshBasicMaterial, MeshLambertMaterial, MeshNormalMaterial, MeshPhongMaterial, MeshPhysicalMaterial, MeshStandardMaterial, RawShaderMaterial, ShaderChunk, ShaderLib, ShaderMaterial, ShadowMaterial, Texture, type WebGLRenderer } from 'three';
import { applyNativeMaterialAlpha, getNativeAlphaOptions, hasNativeAlphaShader } from './native-alpha-material';
import { applyNativeRenderState } from './native-render-state';
import { cloneNativeMaterialWithZeroLightGuard, guardNativeZeroLightChunk, hasNativeZeroLightShader, installNativeZeroLightShader, matchesNativeZeroLightHooks, restoreNativeZeroLightShader } from './native-zero-lights';

function shader() { return { ...ShaderLib.standard, uniforms: { ...ShaderLib.standard.uniforms } } as Parameters<Material['onBeforeCompile']>[0]; }
const renderer = {} as WebGLRenderer;

test('pinned local shader expansion leaves global source and all original contributions byte-identical', () => {
  const before = ShaderChunk.lights_fragment_begin, expanded = guardNativeZeroLightChunk();
  assert.equal(createHash('sha256').update(before).digest('hex'), 'd73780c6a964327484c27b2fe283c1a511a6007805afcd0491090b5b3769bd68');
  assert.equal(ShaderChunk.lights_fragment_begin, before);
  let reconstructed = expanded;
  for (const kind of ['point', 'spot']) {
    const prefix = `\n\t\tif ( any( notEqual( ${kind}Light.color, vec3( 0.0 ) ) ) ) {`;
    assert.equal(reconstructed.split(prefix).length, 2);
    const begin = reconstructed.indexOf(prefix), end = reconstructed.indexOf('\n\t\t}\n\t}\n\t#pragma unroll_loop_end', begin);
    assert.ok(end > begin);
    const body = reconstructed.slice(begin + prefix.length, end);
    assert.ok(body.includes(`get${kind === 'point' ? 'Point' : 'Spot'}LightInfo(`));
    assert.ok(body.includes(kind === 'point' ? 'getPointShadow(' : 'getShadow('));
    assert.ok(body.includes('RE_Direct( directLight,'));
    if (kind === 'spot') assert.ok(body.includes('texture2D( spotLightMap['));
    reconstructed = reconstructed.slice(0, begin) + body + reconstructed.slice(end + '\n\t\t}'.length);
  }
  assert.equal(reconstructed, before);
  assert.throws(() => guardNativeZeroLightChunk(before.replace('getPointLightInfo', 'foreignLightInfo')), /Unaudited/);
});

test('nested uniform branches preserve the exact pinned Three unroller and all sixteen static light indices', () => {
  const program = readFileSync(new URL('../node_modules/three/src/renderers/webgl/WebGLProgram.js', import.meta.url), 'utf8');
  const literal = program.match(/const unrollLoopPattern = (\/[^\n]+\/g);/)?.[1]; assert.ok(literal);
  const pattern = new RegExp(literal.slice(1, -2), 'g');
  const source = guardNativeZeroLightChunk().replaceAll('NUM_POINT_LIGHTS', '8').replaceAll('NUM_SPOT_LIGHTS', '8');
  const unrolled = source.replace(pattern, (_match, start: string, end: string, snippet: string) => Array.from({ length: Number(end) - Number(start) }, (_, offset) => snippet.replace(/\[\s*i\s*\]/g, `[ ${Number(start) + offset} ]`).replaceAll('UNROLLED_LOOP_INDEX', `${Number(start) + offset}`)).join(''));
  assert.equal(unrolled.match(/if \( any\( notEqual\( pointLight.color/g)?.length, 8);
  assert.equal(unrolled.match(/if \( any\( notEqual\( spotLight.color/g)?.length, 8);
  for (let index = 0; index < 8; index++) {
    assert.ok(unrolled.includes(`pointLight = pointLights[ ${index} ];`));
    assert.ok(unrolled.includes(`spotLight = spotLights[ ${index} ];`));
    assert.ok(unrolled.includes(`pointShadowMap[ ${index} ]`));
    assert.ok(unrolled.includes(`vSpotLightCoord[ ${index} ]`));
  }
  assert.ok(!unrolled.includes('UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS'));
});

test('exact RGB predicate has no threshold and keeps negative, tiny, single-channel and HDR colors eligible', () => {
  const source = guardNativeZeroLightChunk();
  assert.ok(!source.includes('nativeZeroLightThreshold'));
  assert.ok(source.includes('notEqual( pointLight.color, vec3( 0.0 ) )'));
  assert.ok(source.includes('notEqual( spotLight.color, vec3( 0.0 ) )'));
  // IEEE exact-zero oracle for the tested GLSL predicate, including negative zero.
  for (const rgb of [[0,0,0], [-0,0,-0]]) assert.equal(rgb.some(value => value !== 0), false);
  for (const rgb of [[1e-8,0,0], [0,-.25,0], [0,0,2048], [1,2,3]]) assert.equal(rgb.some(value => value !== 0), true);
});

test('known native lit materials install once without changing render state, geometry options or default hooks globally', () => {
  const defaultCompile = Material.prototype.onBeforeCompile, defaultKey = Material.prototype.customProgramCacheKey;
  for (const material of [new MeshStandardMaterial(), new MeshPhysicalMaterial(), new MeshPhongMaterial(), new MeshLambertMaterial()]) {
    const before = { opacity: material.opacity, side: material.side, depthWrite: material.depthWrite, transparent: material.transparent, forceSinglePass: material.forceSinglePass };
    installNativeZeroLightShader(material); const version = material.version, key = material.customProgramCacheKey();
    for (let index = 0; index < 20; index++) installNativeZeroLightShader(material);
    assert.equal(material.version, version); assert.equal(material.customProgramCacheKey(), key); assert.equal(hasNativeZeroLightShader(material), true);
    assert.deepEqual({ opacity: material.opacity, side: material.side, depthWrite: material.depthWrite, transparent: material.transparent, forceSinglePass: material.forceSinglePass }, before);
    const parameters = shader(); material.onBeforeCompile(parameters, renderer);
    assert.ok(parameters.fragmentShader.includes('notEqual( pointLight.color')); assert.ok(!parameters.fragmentShader.includes('#include <lights_fragment_begin>'));
    assert.equal(restoreNativeZeroLightShader(material), true); assert.equal(material.onBeforeCompile, defaultCompile); assert.equal(material.customProgramCacheKey, defaultKey);
    assert.equal(restoreNativeZeroLightShader(material), false); material.dispose();
  }
  assert.equal(Material.prototype.onBeforeCompile, defaultCompile); assert.equal(Material.prototype.customProgramCacheKey, defaultKey);
});

test('foreign callbacks, copied ownership, custom and unlit materials are refused without version/state mutation', () => {
  for (const material of [new ShaderMaterial(), new RawShaderMaterial(), new MeshBasicMaterial(), new MeshNormalMaterial(), new ShadowMaterial()]) {
    const version = material.version; assert.throws(() => installNativeZeroLightShader(material), /built-in lit/); assert.equal(material.version, version); material.dispose();
  }
  const guarded = new MeshStandardMaterial(); installNativeZeroLightShader(guarded);
  for (const change of ['compile', 'key', 'copied'] as const) {
    const material = new MeshStandardMaterial(); material.userData.nativeZeroLights = true;
    if (change === 'compile') material.onBeforeCompile = () => {};
    else if (change === 'key') material.customProgramCacheKey = () => 'claimed-trusted';
    else { material.onBeforeCompile = guarded.onBeforeCompile; material.customProgramCacheKey = guarded.customProgramCacheKey; }
    const version = material.version, compile = material.onBeforeCompile, key = material.customProgramCacheKey;
    assert.equal(hasNativeZeroLightShader(material), false); assert.equal(matchesNativeZeroLightHooks(material, compile, key), false);
    assert.throws(() => installNativeZeroLightShader(material), /unsupported custom/);
    assert.throws(() => cloneNativeMaterialWithZeroLightGuard(material), /unsupported custom/);
    assert.equal(material.version, version); assert.equal(material.onBeforeCompile, compile); assert.equal(material.customProgramCacheKey, key); material.dispose();
  }
  const copied = new MeshStandardMaterial(); copied.onBeforeCompile = guarded.onBeforeCompile;
  assert.throws(() => copied.onBeforeCompile(shader(), renderer), /ownership changed/); guarded.dispose(); copied.dispose();
});

test('owned native alpha hook composes and clones with its private proof, cutoff uniform and shared texture intact', async () => {
  const map = new Texture(), material = new MeshStandardMaterial({ map });
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK', cutoff: .375 });
  const parentCompile = material.onBeforeCompile, parentKey = material.customProgramCacheKey;
  installNativeZeroLightShader(material); const version = material.version;
  const parameters = shader(); material.onBeforeCompile(parameters, renderer);
  assert.equal(parameters.uniforms.nativeOpacityCutoff.value, .375);
  assert.ok(parameters.fragmentShader.includes('opacity * step(nativeOpacityCutoff, sampledDiffuseColor.a)'));
  assert.ok(parameters.fragmentShader.includes('notEqual( spotLight.color'));
  const clone = cloneNativeMaterialWithZeroLightGuard(material);
  assert.equal(material.version, version); assert.equal(hasNativeZeroLightShader(material), true); assert.equal(hasNativeZeroLightShader(clone), true);
  assert.equal(clone.map, map); assert.deepEqual(getNativeAlphaOptions(clone), getNativeAlphaOptions(material));
  assert.equal(clone.customProgramCacheKey(), material.customProgramCacheKey());
  assert.equal(restoreNativeZeroLightShader(clone), true); assert.equal(hasNativeAlphaShader(clone), true); assert.equal(clone.onBeforeCompile, parentCompile); assert.equal(clone.customProgramCacheKey, parentKey);
  clone.dispose(); material.dispose(); map.dispose();
});

test('alpha and render-state reconfiguration requires explicit detach and preserves new private parent authority', async () => {
  const material = new MeshStandardMaterial({ map: new Texture() });
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_MASK' });
  installNativeZeroLightShader(material); const oldCompile = material.onBeforeCompile, oldKey = material.customProgramCacheKey;
  await assert.rejects(applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' }), /unsupported custom/);
  assert.throws(() => applyNativeRenderState(material), /unsupported custom/);
  assert.equal(restoreNativeZeroLightShader(material), true);
  await applyNativeMaterialAlpha(material, { useAlpha: true, mode: 'OPACITY_MAP_BLEND' }); applyNativeRenderState(material);
  assert.equal(material.transparent, true); assert.equal(material.depthWrite, false);
  // Reusing old captured pairs after alpha ownership changes is not a proof.
  material.onBeforeCompile = oldCompile; material.customProgramCacheKey = oldKey;
  assert.equal(hasNativeZeroLightShader(material), false); assert.throws(() => material.customProgramCacheKey(), /ownership changed/);
  material.onBeforeCompile = Material.prototype.onBeforeCompile; material.customProgramCacheKey = Material.prototype.customProgramCacheKey;
  installNativeZeroLightShader(material); assert.equal(hasNativeZeroLightShader(material), true); assert.equal(material.transparent, true); assert.equal(material.depthWrite, false);
  material.map?.dispose(); material.dispose();
});

test('foreign mutation is never overwritten by detach, and unsafe compile source fails explicitly', () => {
  const material = new MeshStandardMaterial(); installNativeZeroLightShader(material);
  const foreign = () => {}; material.onBeforeCompile = foreign; const version = material.version;
  assert.equal(restoreNativeZeroLightShader(material), false); assert.equal(material.onBeforeCompile, foreign); assert.equal(material.version, version);
  const safe = new MeshStandardMaterial(); installNativeZeroLightShader(safe);
  for (const fragmentShader of ['void main() {}', '#include <lights_fragment_begin>\n#include <lights_fragment_begin>']) {
    assert.throws(() => safe.onBeforeCompile({ ...shader(), fragmentShader }, renderer), /Unaudited/);
  }
  material.dispose(); safe.dispose();
});

test('failed synchronous clone restores exact original ownership, while clone-time foreign mutation is not overwritten', () => {
  const material = new MeshStandardMaterial(); installNativeZeroLightShader(material);
  const compile = material.onBeforeCompile, key = material.customProgramCacheKey, version = material.version;
  material.clone = () => { throw Error('Clone failed'); };
  assert.throws(() => cloneNativeMaterialWithZeroLightGuard(material), /Clone failed/);
  assert.equal(material.onBeforeCompile, compile); assert.equal(material.customProgramCacheKey, key); assert.equal(material.version, version); assert.equal(hasNativeZeroLightShader(material), true);
  const foreign = () => {}; let released = false;
  material.clone = () => { material.onBeforeCompile = foreign; const clone = new MeshStandardMaterial(); clone.addEventListener('dispose', () => { released = true; }); return clone; };
  assert.throws(() => cloneNativeMaterialWithZeroLightGuard(material), /ownership changed during clone/);
  assert.equal(material.onBeforeCompile, foreign); assert.equal(hasNativeZeroLightShader(material), false); assert.equal(released, true); material.dispose();
});
