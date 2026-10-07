// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Actual equirectangular skybox sources; native rotation/color behavior reviewed
// against graphics/Skybox.cpp and graphics/Light.slh (Apache-2.0).
import * as THREE from 'three';
import type { ZoneSkyboxSelection } from './world-zones';
import { entityTransform, type Entity } from './world-data';

interface Options {
    signal: AbortSignal;
    load(source: string, signal: AbortSignal): Promise<THREE.Texture>;
    prepare(root: THREE.Object3D, current: () => boolean): Promise<void>;
    assertCurrent(): void;
    warn(message: string): void;
}

/** One current skybox and one bounded pending load per visitor World. Revocation
 * disposes only its own Texture; image-sharing ownership remains with its loader. */
export class WorldZoneSkybox {
    private signature = '';
    private request?: AbortController;
    private root?: THREE.Mesh<THREE.BoxGeometry, THREE.ShaderMaterial>;
    private selection?: ZoneSkyboxSelection;
    private readonly fallback: THREE.Color | THREE.Texture | null;
    private state: 'default' | 'disabled' | 'color' | 'loading' | 'ready' | 'error' = 'default';
    private draws = 0;
    private source = '';
    private resolvedSource = '';
    private error?: string;
    private dimensions?: { width: number; height: number };
    private disposed = false;

    constructor(private readonly scene: THREE.Scene, private readonly options: Options) {
        this.fallback = scene.background;
        options.signal.addEventListener('abort', () => this.dispose(), { once: true });
    }

    select(selection: ZoneSkyboxSelection | undefined, entities: ReadonlyMap<string, Entity>): void {
        if (this.disposed) return;
        const signature = JSON.stringify(selection ? [selection.entity.id, selection.mode, selection.source, selection.color] : []);
        if (signature === this.signature) {
            if (selection && this.root) this.root.material.uniforms.skyboxRotation.value.makeRotationFromQuaternion(entityTransform(selection.entity, entities).rotation.clone().invert());
            return;
        }
        this.clear(); this.signature = signature; this.selection = selection; this.draws = 0; this.error = undefined; this.dimensions = undefined;
        this.source = selection?.source ?? ''; this.resolvedSource = '';
        if (!selection) { this.state = 'default'; this.scene.background = this.fallback; return; }
        if (selection.mode === 'disabled') { this.state = 'disabled'; this.scene.background = null; return; }
        // While loading, use exactly the Zone's authored solid color, as native
        // Skybox does before its map is ready. A failure is never marked ready.
        this.scene.background = new THREE.Color(...selection.color);
        if (!selection.source) { this.state = 'color'; return; }
        const controller = new AbortController(); this.request = controller; this.state = 'loading';
        const current = () => !this.disposed && !controller.signal.aborted && this.request === controller;
        void this.load(selection, entities, controller, current).catch(error => {
            if (!current()) return;
            this.state = 'error'; this.error = String(error instanceof Error ? error.message : error).slice(0, 500);
            this.options.warn(`${selection.entity.name || 'Zone'} skybox could not load: ${this.error}`);
        });
    }

    private async load(selection: ZoneSkyboxSelection, entities: ReadonlyMap<string, Entity>, controller: AbortController, current: () => boolean): Promise<void> {
        let texture: THREE.Texture | undefined;
        let root: THREE.Mesh<THREE.BoxGeometry, THREE.ShaderMaterial> | undefined;
        const check = () => { controller.signal.throwIfAborted(); this.options.assertCurrent(); if (!current()) throw new DOMException('Skybox source ended', 'AbortError'); };
        try {
            check(); texture = await this.options.load(selection.source, controller.signal); check();
            const image = texture.image as { width?: number; height?: number } | undefined;
            if (!image || !Number.isSafeInteger(image.width) || !Number.isSafeInteger(image.height) || !image.width || !image.height) throw Error('Skybox image has invalid dimensions');
            // The current native Hub sources are equirectangular. A cubemap
            // cross/strip needs its actual layout conversion, never stretching.
            if (image.width !== image.height * 2) throw Error('Skybox image is not an equirectangular 2:1 map; cubemap layouts are unsupported');
            this.dimensions = { width: image.width, height: image.height };
            this.resolvedSource = typeof texture.userData.assetSource === 'string' ? texture.userData.assetSource : selection.source;
            const color = selection.color.every(value => value === 0) ? [1, 1, 1] : selection.color;
            const material = new THREE.ShaderMaterial({
                uniforms: { skyboxMap: { value: texture }, skyboxColor: { value: new THREE.Vector3(...color) },
                    skyboxRotation: { value: new THREE.Matrix4().makeRotationFromQuaternion(entityTransform(selection.entity, entities).rotation.clone().invert()) } },
                side: THREE.BackSide, depthTest: true, depthWrite: false,
                vertexShader: `varying vec3 skyboxDirection;
                    void main() {
                        skyboxDirection = position;
                        gl_Position = projectionMatrix * mat4(mat3(viewMatrix)) * vec4(position, 1.0);
                        gl_Position.z = gl_Position.w;
                    }`,
                fragmentShader: `uniform sampler2D skyboxMap; uniform vec3 skyboxColor; uniform mat4 skyboxRotation;
                    varying vec3 skyboxDirection;
                    #include <common>
                    void main() {
                        vec3 direction = normalize(mat3(skyboxRotation) * skyboxDirection);
                        gl_FragColor = vec4(texture2D(skyboxMap, equirectUv(direction)).rgb * skyboxColor, 1.0);
                        #include <tonemapping_fragment>
                        #include <colorspace_fragment>
                    }`,
            });
            root = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), material);
            root.name = 'Native Zone skybox'; root.frustumCulled = false; root.renderOrder = -Infinity; root.visible = false;
            root.onAfterRender = () => { if (current()) this.draws++; };
            this.root = root; this.scene.add(root);
            texture = undefined; // The installed root now owns its texture.
            await this.options.prepare(root, current); check();
            root.visible = true; this.scene.background = null; this.state = 'ready'; root = undefined;
        } finally {
            if (root && this.root === root) this.disposeRoot();
            texture?.dispose();
        }
    }

    diagnostics() {
        return { state: this.state, selectedZone: this.selection?.entity.id, name: this.selection?.entity.name,
            source: this.source, resolvedSource: this.resolvedSource, dimensions: this.dimensions,
            renderedDraws: this.draws, activeLoads: this.state === 'loading' ? 1 : 0,
            ...(this.error ? { error: this.error } : {}),
            supported: 'Native simple-volume containment, volume/UUID layering, inherit/disabled/enabled, rotation, color and full-resolution equirectangular image/EXR skybox',
            unsupported: ['compound convex-hull Zone', 'cubemap cross/strip layout', 'procedural skybox', 'Zone ambient/key-light/haze/bloom/postprocessing parity'] };
    }

    private clear(): void {
        this.request?.abort(); this.request = undefined;
        this.disposeRoot();
    }

    private disposeRoot(): void {
        if (this.root) {
            this.scene.remove(this.root); this.root.geometry.dispose();
            const texture = this.root.material.uniforms.skyboxMap.value; if (texture instanceof THREE.Texture) texture.dispose();
            this.root.material.dispose(); this.root = undefined;
        }
    }

    dispose(): void {
        if (this.disposed) return; this.disposed = true; this.clear(); this.scene.background = this.fallback; this.state = 'default'; this.selection = undefined;
    }
}
