// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { LoadingManager, Texture, TextureLoader } from 'three';

/** Preserve synchronous Texture ownership while native ATP mapping and texture
 * metadata resolve asynchronously. Samplers/color space remain the caller's. */
export class NativeTextureLoader extends TextureLoader {
    constructor(manager: LoadingManager, private readonly images: TextureLoader,
        private readonly resolveImage: (url: string) => Promise<string>) { super(manager); }

    override load(url: string, onLoad?: (texture: Texture<HTMLImageElement>) => void,
        onProgress?: (event: ProgressEvent) => void, onError?: (error: unknown) => void): Texture<HTMLImageElement> {
        const requested = this.manager.resolveURL(this.path ? this.path + url : url);
        const texture = new Texture<HTMLImageElement>();
        this.manager.itemStart(requested);
        const finish = () => this.manager.itemEnd(requested);
        const failed = (error: unknown) => {
            texture.dispose();
            try { onError?.(error); } finally { this.manager.itemError(requested); }
        };
        void this.resolveImage(requested).then(resolved => new Promise<void>((resolve, reject) => {
            this.images.load(resolved, loaded => {
                texture.source = loaded.source;
                texture.needsUpdate = true;
                loaded.dispose();
                try { onLoad?.(texture); resolve(); } catch (error) { reject(error); }
            }, onProgress, reject);
        })).catch(failed).finally(finish).catch(() => {});
        return texture;
    }
}
