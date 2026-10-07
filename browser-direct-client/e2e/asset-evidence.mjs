// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

/** Bind acceptance to the actual source and served native scene, including URLs
 * outside modelURL. This audit does not assert those optional effects render. */
export async function readSceneAssetAudit(labRoot) {
    const manifest = JSON.parse(await readFile(resolve(labRoot, 'scene/atp-scene-provenance.json'), 'utf8'));
    const sourceBytes = await readFile(resolve(labRoot, 'scene', manifest.historicalSourceScene));
    const mixedPath = resolve(labRoot, 'scene/mixed-scene-provenance.json');
    const mixed = existsSync(mixedPath) ? JSON.parse(await readFile(mixedPath, 'utf8')) : undefined;
    const baseBytes = await readFile(resolve(labRoot, 'scene', manifest.runtimeScene));
    assert.equal(createHash('sha256').update(baseBytes).digest('hex'), manifest.sceneSHA256);
    if (mixed) assert.equal(mixed.baseSceneSHA256, manifest.sceneSHA256);
    const servedBytes = mixed ? await readFile(resolve(labRoot, 'scene', mixed.runtimeScene)) : baseBytes;
    const sourceSHA256 = createHash('sha256').update(sourceBytes).digest('hex');
    const servedSHA256 = createHash('sha256').update(servedBytes).digest('hex');
    assert.equal(sourceSHA256, manifest.historicalSourceSHA256);
    assert.equal(servedSHA256, mixed?.sceneSHA256 ?? manifest.sceneSHA256);
    const source = JSON.parse(sourceBytes), served = JSON.parse(servedBytes);
    const collect = (value, path, output) => {
        if (typeof value === 'string' && /^(?:https?:|atp:)/.test(value)) output.push({ property: path, url: value });
        else if (Array.isArray(value)) value.forEach((item, index) => collect(item, `${path}[${index}]`, output));
        else if (value && typeof value === 'object') for (const [key, item] of Object.entries(value)) collect(item, path ? `${path}.${key}` : key, output);
    };
    const sourceEffects = source.Entities.filter(entity => entity.type === 'Zone' || entity.type === 'Material').map(entity => {
        const urls = []; collect(entity, '', urls); return { id: entity.id, name: entity.name, type: entity.type, urls };
    });
    const servedEffects = served.Entities.filter(entity => entity.type === 'Zone' || entity.type === 'Material').map(entity => {
        const urls = []; collect(entity, '', urls); return { id: entity.id, name: entity.name, type: entity.type, urls };
    });
    const httpsModels = served.Entities.filter(entity => entity.type === 'Model' && entity.modelURL?.startsWith('https://127.0.0.1:46119/'));
    const atpModels = served.Entities.filter(entity => entity.type === 'Model' && entity.modelURL?.startsWith('atp:'));
    return { sourceSHA256, servedSHA256, entityCount: served.Entities.length, sourceEffects, servedEffects,
        httpsModels: httpsModels.map(entity => ({ id: entity.id, name: entity.name, modelURL: entity.modelURL,
            position: entity.position, rotation: entity.rotation, dimensions: entity.dimensions })),
        atpModelCount: atpModels.length };
}

/** Actual browser CORS checks for raw source effect URLs. Reading one chunk and
 * canceling avoids downloading entire optional EXR resources for a URL audit. */
export async function probeSourceEffectCORS(page, audit) {
    const urls = [...new Set(audit.sourceEffects.flatMap(entity => entity.urls.map(item => item.url)))].filter(url => url.startsWith('https:'));
    return page.evaluate(async urls => {
        const output = [];
        for (const url of urls) {
            const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 10000);
            try {
                const response = await fetch(url, { mode: 'cors', cache: 'no-store', signal: controller.signal });
                const reader = response.body?.getReader(); const first = await reader?.read(); await reader?.cancel();
                output.push({ url, corsAccessible: response.ok && response.type === 'cors', status: response.status,
                    responseType: response.type, contentType: response.headers.get('Content-Type'), inspectedBytes: first?.value?.byteLength || 0 });
            } catch (error) { output.push({ url, corsAccessible: false, error: String(error.message).slice(0, 500) }); }
            finally { clearTimeout(timer); }
        }
        return output;
    }, urls);
}
