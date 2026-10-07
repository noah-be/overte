// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0

export interface ModelLoadState {
  id: string;
  name?: string;
  modelURL?: string;
  owner?: object;
  loaded: boolean;
  failed: boolean;
  shadersReady: boolean;
}

function sourceLabel(value: string): string {
  const bounded = value.slice(0, 4096);
  try {
    const url = new URL(bounded);
    if (url.protocol === 'data:' || url.protocol === 'blob:') return '[embedded source omitted]';
    url.username = ''; url.password = ''; url.search = ''; url.hash = '';
    return url.href;
  } catch { return bounded; }
}

/** Failure messages belong to current World roots. A replacement never inherits
 * its predecessor's failure; this collection does not keep retired roots alive. */
export class ModelLoadEvidence {
  private readonly failures = new WeakMap<object, string>();
  private readonly unavailable = new WeakMap<object, readonly { sourceURL: string; property: string; error: string }[]>();

  incomplete(owner: object, values: readonly { sourceURL: string; property: string; error: string }[]): void {
    const sources = new Map<string, { sourceURL: string; property: string; error: string }>();
    for (const value of values) {
      const sourceURL = sourceLabel(value.sourceURL);
      if (sources.size >= 32 && !sources.has(sourceURL)) continue;
      sources.set(sourceURL, { sourceURL, property: value.property.slice(0, 64),
        error: /\b(password|authorization|secret|sdp|candidate|token)\b/i.test(value.error)
          ? '[Sensitive failure reason omitted]' : value.error.slice(0, 2048).replace(/\b(?:https?|wss?|atp):[^\s"'<>]+/gi, sourceLabel) });
    }
    this.unavailable.set(owner, [...sources.values()]);
  }

  failed(owner: object, error: unknown): void {
    const message = (error instanceof Error ? error.message : String(error)).slice(0, 2048);
    this.failures.set(owner, /\b(password|authorization|secret|sdp|candidate|token)\b/i.test(message)
      ? '[Sensitive failure reason omitted]'
      : message.replace(/\b(?:https?|wss?|atp):[^\s"'<>]+/gi, sourceLabel));
  }

  snapshot(values: Iterable<ModelLoadState>, requestedLimit = 128) {
    const limit = Number.isFinite(requestedLimit) ? Math.max(0, Math.min(128, Math.floor(requestedLimit))) : 128;
    const rows: Array<{ id: string; name: string; modelURL: string; loaded: boolean; failed: boolean; shadersReady: boolean;
      error?: string; incompleteTextures: boolean; unavailableTextures: readonly { sourceURL: string; property: string; error: string }[] }> = [];
    let total = 0, loaded = 0, failed = 0, pending = 0, incompleteModels = 0;
    const missing = new Set<string>();
    for (const value of values) {
      total++; if (value.loaded) loaded++; if (value.failed) failed++;
      if (!value.loaded && !value.failed) pending++;
      const unavailableTextures = value.owner ? this.unavailable.get(value.owner) ?? [] : [];
      if (unavailableTextures.length) incompleteModels++;
      for (const texture of unavailableTextures) missing.add(texture.sourceURL);
      if (rows.length >= limit) continue;
      rows.push({ id: value.id.slice(0, 128), name: (value.name || 'Model').slice(0, 256),
        modelURL: sourceLabel(value.modelURL || ''), loaded: value.loaded, failed: value.failed, shadersReady: value.shadersReady,
        incompleteTextures: unavailableTextures.length > 0, unavailableTextures: unavailableTextures.map(value => ({ ...value })),
        ...(value.owner && this.failures.has(value.owner) ? { error: this.failures.get(value.owner) } : {}) });
    }
    return { total, loaded, failed, pending, incompleteModels, unavailableTextures: missing.size,
      retained: rows.length, omitted: total - rows.length, limit, rows,
      scope: 'Current model roots and bounded failure reasons only; reading does not request assets, compile shaders or traverse geometry.' };
  }
}
