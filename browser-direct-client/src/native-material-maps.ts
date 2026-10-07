// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { MeshBasicMaterial, MeshStandardMaterial, type Texture } from 'three';
import type { MaterialData } from './world-data';

export interface NativeMaterialMapFailure { sourceURL: string; property: string; error: string }
const fields = [ ['albedoMap', 'map', true, 'albedo'], ['normalMap', 'normalMap', false, 'linear'],
  ['roughnessMap', 'roughnessMap', false, 'linear'], ['metallicMap', 'metalnessMap', false, 'linear'],
  ['emissiveMap', 'emissiveMap', true, 'emissive'] ] as const;
const isAbort = (error: unknown) => Boolean(error && typeof error === 'object' && 'name' in error && error.name === 'AbortError');

/** One FST's ordered templates may share a failed original URL. Remember only
 * those exact failures within that load, never across sessions or root reloads. */
export class NativeMaterialMapFailures {
  private readonly entries = new Map<string, Error>();
  async load(key: string, operation: () => Promise<Texture>, assertCurrent: () => void): Promise<Texture> {
    assertCurrent();
    const previous = this.entries.get(key); if (previous) throw previous;
    try { return await operation(); }
    catch (error) {
      assertCurrent();
      if (isAbort(error)) throw error;
      const failure = new Error((error instanceof Error ? error.message : 'A declared texture image could not be loaded.').slice(0, 2048));
      if (this.entries.size < 256) this.entries.set(key, failure);
      throw failure;
    }
  }
}

/** Native NetworkMaterial::isMissingTexture treats a failed image as finished
 * so its real geometry fades in. Keep the declared material values and every
 * successful map; no replacement image, white texture or quality change. */
export async function loadNativeMaterialMaps(material: MeshBasicMaterial | MeshStandardMaterial, data: MaterialData,
  resolve: (url: string) => string,
  load: (url: string, color: boolean, role: 'albedo' | 'emissive' | 'linear') => Promise<Texture>,
  assertCurrent: () => void, memo?: NativeMaterialMapFailures): Promise<NativeMaterialMapFailure[]> {
  assertCurrent();
  const requests = fields.filter(([key, field]) => data[key] && (field === 'map' || material instanceof MeshStandardMaterial))
    .map(([property, field, color, role]) => ({ property, field, color, role, sourceURL: resolve(data[property]!) }));
  const results = await Promise.allSettled(requests.map(async request => {
    const operation = () => load(request.sourceURL, request.color, request.role);
    const texture = await (memo ? memo.load(JSON.stringify([request.sourceURL, request.color, request.role]), operation, assertCurrent) : operation());
    if (request.field === 'map') material.map = texture;
    else if (material instanceof MeshStandardMaterial) material[request.field] = texture;
  }));
  assertCurrent();
  const failures: NativeMaterialMapFailure[] = [];
  for (let index = 0; index < results.length; index++) {
    const result = results[index]; if (result.status === 'fulfilled') continue;
    if (isAbort(result.reason)) throw result.reason;
    failures.push({ property: requests[index].property, sourceURL: requests[index].sourceURL,
      error: (result.reason instanceof Error ? result.reason.message : 'A declared texture image could not be loaded.').slice(0, 2048) });
  }
  return failures;
}
