// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { Material, MeshLambertMaterial, MeshPhongMaterial, MeshStandardMaterial, REVISION, ShaderChunk } from 'three';
import { cloneNativeMaterial, matchesNativeAlphaHooks } from './native-alpha-material';

type Compile = Material['onBeforeCompile'];
type CacheKey = Material['customProgramCacheKey'];
interface HookPair { compile: Compile; key: CacheKey }
interface OwnedGuard extends HookPair { parent: HookPair }
const owned = new WeakMap<Material, OwnedGuard>();
const originalChunk = ShaderChunk.lights_fragment_begin;
const include = '#include <lights_fragment_begin>';
const cacheVersion = 'native-exact-zero-point-spot-v1';

function safeParent(material: Material, parent: HookPair): boolean {
  return parent.compile === Material.prototype.onBeforeCompile && parent.key === Material.prototype.customProgramCacheKey
    || matchesNativeAlphaHooks(material, parent.compile, parent.key);
}

/** A compatibility fingerprint, not an authorization mechanism. The package is
 * pinned to Three 0.186.1; refuse source changes until the new shader is audited.
 * No global ShaderChunk is written and no model/userData can authorize a hook. */
function checkChunk(source: string): void {
  let hash = 2166136261;
  for (let index = 0; index < source.length; index++) hash = Math.imul(hash ^ source.charCodeAt(index), 16777619) >>> 0;
  if (REVISION !== '186' || source.length !== 7454 || hash !== 400040809 || source !== originalChunk) {
    throw Error('Unaudited Three point/spot lighting shader');
  }
}

/** Preserve the complete contribution byte-for-byte inside an exact uniform
 * RGB test. Shadows and projected spot maps are inside the branch. Sun,
 * directional, area, ambient and indirect lighting remain untouched. */
export function guardNativeZeroLightChunk(source = originalChunk): string {
  checkChunk(source);
  let result = source;
  for (const kind of ['point', 'spot'] as const) {
    const name = `${kind}Light`;
    const pattern = new RegExp(`(\\t\\t${name} = ${kind}Lights\\[ i \\];\\n)([\\s\\S]*?)(\\n\\t}\\n\\t#pragma unroll_loop_end)`, 'g');
    let count = 0;
    result = result.replace(pattern, (_match, assignment: string, contribution: string, end: string) => {
      count++;
      return `${assignment}\n\t\tif ( any( notEqual( ${name}.color, vec3( 0.0 ) ) ) ) {${contribution}\n\t\t}${end}`;
    });
    if (count !== 1) throw Error(`Unaudited Three ${kind} lighting loop`);
  }
  return result;
}

let guardedChunk: string | undefined;

/** Exact per-material ownership includes the captured parent's private proof.
 * A copied callback, forged userData or a subsequently replaced alpha hook
 * cannot authorize this shader for static batching or further composition. */
export function matchesNativeZeroLightHooks(material: Material, compile: Compile, key: CacheKey): boolean {
  const guard = owned.get(material);
  return Boolean(guard && guard.compile === compile && guard.key === key && safeParent(material, guard.parent));
}

export function hasNativeZeroLightShader(material: Material): boolean {
  return matchesNativeZeroLightHooks(material, material.onBeforeCompile, material.customProgramCacheKey);
}

/** Prepared optimization: callers must deliberately install it on their own
 * native lit materials. It changes no light count, visibility or render state.
 * No epsilon: tiny, negative, single-channel and HDR nonzero RGB still execute.
 * ShadowMaterial/Basic/custom shaders are deliberately not in this contract. */
export function installNativeZeroLightShader(material: Material): void {
  if (hasNativeZeroLightShader(material)) return;
  if (!(material instanceof MeshStandardMaterial || material instanceof MeshPhongMaterial || material instanceof MeshLambertMaterial)) {
    throw Error('Zero-light guard requires an owned native built-in lit material');
  }
  const parent = { compile: material.onBeforeCompile, key: material.customProgramCacheKey };
  if (!safeParent(material, parent)) throw Error('Zero-light guard cannot replace an unsupported custom material shader');
  const chunk = guardedChunk ??= guardNativeZeroLightChunk();
  const compile: Compile = function (this: Material, shader, renderer) {
    if (this !== material || !hasNativeZeroLightShader(material)) throw Error('Zero-light shader ownership changed');
    parent.compile.call(material, shader, renderer);
    if (shader.fragmentShader.split(include).length !== 2) throw Error('Unaudited native lit material shader');
    shader.fragmentShader = shader.fragmentShader.replace(include, chunk);
  };
  const key: CacheKey = function (this: Material) {
    if (this !== material || !hasNativeZeroLightShader(material)) throw Error('Zero-light shader ownership changed');
    // Three's default key reads this.onBeforeCompile. Preserve the captured
    // default's identity rather than deriving it from the installed wrapper.
    const parentKey = parent.key === Material.prototype.customProgramCacheKey
      ? parent.compile.toString() : parent.key.call(material);
    return `${parentKey}|${cacheVersion}`;
  };
  owned.set(material, { compile, key, parent });
  material.onBeforeCompile = compile; material.customProgramCacheKey = key;
  material.needsUpdate = true;
}

/** Detach before native alpha/cull reconfiguration. Only our exact currently
 * installed pair is restored; a foreign mutation is never overwritten. */
export function restoreNativeZeroLightShader(material: Material): boolean {
  const guard = owned.get(material);
  if (!guard || material.onBeforeCompile !== guard.compile || material.customProgramCacheKey !== guard.key) return false;
  material.onBeforeCompile = guard.parent.compile; material.customProgramCacheKey = guard.parent.key;
  owned.delete(material); material.needsUpdate = true;
  return true;
}

/** Three.clone omits shader callbacks. Expose the exact trusted parent only
 * during the synchronous native clone call, without recompiling the source.
 * Native alpha's own clone helper installs its private proof on the new object.
 * The guard is reinstalled on the clone, with its own private registry entry. */
export function cloneNativeMaterialWithZeroLightGuard<T extends Material>(material: T): T {
  const guard = owned.get(material);
  if (!guard) {
    if (!safeParent(material, { compile: material.onBeforeCompile, key: material.customProgramCacheKey })) throw Error('Cannot clone an unsupported custom material shader');
    return cloneNativeMaterial(material);
  }
  if (!hasNativeZeroLightShader(material)) throw Error('Zero-light shader ownership changed');
  let clone: T;
  material.onBeforeCompile = guard.parent.compile; material.customProgramCacheKey = guard.parent.key;
  try { clone = cloneNativeMaterial(material); }
  finally {
    if (material.onBeforeCompile === guard.parent.compile && material.customProgramCacheKey === guard.parent.key) {
      material.onBeforeCompile = guard.compile; material.customProgramCacheKey = guard.key;
    } else {
      // A subclass/custom clone must not gain permission to have its concurrent
      // callback replacement overwritten or attributed to this private wrapper.
      owned.delete(material);
    }
  }
  if (!hasNativeZeroLightShader(material)) { clone.dispose(); throw Error('Zero-light shader ownership changed during clone'); }
  try { installNativeZeroLightShader(clone); return clone; }
  catch (error) { clone.dispose(); throw error; }
}
