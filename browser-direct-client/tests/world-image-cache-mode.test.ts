// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Real World texture-loading methods; fake DOM image completion, no GPU claim.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { NoColorSpace, SRGBColorSpace, type Texture } from 'three';
import { BrowserWorld } from '../src/world';
import { WorldImageCache } from '../src/world-image-cache';

class ImageFixture extends EventTarget {
    crossOrigin = ''; naturalWidth = 4; naturalHeight = 4; complete = false; url = '';
    set src(value: string) { this.url = value; queueMicrotask(() => { this.complete = true; this.dispatchEvent(new Event('load')); }); }
    get src() { return this.url; }
    async decode() {} removeAttribute() { this.url = ''; }
}
test('cache benchmark arms request the identical original source and preserve independent texture sampler/color settings', async t => {
    const before = Object.getOwnPropertyDescriptor(globalThis, 'document'), images: ImageFixture[] = [];
    const image = () => { const created = new ImageFixture(); images.push(created); return created as unknown as HTMLImageElement; };
    Object.defineProperty(globalThis, 'document', { configurable: true, value: { createElementNS: image, createElement: image } });
    t.after(() => { if (before) Object.defineProperty(globalThis, 'document', before); else Reflect.deleteProperty(globalThis, 'document'); });
    const source = 'https://actual-domain.invalid/textures/original.png';
    const arms: { enabled: boolean; imageCount: number; textures: Texture[] }[] = [];
    for (const enabled of [true, false]) {
        const abort = new AbortController(), cache = new WorldImageCache({ signal: abort.signal, createImage: image });
        const context = Object.create(BrowserWorld.prototype) as BrowserWorld;
        Object.assign(context, { imageCaching: enabled, imageCache: cache, abort,
            disposed: false, loadManagers: new Set(), options: { resolveAsset: (url: string) => url } });
        const load = (Reflect.get(context, 'texture') as (url: string, color?: boolean) => Promise<Texture>).bind(context);
        const count = images.length, textures = await Promise.all([load(source, true), load(source, false)]);
        assert.equal(textures[0].colorSpace, SRGBColorSpace); assert.equal(textures[1].colorSpace, NoColorSpace);
        assert.notEqual(textures[0], textures[1]); textures[0].repeat.set(2, 3);
        assert.deepEqual(textures[1].repeat.toArray(), [1, 1]);
        assert.ok(images.slice(count).every(value => value.src === source));
        arms.push({ enabled, imageCount: images.length - count, textures }); abort.abort();
    }
    assert.equal(arms[0].imageCount, 1); assert.equal(arms[1].imageCount, 2);
    for (let index = 0; index < 2; index++) {
        const cached = arms[0].textures[index], baseline = arms[1].textures[index];
        assert.equal(cached.colorSpace, baseline.colorSpace); assert.equal(cached.flipY, baseline.flipY);
        assert.equal(cached.minFilter, baseline.minFilter); assert.equal(cached.magFilter, baseline.magFilter);
        assert.equal(cached.wrapS, baseline.wrapS); assert.equal(cached.wrapT, baseline.wrapT);
        assert.equal(cached.generateMipmaps, baseline.generateMipmaps);
        cached.dispose(); baseline.dispose();
    }
});
