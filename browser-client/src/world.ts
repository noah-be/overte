// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { assetDependency, colliderDistance, constrainCamera, entityCollider, entityTransform, materialRGB, parseMaterialData, poseRecord, quaternion, resolveCollision, unsupportedEntityEffects, vector } from './world-data';
import type { Avatar, Collider, Entity, MaterialData, Pose, Quat, Vec3 } from './world-data';
import { FrameMetrics } from './frame-metrics';
import { MeshCollision } from './mesh-collision';
import { AvatarRig, type AvatarMapping } from './avatar-rig';
import { fstDependencies } from './fst-dependencies';
import { requireAssetResponse } from './asset-errors';
import { applyNativeFbxOpacity } from './fbx-materials';
import { applyNativeMaterialAlpha, getNativeAlphaOptions, nativeOpacityMapMode, type MappedMaterial, type NativeAlphaOptions } from './native-alpha-material';
import { applyNativeModelRenderState, applyNativeRenderState, cloneNativeMaterialForGeometry, nativeCullFaceMode } from './native-render-state';
import { parseTexturedModel } from './model-textures';
import { ModelResources } from './model-resources';
import { WorldImageCache } from './world-image-cache';
import { EmbeddedFbxImages } from './embedded-fbx-images';
import { BakedFbxPreparePool } from './model-fbx-pool';
import { PreparedFbxCache } from './prepared-fbx-cache';
import { ModelLoadScheduler } from './model-load-scheduler';
import { ModelGeometryStage } from './model-geometry-stage';
import { InitialSurfaceWait } from './initial-surface-wait';
import { SimulationClock } from './simulation-clock';
import { colorTextureCandidate,readColorTextureMetadata,type TextureRole } from './color-texture-metadata';
import { UnsupportedNativeCompression, type NativeCompressedColorCache, type CompressionCapabilities } from './native-compressed-color';
import { batchStaticModel, inspectStaticModel, type StaticModelBatch, type StaticModelBatchInspection } from './static-model-batch';
import { hasNativeZeroLightShader, installNativeZeroLightShader, restoreNativeZeroLightShader } from './native-zero-lights';
export type { Avatar, Entity, Pose, Vec3 } from './world-data';

export interface WorldOptions {
  resolveAsset(url: string): string;
  /** Reviewed performance experiment, fixed for this World; disabled by default. */
  zeroLightGuard?: boolean;
  /** Optional approved-session factory; absent means the unchanged original-image path. */
  compressedColors?(capabilities:CompressionCapabilities,worldSignal:AbortSignal):NativeCompressedColorCache;
  onPose(pose: Pose): void;
  onInteract(entity: Entity): void;
  onStatus(message: string, kind?: 'info' | 'warning' | 'error'): void;
}

function disposeObject(root: THREE.Object3D): void {
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh || object instanceof THREE.Line)) return;
    object.geometry.dispose();
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) {
        value.dispose();
        if (typeof ImageBitmap !== 'undefined' && value.image instanceof ImageBitmap) value.image.close();
      }
      material.dispose();
    }
  });
}

export class BrowserWorld {
  readonly canvas: HTMLCanvasElement;
  readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(70, 1, 0.05, 10000);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly entities = new Map<string, Entity>();
  private readonly objects = new Map<string, THREE.Group>();
  private readonly signatures = new Map<string, string>();
  private readonly modelBatches = new Map<THREE.Group,{value:StaticModelBatch;candidate:StaticModelBatchInspection}>();
  private readonly avatars = new Map<string, THREE.Group>();
  private readonly avatarModels = new Map<THREE.Group,{source:string; snapshot:Avatar; rig?:AvatarRig}>();
  private readonly resizeObserver: ResizeObserver;
  private readonly abort = new AbortController();
  private compressedColorCache?: NativeCompressedColorCache;
  private readonly imageCache = new WorldImageCache({signal:this.abort.signal});
  private readonly embeddedFbxImages = new EmbeddedFbxImages(this.abort.signal);
  private readonly embeddedFbxCounts={preparations:0,convertedImages:0,extractedBytes:0,skippedOversize:0,skippedUnsupported:0};
  private readonly fbxPreparePool = new BakedFbxPreparePool({signal:this.abort.signal,limit:2});
  private readonly preparedFbx = new PreparedFbxCache({signal:this.abort.signal});
  private readonly modelScheduler = new ModelLoadScheduler({signal:this.abort.signal});
  private readonly modelReaders = new WeakMap<THREE.Group,AbortController>();
  private readonly modelGeometry = new WeakMap<THREE.Group,ModelGeometryStage>();
  private readonly loadManagers = new Set<THREE.LoadingManager>();
  private readonly zeroLightWarnings = new WeakSet<THREE.Material>();
  private readonly zeroLightGuard: boolean;
  private readonly localLights = new Set<THREE.PointLight | THREE.SpotLight>();
  private readonly pointSlots = Array.from({ length: 8 }, () => new THREE.PointLight(0xffffff, 0));
  private readonly spotSlots = Array.from({ length: 8 }, () => new THREE.SpotLight(0xffffff, 0));
  private compilingGraphics = 0;
  private lastLightSelection = 0;
  private readonly raycaster = new THREE.Raycaster();
  private readonly metrics = new FrameMetrics();
  private readonly loadPhases = new Map<string, { count: number; totalMs: number; maxMs: number }>();
  private colliders: Collider[] = [];
  private readonly meshCollisions = new Map<string, { matrix: string; value: MeshCollision }>();
  private pendingModelColliders: Collider[] = [];
  private readonly initialSurfaceWait = new InitialSurfaceWait();
  private keys = new Set<string>();
  private position = new THREE.Vector3(0, 1, 0);
  private spawn = new THREE.Vector3(0, 1, 0);
  private velocity = new THREE.Vector3();
  private yaw = 0;
  private pitch = 0;
  private grounded = false;
  private enabled = false;
  private inputEnabled = true;
  private presentationEnabled = true;
  private renderedFrames = 0;
  private thirdPerson = false;
  private localAvatarID = '';
  private readonly self: THREE.Group;
  private frame = 0;
  private readonly simulationClock = new SimulationClock();
  private lastPose = 0;
  private disposed = false;
  private touchMove = new THREE.Vector2();
  private touchOrigin?: THREE.Vector2;
  private touchLast?: THREE.Vector2;
  private touchMode: 'move' | 'look' = 'move';

  constructor(private readonly container: HTMLElement, private readonly options: WorldOptions) {
    this.zeroLightGuard = options.zeroLightGuard === true;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.canvas = this.renderer.domElement;
    this.canvas.tabIndex = 0;
    this.canvas.setAttribute('aria-label', 'Overte world. Click to look around. WASD to move, Space to jump, E to interact, V to see your avatar, Escape to release the mouse.');
    this.canvas.style.cssText = 'width:100%;height:100%;display:block;touch-action:none;';
    container.append(this.canvas);
    this.scene.background = new THREE.Color('#18253a');
    this.scene.add(new THREE.HemisphereLight(0xd8e9ff, 0x75715e, 2));
    const sunlight = new THREE.DirectionalLight(0xfff1db, 2.2);
    sunlight.position.set(20, 40, 15);
    this.scene.add(sunlight);
    // Stable light counts avoid compiling a new shader permutation every time
    // a nearby light enters/leaves range. Slots with no contribution stay dark.
    for (const light of [...this.pointSlots, ...this.spotSlots]) this.scene.add(light);
    for (const light of this.spotSlots) this.scene.add(light.target);
    this.self = this.makeAvatar('You', 0x64c5ff);
    this.self.visible = false;
    this.scene.add(this.self);
    void this.prepareGraphics(this.self).then(() => { if (!this.disposed) this.self.visible = this.enabled && this.thirdPerson; });
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.installControls();
    this.frame = requestAnimationFrame(time => this.animate(time));
  }

  private resize(): void {
    const width = Math.max(1, this.container.clientWidth), height = Math.max(1, this.container.clientHeight);
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
  }

  setEnabled(enabled: boolean): void {
    if (this.enabled === enabled) return;
    this.enabled = enabled;
    this.simulationClock.reset();
    this.keys.clear();
    this.velocity.set(0, 0, 0);
    this.touchMove.set(0, 0);
    this.self.visible = enabled && this.thirdPerson && this.self.userData.shadersReady === true;
    if (!enabled && document.pointerLockElement === this.canvas) document.exitPointerLock();
  }
  setInputEnabled(enabled: boolean): void {
    if (this.inputEnabled === enabled) return;
    this.inputEnabled = enabled;
    this.simulationClock.reset();
    this.keys.clear(); this.touchMove.set(0, 0);
    this.touchOrigin = undefined; this.touchLast = undefined;
    if (!enabled && document.pointerLockElement === this.canvas) document.exitPointerLock();
  }
  setPresentationEnabled(enabled: boolean): void { this.presentationEnabled = enabled; }
  /** Capture visitor-rendered pixels, including while a tablet covers the scene. */
  captureScene(): Promise<Blob> {
    if (this.disposed || !this.enabled) return Promise.reject(new Error('Join a world before taking a snapshot'));
    // toBlob snapshots the drawing buffer at invocation. Render immediately
    // before it so WebGL's discarded buffer cannot produce a blank image.
    this.renderer.render(this.scene, this.camera);
    return new Promise((resolve, reject) => {
      this.canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('Unable to capture the world')), 'image/png');
    });
  }
  setSpawn(position: Vec3, orientation?: Quat): void {
    this.position.copy(vector(position)); this.spawn.copy(this.position); this.velocity.set(0, 0, 0);
    this.initialSurfaceWait.reset(); this.simulationClock.reset();
    if (orientation) this.setOrientation(orientation);
  }
  setOrientation(orientation: Quat): void {
    const angles = new THREE.Euler().setFromQuaternion(quaternion(orientation), 'YXZ');
    this.yaw = angles.y;
    this.pitch = THREE.MathUtils.clamp(angles.x, -Math.PI / 2 + 0.05, Math.PI / 2 - 0.05);
  }
  setLocalAvatar(id: string): void {
    this.localAvatarID = id;
    const own = this.avatars.get(id);
    if (own) { this.avatarModels.delete(own); this.scene.remove(own); disposeObject(own); this.avatars.delete(id); }
  }
  getPose(): Pose {
    return poseRecord(this.position, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw), this.velocity);
  }
  get entityCount(): number { return this.entities.size; }
  getSelfAvatarRig() { return this.avatarModels.get(this.self)?.rig?.inspect(); }
  getSelfAvatarRenderState() {
    const rig=this.avatarModels.get(this.self)?.rig;
    this.self.updateWorldMatrix(true,true);
    const bounds=rig ? new THREE.Box3().setFromObject(rig.root) : undefined;
    return {thirdPerson:this.thirdPerson,enabled:this.enabled,selfVisible:this.self.visible,
      selfScale:{x:this.self.scale.x,y:this.self.scale.y,z:this.self.scale.z},selfPosition:{x:this.self.position.x,y:this.self.position.y,z:this.self.position.z},
      rigVisible:rig?.root.visible,modelVisible:rig?.model.visible,modelUnits:rig?.model.userData.unitScaleFactor,
      mapping:rig?.model.userData.avatarMapping ? structuredClone(rig.model.userData.avatarMapping) : undefined,
      cameraPosition:{x:this.camera.position.x,y:this.camera.position.y,z:this.camera.position.z},
      ...(bounds && !bounds.isEmpty() ? {bounds:{min:{x:bounds.min.x,y:bounds.min.y,z:bounds.min.z},max:{x:bounds.max.x,y:bounds.max.y,z:bounds.max.z}}} : {})};
  }
  getRenderInventory() {
    return [...this.objects].filter(([,root]) => root.userData.modelLoaded).map(([id,root]) => {
      let meshes = 0, groups = 0, triangles = 0, skins = 0, morphs = 0;
      const materials = new Set<THREE.Material>();
      root.traverse(object => {
        if (!(object instanceof THREE.Mesh) || !object.visible) return;
        let parent = object.parent;
        while (parent && parent !== root) { if (!parent.visible) return; parent = parent.parent; }
        meshes++;
        const geometry = object.geometry, available = geometry.index?.count ?? geometry.getAttribute('position').count;
        const first = Math.max(0,geometry.drawRange.start), end = Math.min(available,first + geometry.drawRange.count);
        const ranges = Array.isArray(object.material) ? geometry.groups : [{start:first,count:end-first,materialIndex:0}];
        for (const range of ranges) {
          const material = Array.isArray(object.material) ? object.material[range.materialIndex ?? 0] : object.material;
          const count = Math.max(0,Math.min(end,range.start + range.count) - Math.max(first,range.start));
          if (material?.visible && count) { groups++; triangles += count / 3; }
        }
        if (object instanceof THREE.SkinnedMesh) skins++;
        if (Object.keys(object.geometry.morphAttributes).length) morphs++;
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
      });
      return {name:this.entities.get(id)?.name || 'Model',meshes,groups,materials:materials.size,triangles,skins,morphs,
        batchCandidate:this.modelBatches.get(root)?.candidate ?? inspectStaticModel(root,{materialChildren:this.hasMaterialChildren(id)}),
        batchedDrawCallsSaved:this.modelBatches.get(root)?.value.savedDrawCalls ?? 0};
    }).sort((a,b) => b.groups - a.groups);
  }
  getPerformance() {
    return { ...this.metrics.snapshot(), drawingBufferWidth: this.renderer.getContext().drawingBufferWidth,
      drawingBufferHeight: this.renderer.getContext().drawingBufferHeight, drawCalls: this.renderer.info.render.calls,
      triangles: this.renderer.info.render.triangles, geometries: this.renderer.info.memory.geometries,
      textures: this.renderer.info.memory.textures, entities: this.entities.size,
      loadedAvatars: [...this.avatarModels.values()].filter(value => value.rig).length,
      loadedModels: [...this.objects.values()].filter(root => root.userData.modelLoaded).length,
      loadingModels: this.modelScheduler.stats.active, queuedModels: this.modelScheduler.stats.queued,
      compilingGraphics: this.compilingGraphics, parallelShaderCompile: this.renderer.extensions.has('KHR_parallel_shader_compile'),
      meshColliders: this.meshCollisions.size, graphicsActive: this.presentationEnabled,
      imageLoading: this.imageCache.stats(), embeddedImages: {...this.embeddedFbxImages.statistics,...this.embeddedFbxCounts}, fbxPreparation: this.fbxPreparePool.counters,
      preparedFbxCache: this.preparedFbx.stats, modelScheduling: this.modelScheduler.stats,
      compressedColorLoading: this.compressedColorCache?.statistics,
      initialSurfaceWait: this.initialSurfaceWait.state,
      loadPhases: Object.fromEntries([...this.loadPhases].map(([name, value]) => [name, { ...value }])),
      renderedFrames: this.renderedFrames };
  }
  private recordLoadPhase(name: string, started: number): void {
    this.recordLoadDuration(name,performance.now()-started);
  }
  private recordLoadDuration(name:string,elapsed:number):void {
    const previous = this.loadPhases.get(name) ?? { count: 0, totalMs: 0, maxMs: 0 };
    this.loadPhases.set(name, { count: previous.count + 1, totalMs: previous.totalMs + elapsed, maxMs: Math.max(previous.maxMs, elapsed) });
  }
  private async prepareGraphics(root: THREE.Object3D): Promise<void> {
    const revision = (root.userData.shaderRevision ?? 0) + 1;
    root.userData.shaderRevision = revision;
    root.userData.shadersReady = false; root.visible = false;
    this.compilingGraphics++;
    const started = performance.now();
    try {
      this.prepareZeroLightShaders(root);
      await this.renderer.compileAsync(root, this.camera, this.scene);
      if (!this.disposed && root.userData.shaderRevision === revision) root.userData.shadersReady = true;
    } finally { this.compilingGraphics--; this.recordLoadPhase('shaderPrepare', started); }
  }

  /** Replace the domain snapshot, including deletion of entities absent from it. */
  setEntities(values: Entity[]): void {
    const present = new Set(values.map(entity => entity.id));
    this.removeEntities([...this.entities.keys()].filter(id => !present.has(id)));
    this.upsertEntities(values);
  }

  upsertEntities(values: Entity[]): void {
    const started = performance.now();
    for (const incoming of values) {
      if (!incoming.id || !incoming.type) continue;
      const previous = this.entities.get(incoming.id), merged = {...previous,...incoming};
      if (previous?.type === 'Material' && (merged.type !== 'Material' || previous.parentID !== merged.parentID)) this.signatures.delete(previous.parentID || '');
      if (merged.type === 'Material') {
        const parent = this.objects.get(merged.parentID || '');
        if (parent) this.restoreModelBatch(parent);
      }
      this.entities.set(incoming.id, merged);
    }
    for (const entity of this.entities.values()) {
      const unsupportedEffects = unsupportedEntityEffects(entity);
      const transform = entityTransform(entity, this.entities);
      const existing = this.objects.get(entity.id);
      if (existing) { existing.position.copy(transform.position); existing.quaternion.copy(transform.rotation); existing.visible = entity.visible !== false && existing.userData.shadersReady === true; }
      const signature = JSON.stringify([entity.type, entity.shape,
        entity.parentID, entity.dimensions, entity.registrationPoint, entity.color, entity.alpha, entity.unlit,
        entity.intensity, entity.isSpotlight,
        entity.modelURL, entity.textures, entity.shapeType, entity.collisionless, entity.imageURL, entity.text, entity.textColor, entity.materialURL, entity.materialData, entity.parentMaterialName, unsupportedEffects]);
      if (this.signatures.get(entity.id) === signature) continue;
      if (unsupportedEffects.length) this.options.onStatus(`${entity.name || entity.type}: ${unsupportedEffects.join(' and ')} effects are not supported. Basic world rendering remains available.`, 'warning');
      this.signatures.set(entity.id, signature);
      const previous = this.objects.get(entity.id);
      if (previous) { this.modelGeometry.get(previous)?.revoke();this.modelReaders.get(previous)?.abort(); }
      this.meshCollisions.get(entity.id)?.value.dispose(); this.meshCollisions.delete(entity.id);
      if (previous) {
        previous.traverse(object => { if (object instanceof THREE.PointLight || object instanceof THREE.SpotLight) this.localLights.delete(object); });
        this.restoreModelBatch(previous); this.scene.remove(previous); disposeObject(previous);
      }
      const root = new THREE.Group();
      root.userData.entityID = entity.id;
      this.objects.set(entity.id, root);
      this.scene.add(root);
      root.position.copy(transform.position);
      root.quaternion.copy(transform.rotation);
      root.visible = false;
      void this.populateEntity(entity, root).then(async () => {
        if (this.disposed || this.objects.get(entity.id) !== root || entity.type === 'Material') return;
        this.updateMeshCollision(entity, root);
        for (const attachment of this.entities.values()) if (attachment.type === 'Material' && attachment.parentID === entity.id) await this.applyEntityMaterial(attachment);
        if (this.disposed || this.objects.get(entity.id) !== root) return;
        if (entity.type === 'Model') this.prepareModelBatch(entity.id,root);
        await this.prepareGraphics(root);
        if (!this.disposed && this.objects.get(entity.id) === root) root.visible = this.entities.get(entity.id)?.visible !== false && root.userData.shadersReady === true;
      }).catch(error => {
        if (!this.disposed && this.objects.get(entity.id) === root) {
          root.userData.modelFailed = true;
          this.options.onStatus(`Could not load ${entity.name || entity.type}: ${String(error instanceof Error ? error.message : error)}`, 'warning');
        }
      });
    }
    this.colliders = [...this.entities.values()].filter(entity => entity.type !== 'Model').map(entity => entityCollider(entity, this.entities)).filter((value): value is Collider => !!value);
    this.pendingModelColliders = [...this.entities.values()].filter(entity => entity.type === 'Model')
      .map(entity => entityCollider(entity, this.entities)).filter((value): value is Collider => !!value);
    for (const entity of this.entities.values()) {
      const root = this.objects.get(entity.id);
      if (root?.userData.modelGeometryReady) this.modelGeometry.get(root)?.update();
      else if (root && root.userData.modelLoaded) this.updateMeshCollision(entity, root);
    }
    this.recordLoadPhase('entityUpdate', started);
  }

  private hasMaterialChildren(id:string):boolean {
    return [...this.entities.values()].some(entity => entity.type === 'Material' && entity.parentID === id);
  }
  private restoreModelBatch(root:THREE.Group):void {
    this.modelBatches.get(root)?.value.restore(); this.modelBatches.delete(root);
  }
  private prepareModelBatch(id:string,root:THREE.Group):void {
    this.restoreModelBatch(root);
    this.prepareZeroLightShaders(root);
    const options = {materialChildren:this.hasMaterialChildren(id)};
    const candidate = inspectStaticModel(root,options);
    if (!candidate.withinBudget || !candidate.savedDrawCalls) return;
    const started = performance.now(), value = batchStaticModel(root,options);
    this.recordLoadPhase('modelBatch',started);
    if (value.savedDrawCalls) this.modelBatches.set(root,{value,candidate});
  }

  private updateMeshCollision(entity: Entity, root: THREE.Group, geometryRoot: THREE.Object3D = root): void {
    if (entity.type !== 'Model' || !entityCollider(entity, this.entities)) return;
    root.updateWorldMatrix(true, true);
    const matrix = root.matrixWorld.elements.join(',');
    if (this.meshCollisions.get(entity.id)?.matrix === matrix) return;
    this.meshCollisions.get(entity.id)?.value.dispose();
    const started = performance.now();
    this.meshCollisions.set(entity.id, { matrix, value: new MeshCollision(geometryRoot) });
    this.recordLoadPhase('colliderBuild', started);
  }

  /** Limit parsing/download pressure and bring nearby walkable geometry in first. */
  private queuedModel(source: string, entity: Entity, root: THREE.Group): Promise<THREE.Object3D> {
    const reader=new AbortController();this.modelReaders.set(root,reader);
    const stage=new ModelGeometryStage({root,entity,isCurrent:()=>!this.disposed&&this.objects.get(entity.id)===root,
      publish:geometry=>{
        this.updateMeshCollision(this.entities.get(entity.id)??entity,root,geometry);root.userData.modelGeometryReady=true;
      },
      withdraw:()=>{
        root.userData.modelGeometryReady=false;
        if(this.objects.get(entity.id)===root){this.meshCollisions.get(entity.id)?.value.dispose();this.meshCollisions.delete(entity.id);}
      },
    });
    this.modelGeometry.set(root,stage);
    return this.modelScheduler.schedule({
      priority:()=>{
        const current=this.entities.get(entity.id)??entity,collider=entityCollider(current,this.entities);
        return[collider?colliderDistance(this.position,collider):root.position.distanceTo(this.position),root.position.distanceToSquared(this.position)];
      },
      signal:reader.signal,discard:disposeObject,
      run:signal=>{
        if(this.objects.get(entity.id)!==root)throw new DOMException('The model was removed before loading','AbortError');
        return this.loadModel(source,new Set<string>(),undefined,signal,model=>stage.prepare(model)).then(model=>{
          try{stage.prepare(model);return model;}catch(error){disposeObject(model);throw error;}
        });
      },
    }).catch(error=>{stage.revoke();throw error;});
  }

  removeEntities(ids: string[]): void {
    let materialRemoved = false;
    for (const id of ids) {
      const entity = this.entities.get(id);
      if (entity?.type === 'Material') { this.signatures.delete(entity.parentID || ''); materialRemoved = true; }
      this.entities.delete(id); this.signatures.delete(id);
      this.meshCollisions.get(id)?.value.dispose(); this.meshCollisions.delete(id);
      const root = this.objects.get(id);
      if (root) {
        this.modelGeometry.get(root)?.revoke();this.modelReaders.get(root)?.abort();
        root.traverse(object => { if (object instanceof THREE.PointLight || object instanceof THREE.SpotLight) this.localLights.delete(object); });
        this.restoreModelBatch(root); this.scene.remove(root); disposeObject(root); this.objects.delete(id);
      }
    }
    this.colliders = this.colliders.filter(collider => !ids.includes(collider.id));
    this.pendingModelColliders = this.pendingModelColliders.filter(collider => !ids.includes(collider.id));
    if (materialRemoved) this.upsertEntities([]);
  }

  setAvatars(values: Avatar[]): void {
    const present = new Set(values.map(avatar => avatar.id));
    for (const [id, object] of this.avatars) if (!present.has(id)) { this.avatarModels.delete(object); this.scene.remove(object); disposeObject(object); this.avatars.delete(id); }
    for (const avatar of values) {
      if (!avatar.position) continue;
      if (avatar.id === this.localAvatarID) { this.self.scale.setScalar(Math.min(1000,Math.max(.005,avatar.scale || 1))); this.updateAvatarModel(this.self,avatar); continue; }
      let object = this.avatars.get(avatar.id);
      if (!object) {
        object = this.makeAvatar(avatar.displayName || 'Participant', 0xf3b96a);
        this.avatars.set(avatar.id, object); this.scene.add(object);
        const current = object;
        void this.prepareGraphics(current).then(() => { if (!this.disposed && this.avatars.get(avatar.id) === current) current.visible = true; });
      }
      object.position.copy(vector(avatar.position));
      object.quaternion.copy(quaternion(avatar.orientation));
      object.scale.setScalar(Math.min(1000, Math.max(0.005, avatar.scale || 1)));
      this.updateAvatarModel(object,avatar);
    }
  }

  private updateAvatarModel(root:THREE.Group, avatar:Avatar):void {
    const name = avatar.displayName || (root === this.self ? 'You' : 'Participant');
    if (root.userData.avatarLabelName !== name) {
      const old = root.userData.avatarLabel as THREE.Object3D;
      root.remove(old); disposeObject(old);
      const label = this.textPlane(name,'#ffffff','rgba(20,30,45,0.8)');
      label.position.y = 1.1; label.scale.set(1.5,.25,1); root.add(label);
      root.userData.avatarLabel = label; root.userData.avatarLabelName = name;
    }
    const previous = this.avatarModels.get(root);
    const source = avatar.skeletonModelURL || '';
    if (previous?.source === source) { previous.snapshot = avatar; previous.rig?.apply(avatar); return; }
    if (previous?.rig) {
      root.remove(previous.rig.root); disposeObject(previous.rig.root);
      const fallback = this.makeAvatar(avatar.displayName || 'Participant',root === this.self ? 0x64c5ff : 0xf3b96a);
      for (const child of [...fallback.children]) if (child !== fallback.userData.avatarLabel) root.add(child);
      disposeObject(fallback);
    }
    this.avatarModels.delete(root);
    if (!source) return;
    const state = {source, snapshot:avatar, rig:undefined as AvatarRig|undefined};
    this.avatarModels.set(root,state);
    void this.loadModel(source).then(async model => {
      if (this.disposed || this.avatarModels.get(root) !== state) { disposeObject(model); return; }
      let rig:AvatarRig;
      try { rig = new AvatarRig(model, model.userData.avatarFormat || 'fbx', model.userData.avatarMapping as AvatarMapping|undefined); }
      catch (error) { disposeObject(model); throw error; }
      rig.apply(state.snapshot);
      try { await this.prepareGraphics(rig.root); }
      catch (error) { disposeObject(rig.root); throw error; }
      if (this.disposed || this.avatarModels.get(root) !== state) { disposeObject(rig.root); return; }
      // Keep the usable fallback until actual avatar geometry and shaders exist.
      for (const child of [...root.children]) if (child !== root.userData.avatarLabel) { root.remove(child); disposeObject(child); }
      state.rig = rig; root.add(rig.root); rig.root.visible = true;
      rig.apply(state.snapshot);
    }).catch(error => {
      if (!this.disposed && this.avatarModels.get(root) === state) this.options.onStatus(`Avatar ${avatar.displayName || 'Participant'} could not load: ${error instanceof Error ? error.message : String(error)}`, 'warning');
    });
  }

  private makeAvatar(name: string, color: number): THREE.Group {
    const root = new THREE.Group();
    const material = new THREE.MeshStandardMaterial({ color, roughness: 0.7 });
    const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.25, 0.8, 4, 12), material);
    body.position.y = -0.1; root.add(body);
    const head = new THREE.Mesh(new THREE.SphereGeometry(0.19, 16, 12), material.clone());
    head.position.y = 0.63; root.add(head);
    const nose = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.14, 8), new THREE.MeshStandardMaterial({ color: 0x263544 }));
    nose.rotation.x = -Math.PI / 2; nose.position.set(0, 0.64, -0.2); root.add(nose);
    const label = this.textPlane(name, '#ffffff', 'rgba(20,30,45,0.8)');
    label.position.y = 1.1; label.scale.set(1.5, 0.25, 1); root.add(label);
    root.userData.avatar = true;
    root.userData.avatarLabel = label;
    root.userData.avatarLabelName = name;
    return root;
  }

  private textPlane(text: string, color: string, background = 'transparent'): THREE.Mesh {
    const canvas = document.createElement('canvas'); canvas.width = 1024; canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = background; context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = color; context.font = '48px sans-serif'; context.textBaseline = 'middle'; context.textAlign = 'center';
    text.split('\n').slice(0, 4).forEach((line, index, lines) => context.fillText(line.slice(0, 140), 512, 128 + (index - (lines.length - 1) / 2) * 54, 1000));
    const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
    const material = new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide });
    applyNativeRenderState(material, { cullFaceMode: 'CULL_NONE' });
    return new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  }

  private baseMaterial(entity: Entity): THREE.Material {
    const color = entity.color ? new THREE.Color(entity.color.red / 255, entity.color.green / 255, entity.color.blue / 255) : new THREE.Color('#cccccc');
    const params = { color, opacity: entity.alpha ?? 1, transparent: (entity.alpha ?? 1) < 1, side: THREE.DoubleSide };
    return entity.unlit ? new THREE.MeshBasicMaterial({ ...params, toneMapped: false }) : new THREE.MeshStandardMaterial({ ...params, roughness: 0.7 });
  }
  private async texture(url: string, color = true, role:TextureRole='other', signal=this.abort.signal): Promise<THREE.Texture> {
    signal.throwIfAborted();
    if (/\.texmeta\.json(?:[?#]|$)/i.test(url)) return this.originalTexture(url, color,role,signal);
    const manager=new THREE.LoadingManager(),abort=()=>manager.abort();this.loadManagers.add(manager);signal.addEventListener('abort',abort,{once:true});
    try{const texture=await this.imageCache.loader(manager).loadAsync(this.options.resolveAsset(url));
      if (this.disposed||signal.aborted) { texture.dispose(); throw new DOMException('Session ended while loading a texture','AbortError'); }
      if (color) texture.colorSpace = THREE.SRGBColorSpace;
      return texture;
    }finally{signal.removeEventListener('abort',abort);this.loadManagers.delete(manager);}
  }

  private async originalTexture(url: string, color: boolean,role:TextureRole='other',signal=this.abort.signal): Promise<THREE.Texture> {
    signal.throwIfAborted();
    let colors:NativeCompressedColorCache|undefined,caps:CompressionCapabilities|undefined,assertApproval:(()=>void)|undefined;
    if(color&&(role==='albedo'||role==='emissive')&&this.options.compressedColors){
      const gl=this.renderer.getContext();caps={s3tc:!!gl.getExtension('WEBGL_compressed_texture_s3tc'),s3tcSRGB:!!gl.getExtension('WEBGL_compressed_texture_s3tc_srgb'),maximumTextureSize:gl.getParameter(gl.MAX_TEXTURE_SIZE)};
      // Obtain current approval before even requesting metadata; denial is never a PNG fallback.
      colors=this.options.compressedColors(caps,this.abort.signal);this.compressedColorCache=colors;
      assertApproval=colors.captureApproval();
    }
    const response = await fetch(this.options.resolveAsset(url), { signal });
    await requireAssetResponse(response,'Texture metadata');
    const metadata = (colors?await readColorTextureMetadata(response,signal):await response.json()) as { original?: string; uncompressed?: string };
    signal.throwIfAborted();assertApproval?.();
    if(colors&&caps){
      const candidate=colorTextureCandidate(metadata,role,caps);
      if(candidate){
        const started=performance.now();
        try{
          const texture=await colors.load(assetDependency(url,candidate.source),{signal,sampler:{flipY:true}});
          if(texture.format!==candidate.format||signal.aborted||this.disposed){texture.dispose();if(signal.aborted||this.disposed)throw new DOMException('Compressed material was cancelled','AbortError');throw Error('Texture metadata codec differs from its validated KTX');}
          return texture;
        }catch(error){if(!(error instanceof UnsupportedNativeCompression))throw error;assertApproval?.();}
        finally{this.recordLoadPhase('compressedColor',started);}
      }
    }
    const source = metadata.original || metadata.uncompressed;
    if (typeof source!=='string'||!source||source.length>4096||/\.texmeta\.json(?:[?#]|$)/i.test(source)) throw new Error('Texture metadata has no supported original image');
    const texture=await this.texture(assetDependency(url, source), color,role,signal);
    try{signal.throwIfAborted();assertApproval?.();return texture;}catch(error){texture.dispose();throw error;}
  }

  private async populateEntity(entity: Entity, root: THREE.Group): Promise<void> {
    const size = vector(entity.dimensions, 1);
    const content = new THREE.Group(); root.add(content);
    content.position.copy(new THREE.Vector3(0.5, 0.5, 0.5).sub(vector(entity.registrationPoint, 0.5)).multiply(size));
    let mesh: THREE.Mesh | undefined;
    switch (entity.type) {
      case 'Box': mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), this.baseMaterial(entity)); break;
      case 'Sphere': mesh = new THREE.Mesh(new THREE.SphereGeometry(0.5, 24, 16), this.baseMaterial(entity)); break;
      case 'Shape': {
        const shape = (entity.shape || 'Sphere').toLowerCase();
        const geometry = shape === 'cube' ? new THREE.BoxGeometry(1, 1, 1)
          : shape === 'cylinder' ? new THREE.CylinderGeometry(0.5, 0.5, 1, 24)
          : shape === 'cone' ? new THREE.ConeGeometry(0.5, 1, 24)
          : shape === 'tetrahedron' ? new THREE.TetrahedronGeometry(0.5)
          : shape === 'octahedron' ? new THREE.OctahedronGeometry(0.5)
          : shape === 'dodecahedron' ? new THREE.DodecahedronGeometry(0.5)
          : shape === 'icosahedron' ? new THREE.IcosahedronGeometry(0.5)
          : shape === 'circle' || shape === 'quad' ? new THREE.PlaneGeometry(1, 1)
          : shape === 'sphere' ? new THREE.SphereGeometry(0.5, 24, 16) : undefined;
        if (!geometry) throw new Error(`Unsupported shape ${entity.shape}`);
        mesh = new THREE.Mesh(geometry, this.baseMaterial(entity)); break;
      }
      case 'Model': {
        if (!entity.modelURL) throw new Error('Model has no asset URL');
        this.options.onStatus(`Loading ${entity.name || 'model'}…`, 'info');
        const model = await this.queuedModel(entity.modelURL, entity, root);
        const stage=this.modelGeometry.get(root)!;let committed=false;
        try{
          if(this.objects.get(entity.id)!==root||this.disposed)throw new DOMException('The model owner was removed','AbortError');
          if(entity.textures)await this.overrideTextures(model,entity.textures,this.modelReaders.get(root)?.signal);
          this.modelReaders.get(root)?.signal.throwIfAborted();
          if(this.objects.get(entity.id)!==root||this.disposed)throw new DOMException('The model owner was removed','AbortError');
          stage.commit(content);root.userData.modelLoaded=true;committed=true;
          this.options.onStatus(`Loaded ${entity.name || 'model'}`,'info');
        }finally{
          if(!committed){stage.revoke();disposeObject(model);}
        }
        return;
      }
      case 'Image': {
        if (!entity.imageURL) throw new Error('Image has no asset URL');
        const material = new THREE.MeshBasicMaterial({ map: await this.texture(entity.imageURL), side: THREE.DoubleSide, transparent: true });
        applyNativeRenderState(material, { cullFaceMode: 'CULL_NONE' });
        mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material); break;
      }
      case 'Text': {
        const color = entity.textColor ? `rgb(${entity.textColor.red},${entity.textColor.green},${entity.textColor.blue})` : '#ffffff';
        mesh = this.textPlane(entity.text || '', color); break;
      }
      case 'Material': await this.applyEntityMaterial(entity); return;
      case 'Light': {
        const color = entity.color ? new THREE.Color(entity.color.red / 255, entity.color.green / 255, entity.color.blue / 255) : new THREE.Color(0xffffff);
        const intensity = typeof entity.intensity === 'number' ? Math.max(0, entity.intensity) : 1;
        const light = entity.isSpotlight ? new THREE.SpotLight(color, intensity, Math.max(size.x, size.y, size.z)) : new THREE.PointLight(color, intensity, Math.max(size.x, size.y, size.z));
        if (light instanceof THREE.SpotLight) { light.target.position.set(0, 0, -1); root.add(light.target); }
        this.localLights.add(light);
        light.visible = false;
        content.add(light); return;
      }
      case 'Zone': return; // Zone haze, skybox and postprocessing are optional; scene illumination remains readable.
      default: this.options.onStatus(`${entity.name || entity.type}: ${entity.type} rendering is not supported by this first version.`, 'warning'); return;
    }
    if (mesh) { mesh.scale.copy(size); content.add(mesh); }
    if (this.disposed || this.objects.get(entity.id) !== root) disposeObject(content);
  }

  private async loadModel(source: string, visited = new Set<string>(), textureBase?: string, signal = this.abort.signal, onGeometryReady?: (model:THREE.Object3D)=>void): Promise<THREE.Object3D> {
    signal.throwIfAborted();
    if (visited.has(source) || visited.size >= 8) throw new Error('Model mapping contains a cycle or too many nested mappings');
    visited.add(source);
    const pathname = source.split(/[?#]/)[0].toLowerCase();
    if (pathname.endsWith('.fst')) {
      const response = await fetch(this.options.resolveAsset(source), { signal });
      await requireAssetResponse(response,'FST');
      const mapping = await response.text();
      const dependencies = fstDependencies(source, mapping);
      const value = (key:string) => Number(new RegExp(`^\\s*${key}\\s*=\\s*(.+)\\s*$`,'m').exec(mapping)?.[1] ?? (key === 'scale' ? 1 : 0));
      const scale = value('scale'), rotation = {x:value('rx'),y:value('ry'),z:value('rz')};
      if (!Number.isFinite(scale) || scale <= 0 || !Object.values(rotation).every(Number.isFinite)) throw new Error('Invalid avatar mapping transform');
      let mappedModel: THREE.Object3D | undefined;
      const applyMapping = (model: THREE.Object3D): void => {
        if (mappedModel === model) return;
        if (mappedModel) throw new Error('Model mapping changed geometry during one load');
        model.userData.avatarMapping = {scale, rotation:Object.fromEntries(Object.entries(rotation).map(([axis,degrees]) => [axis,THREE.MathUtils.degToRad(degrees)])),
          root:/^\s*joint\s*=\s*jointRoot\s*=\s*(.+)\s*$/m.exec(mapping)?.[1]?.trim() || 'Hips'};
        mappedModel = model;
      };
      // Mapping is metadata only for Model entities. Apply nested metadata once,
      // child to parent, before a geometry consumer can normalize the hierarchy.
      // AvatarRig remains the consumer of actual avatar scale/rotation.
      const publishGeometry = onGeometryReady ? (model: THREE.Object3D): void => {
        applyMapping(model); onGeometryReady(model);
      } : undefined;
      const model = await this.loadModel(dependencies.model, visited, dependencies.textures ?? textureBase, signal, publishGeometry);
      const resources = new ModelResources(); resources.capture(model);
      let completed = false;
      try {
        signal.throwIfAborted();
        applyMapping(model);
        const materialMap = /^\s*materialMap\s*=\s*(.+)\s*$/m.exec(mapping)?.[1]?.trim();
        if (materialMap) {
          const assignments = JSON.parse(materialMap) as Record<string, string>[];
          if (!Array.isArray(assignments) || assignments.length > 256) throw new Error('Invalid baked material map');
          for (const assignment of assignments) for (const [selector, reference] of Object.entries(assignment)) {
            const url = assetDependency(source, reference);
            signal.throwIfAborted();
            const response = await fetch(this.options.resolveAsset(url), { signal });
            await requireAssetResponse(response,'Baked material');
            const definitions = parseMaterialData(await response.text());
            const name = decodeURIComponent(new URL(url).hash.slice(1));
            const definition = definitions.find(material => material.name === name) ?? definitions[0];
            const material = await this.makeMaterial(definition, url,signal);
            resources.captureMaterial(material);signal.throwIfAborted();
            model.traverse(object => {
              if (!(object instanceof THREE.Mesh)) return;
              const old = Array.isArray(object.material) ? object.material : [object.material];
              const next = old.map(value => {
                if (selector !== 'all' && selector !== `mat::${value.name}`) return value;
                const clone = cloneNativeMaterialForGeometry(material, object.geometry); resources.captureMaterial(clone); return clone;
              });
              object.material = Array.isArray(object.material) ? next : next[0];
            });
          }
        }
        signal.throwIfAborted();completed = true; return model;
      } finally {
        resources.capture(model); resources.releaseKeeping(completed ? model : undefined);
      }
    }
    const manager = new THREE.LoadingManager();
    manager.onError = () => { if (!this.disposed && !signal.aborted) this.options.onStatus('A model dependency or texture could not be loaded. The model may appear incomplete.', 'warning'); };
    let embeddedScope: ReturnType<EmbeddedFbxImages['register']> | undefined;
    manager.setURLModifier(url => {
      const embedded=embeddedScope?.resolveURL(url);
      if (embedded!==undefined && embedded!==url) return embedded;
      if (/^(?:data:|blob:)/i.test(url)) return url;
      const resolved = /^(?:https?:|atp:)/i.test(url) ? url : assetDependency(source, url);
      return this.options.resolveAsset(resolved);
    });
    // FBX uses extension handlers and GLTF uses external-image URI handlers.
    // They share decoded sources without sharing material sampler ownership.
    manager.addHandler(/\.(?:png|jpe?g|gif|webp|avif|bmp|svg)(?:[?#].*)?$/i, this.imageCache.loader(manager));
    this.loadManagers.add(manager);
    const abortDependencies=()=>manager.abort();
    signal.addEventListener('abort',abortDependencies,{once:true});
    try {
      signal.throwIfAborted();
      if (pathname.endsWith('.gltf') || pathname.endsWith('.glb')) {
        const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        const model = (await new GLTFLoader(manager).loadAsync(source)).scene;
        try { applyNativeModelRenderState(model); } catch (error) { disposeObject(model); throw error; }
        model.userData.avatarFormat = 'gltf'; return model;
      }
      if (pathname.endsWith('.fbx')) {
        const { FBXLoader } = await import('three/addons/loaders/FBXLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        // Cache only prepared bytes at the exact authorized asset route. A
        // producer belongs to its pending readers, not the first model instance.
        const modelURL=this.options.resolveAsset(source),prepareStarted=performance.now();
        const prepared=await this.preparedFbx.get(modelURL,async producerSignal=>{
          const response=await fetch(modelURL,{signal:producerSignal});
          await requireAssetResponse(response,'FBX');
          const bytes=await response.arrayBuffer();
          const prepared=await this.fbxPreparePool.prepare(bytes,producerSignal);
          if(prepared.embeddedCounts){const counts=prepared.embeddedCounts;this.embeddedFbxCounts.preparations++;this.embeddedFbxCounts.convertedImages+=counts.converted;this.embeddedFbxCounts.extractedBytes+=counts.rawBytes;this.embeddedFbxCounts.skippedOversize+=counts.skippedOversize;this.embeddedFbxCounts.skippedUnsupported+=counts.skippedUnsupported;}
          this.recordLoadDuration('fbxMaterialBindings',prepared.phases.materialBindingsMs);
          this.recordLoadDuration('fbxDecode',prepared.phases.decodeMs);
          return prepared;
        },signal);
        this.recordLoadPhase('fbxPrepareWait',prepareStarted);
        signal.throwIfAborted();
        const {buffer}=prepared;
        if(prepared.embeddedImages?.length) embeddedScope=this.embeddedFbxImages.register(buffer,prepared.embeddedImages,signal);
          const model = await this.parseTexturedModel(manager, () => {
            const parseStarted = performance.now();
            try {
              const model=new FBXLoader(manager).parse(buffer,textureBase??assetDependency(source,'.'));
              // The loader still owns this model until its image/FST work finishes.
              try {
                // FBXLoader may return a single Group child still parented to
                // its private parse SceneGraph. The normal Model path reparents
                // it too; detach this fresh loader-owned result before staging.
                if (onGeometryReady) { model.removeFromParent(); onGeometryReady(model); }
                return model;
              } catch (error) { disposeObject(model); throw error; }
            }
            finally { this.recordLoadPhase('fbxParse', parseStarted); }
          },signal);
          applyNativeFbxOpacity(model);
          const materials = new Set<MappedMaterial>();
          model.traverse(object => {
            if (object instanceof THREE.Mesh) for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
          });
          try { for (const material of materials) {
            // FBX bindings (including native PBS normalization) enable albedo
            // alpha only when the opacity and albedo texture refer to the same image.
            const map = material.map, opacity = material.alphaMap;
            const albedoImage = map?.image as {src?: string} | undefined, opacityImage = opacity?.image as {src?: string} | undefined;
            const useAlpha = Boolean(map && opacity && (map === opacity || map.image && map.image === opacity.image ||
              albedoImage?.src && albedoImage.src === opacityImage?.src));
            signal.throwIfAborted();await this.configureAlpha(material, { useAlpha },signal);signal.throwIfAborted();
          } } catch (error) { disposeObject(model); throw error; }
          model.userData.avatarFormat = 'fbx'; return model;
      }
      if (pathname.endsWith('.obj')) {
        const { OBJLoader } = await import('three/addons/loaders/OBJLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        const model = await new OBJLoader(manager).loadAsync(source);
        try { applyNativeModelRenderState(model); } catch (error) { disposeObject(model); throw error; }
        model.userData.avatarFormat = 'obj'; return model;
      }
      throw new Error('Unsupported model format (supported: glTF, GLB, FBX, OBJ and FST mappings)');
    } finally { embeddedScope?.close();signal.removeEventListener('abort',abortDependencies);this.loadManagers.delete(manager); }
  }

  /** FBX.parse returns before its textures; classify only fully loaded images. */
  private async parseTexturedModel(manager: THREE.LoadingManager, parse: () => THREE.Object3D, signal = this.abort.signal): Promise<THREE.Object3D> {
    let texturesStarted = performance.now();
    try { return await parseTexturedModel(manager, signal, () => {
      const model = parse(); texturesStarted = performance.now(); return model;
    }, disposeObject); }
    finally { this.recordLoadPhase('fbxTextures', texturesStarted); }
  }

  private async configureAlpha(material: MappedMaterial, options: NativeAlphaOptions,signal=this.abort.signal): Promise<void> {
    const started = performance.now();
    // Only the exact registered wrapper can expose its trusted alpha parent.
    // A foreign/copy mutation retains the original refusal and warning path.
    const guarded = this.zeroLightGuard && hasNativeZeroLightShader(material);
    if (guarded) restoreNativeZeroLightShader(material);
    try { await applyNativeMaterialAlpha(material, options, signal); }
    catch (error) {
      if (this.disposed || this.abort.signal.aborted||signal.aborted) throw error;
      this.options.onStatus(`Texture transparency could not be read for ${material.name || 'a material'}; it may appear incomplete.`, 'warning');
    }
    finally {
      // Even when image classification fails, preserve native scalar blend
      // state. The guard refuses foreign hooks without mutating the material.
      if (!this.disposed && !this.abort.signal.aborted&&!signal.aborted) {
        try { applyNativeRenderState(material); }
        catch { this.options.onStatus('A custom material shader prevented native render-state conversion; it may appear incomplete.', 'warning'); }
        if (guarded) this.prepareZeroLightMaterial(material);
      }
      this.recordLoadPhase('textureAlpha', started);
    }
  }

  /** Terminal material setup: fresh native/FST templates remain unwrapped
   * through alpha/cull conversion. Guard installation precedes batch proof and
   * shader warmup, never occurs during an aborted owner's cleanup, and does
   * not rewrite unlit or foreign material callbacks. */
  private prepareZeroLightShaders(root: THREE.Object3D): void {
    if (!this.zeroLightGuard) return;
    this.abort.signal.throwIfAborted();
    if (this.disposed) throw new DOMException('World presentation ended', 'AbortError');
    const materials = new Set<THREE.Material>();
    root.traverse(object => { if (object instanceof THREE.Mesh) for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material); });
    for (const material of materials) {
      this.abort.signal.throwIfAborted();
      if (this.disposed) throw new DOMException('World presentation ended', 'AbortError');
      this.prepareZeroLightMaterial(material);
    }
  }

  private prepareZeroLightMaterial(material: THREE.Material): void {
    if (!(material instanceof THREE.MeshStandardMaterial || material instanceof THREE.MeshPhongMaterial || material instanceof THREE.MeshLambertMaterial)) return;
    try { installNativeZeroLightShader(material); }
    catch {
      if (!this.zeroLightWarnings.has(material)) {
        this.zeroLightWarnings.add(material);
        this.options.onStatus('A custom or unaudited material shader prevented zero-light optimization; its original rendering is retained.', 'warning');
      }
    }
  }

  private async overrideTextures(root: THREE.Object3D, json: string,signal=this.abort.signal): Promise<void> {
    const replacements = JSON.parse(json) as Record<string, string>;
    for (const [name, url] of Object.entries(replacements)) {
      if (!url) continue;
      const texture = await this.texture(url,true,'albedo',signal);
      const changed = new Set<MappedMaterial>();
      root.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          if ('map' in material && ((material as THREE.MeshStandardMaterial).map?.name === name || material.name === name)) {
            (material as THREE.MeshStandardMaterial).map = texture; material.needsUpdate = true;
            changed.add(material);
          }
        }
      });
      for (const material of changed) {
        const previous = getNativeAlphaOptions(material);
        await this.configureAlpha(material, { ...previous, useAlpha: true },signal);
      }
    }
  }

  private async applyEntityMaterial(entity: Entity): Promise<void> {
    let data = entity.materialData;
    if (entity.materialURL && entity.materialURL !== 'materialData') {
      const response = await fetch(this.options.resolveAsset(entity.materialURL), { signal: this.abort.signal });
      await requireAssetResponse(response,'Material');
      data = await response.text();
    }
    if (!data) throw new Error('Material entity has no material data');
    const materials = parseMaterialData(data);
    const target = this.objects.get(entity.parentID || '');
    if (!target) return;
    this.restoreModelBatch(target);
    const material = await this.makeMaterial(materials[0], entity.materialURL);
    const resources = new ModelResources(); resources.captureMaterial(material);
    if (this.disposed || this.objects.get(entity.parentID || '') !== target) {
      // A replaced target already belongs to its own removal cleanup. Only the
      // newly created template and its unretained maps belong to this branch.
      resources.releaseKeeping(); return;
    }
    resources.capture(target);
    try {
      target.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        const selector = entity.parentMaterialName || '0';
        const previous = Array.isArray(object.material) ? object.material : [object.material];
        const next = previous.map((old, index) => {
          if (selector !== 'all' && selector !== String(index) && selector !== `mat::${old.name}`) return old;
          const clone = cloneNativeMaterialForGeometry(material, object.geometry); resources.captureMaterial(clone); return clone;
        });
        object.material = Array.isArray(object.material) ? next : next[0];
      });
    } finally {
      // Release each obsolete material/map once, keeping shared textures still
      // referenced by unmatched slots and retaining every installed clone.
      resources.capture(target); resources.releaseKeeping(target);
    }
    await this.prepareGraphics(target);
    if (!this.disposed && this.objects.get(entity.parentID || '') === target) target.visible = this.entities.get(entity.parentID || '')?.visible !== false && target.userData.shadersReady === true;
  }

  private async makeMaterial(data: MaterialData, source?: string,signal=this.abort.signal): Promise<THREE.MeshStandardMaterial | THREE.MeshBasicMaterial> {
    signal.throwIfAborted();
    if ((data.model && data.model !== 'hifi_pbr') || data.procedural) {
      this.options.onStatus('Custom shader or toon materials are not supported. Basic material colors and textures are used instead.', 'warning');
    }
    const common = {
      color: data.albedo ? new THREE.Color(...materialRGB(data.albedo)) : 0xffffff,
      opacity: data.opacity ?? 1, transparent: (data.opacity ?? 1) < 1,
      name: data.name, side: THREE.DoubleSide,
    };
    // Unlit materials keep their declared albedo colors without the scene's filmic light grading.
    const material = data.unlit ? new THREE.MeshBasicMaterial({ ...common, toneMapped: false }) : new THREE.MeshStandardMaterial({
      ...common, roughness: data.roughness ?? 0.7, metalness: data.metallic ?? 0,
      emissive: data.emissive ? new THREE.Color(...materialRGB(data.emissive)) : 0,
    });
    const resources = new ModelResources(); resources.captureMaterial(material);
    try {
      // Independent maps can fetch/decode concurrently; the session image cache
      // bounds actual requests to six. Wait for every result before cleanup so
      // a late successful map cannot escape a failed material's ownership.
      const maps = await Promise.allSettled(([ ['albedoMap', 'map', true], ['normalMap', 'normalMap', false], ['roughnessMap', 'roughnessMap', false], ['metallicMap', 'metalnessMap', false], ['emissiveMap', 'emissiveMap', true] ] as const).map(async ([key, field, color]) => {
        const url = data[key];
        if (url && (field === 'map' || material instanceof THREE.MeshStandardMaterial)) {
          const role:TextureRole=field==='map'?'albedo':field==='emissiveMap'?'emissive':'linear';
          const texture = await this.texture(source && source !== 'materialData' ? assetDependency(source, url) : url, color,role,signal);
          if (field === 'map') material.map = texture;
          else if (material instanceof THREE.MeshStandardMaterial) material[field] = texture;
        }
      }));
      const failedMap=maps.find((value):value is PromiseRejectedResult=>value.status==='rejected');
      if(failedMap)throw failedMap.reason;
      signal.throwIfAborted();
      const resolve = (url: string) => source && source !== 'materialData' ? assetDependency(source, url) : url;
      await this.configureAlpha(material, { useAlpha: Boolean(data.albedoMap && data.opacityMap && resolve(data.albedoMap) === resolve(data.opacityMap)),
        mode: nativeOpacityMapMode(data.opacityMapMode), cutoff: data.opacityCutoff },signal);
      applyNativeRenderState(material, { cullFaceMode: nativeCullFaceMode(data.cullFaceMode) });
      return material;
    } catch (error) {
      resources.releaseKeeping(); throw error;
    }
  }

  private installControls(): void {
    const eventOptions = { signal: this.abort.signal };
    const controlled = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space', 'ShiftLeft', 'ShiftRight', 'KeyE', 'KeyV']);
    window.addEventListener('keydown', event => {
      if (event.ctrlKey || event.metaKey || event.altKey || (event.code === 'Space' && event.target instanceof HTMLButtonElement)) return;
      if (!this.enabled || !this.inputEnabled || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
      if (!controlled.has(event.code)) return;
      event.preventDefault(); this.keys.add(event.code);
      if (event.code === 'KeyE' && !event.repeat) this.interact();
      if (event.code === 'KeyV' && !event.repeat) { this.thirdPerson = !this.thirdPerson; this.self.visible = this.thirdPerson && this.self.userData.shadersReady === true; }
    }, eventOptions);
    window.addEventListener('keyup', event => this.keys.delete(event.code), eventOptions);
    const releaseInput = () => { this.keys.clear(); this.touchMove.set(0, 0); this.touchOrigin = undefined; this.touchLast = undefined; this.simulationClock.reset(); };
    window.addEventListener('blur', releaseInput, eventOptions);
    document.addEventListener('visibilitychange', () => { if (document.hidden) releaseInput(); }, eventOptions);
    document.addEventListener('pointerlockchange', () => { if (document.pointerLockElement !== this.canvas) this.keys.clear(); }, eventOptions);
    document.addEventListener('mousemove', event => {
      if (!this.enabled || !this.inputEnabled || document.pointerLockElement !== this.canvas) return;
      this.look(event.movementX, event.movementY);
    }, eventOptions);
    this.canvas.addEventListener('click', event => {
      if (event instanceof PointerEvent && event.pointerType === 'touch') return;
      if (this.enabled && this.inputEnabled && document.pointerLockElement !== this.canvas) {
        this.canvas.focus();
        const request = this.canvas.requestPointerLock();
        if (request) request.catch(() => this.options.onStatus('Mouse capture was denied. Click the world again or use touch controls.', 'warning'));
      }
    }, eventOptions);
    this.canvas.addEventListener('dblclick', () => { if (this.enabled && this.inputEnabled) this.interact(); }, eventOptions);
    this.canvas.addEventListener('pointerdown', event => {
      if (!this.enabled || !this.inputEnabled || event.pointerType !== 'touch') return;
      this.canvas.setPointerCapture(event.pointerId);
      this.touchOrigin = new THREE.Vector2(event.clientX, event.clientY);
      this.touchLast = this.touchOrigin.clone();
      this.touchMode = event.clientX - this.canvas.getBoundingClientRect().left < this.canvas.clientWidth / 2 ? 'move' : 'look';
    }, eventOptions);
    this.canvas.addEventListener('pointermove', event => {
      if (event.pointerType !== 'touch' || !this.touchOrigin || !this.touchLast) return;
      if (this.touchMode === 'move') this.touchMove.set((event.clientX - this.touchOrigin.x) / 70, (event.clientY - this.touchOrigin.y) / 70).clampLength(0, 1);
      else this.look(event.clientX - this.touchLast.x, event.clientY - this.touchLast.y);
      this.touchLast.set(event.clientX, event.clientY);
    }, eventOptions);
    const releaseTouch = () => { this.touchOrigin = undefined; this.touchLast = undefined; this.touchMove.set(0, 0); };
    this.canvas.addEventListener('pointerup', releaseTouch, eventOptions);
    this.canvas.addEventListener('pointercancel', releaseTouch, eventOptions);
    this.canvas.addEventListener('webglcontextlost', event => { event.preventDefault(); this.options.onStatus('Graphics context lost. Reload the page to reconnect.', 'error'); }, eventOptions);
  }

  private look(x: number, y: number): void {
    this.yaw -= x * 0.0025;
    this.pitch = THREE.MathUtils.clamp(this.pitch - y * 0.0025, -Math.PI / 2 + 0.05, Math.PI / 2 - 0.05);
  }
  interact(): void {
    this.raycaster.setFromCamera(new THREE.Vector2(0, 0), this.camera);
    for (const hit of this.raycaster.intersectObjects([...this.objects.values()], true)) {
      if (hit.distance > 5) break;
      let object: THREE.Object3D | null = hit.object;
      while (object && !object.userData.entityID) object = object.parent;
      const entity = object && this.entities.get(object.userData.entityID);
      if (entity && !entity.ignorePickIntersection && entity.visible !== false && entityTransform(entity, this.entities).position.distanceTo(this.position) <= 5) { this.options.onInteract(entity); return; }
    }
    this.options.onStatus('No object within interaction reach. Aim at an object and press E.', 'info');
  }

  /** Resolve movement in bounded 60 Hz steps, independently of render cadence. */
  private simulateMovement(delta: number, waitForSurface: boolean): void {
    const input = new THREE.Vector3(
      Number(this.keys.has('KeyD') || this.keys.has('ArrowRight')) - Number(this.keys.has('KeyA') || this.keys.has('ArrowLeft')) + this.touchMove.x,
      0,
      Number(this.keys.has('KeyS') || this.keys.has('ArrowDown')) - Number(this.keys.has('KeyW') || this.keys.has('ArrowUp')) + this.touchMove.y);
    if (input.lengthSq() > 1) input.normalize();
    if (waitForSurface) input.set(0, 0, 0);
    input.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw).multiplyScalar(this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 5 : 2.8);
    this.velocity.x = input.x; this.velocity.z = input.z;
    if (this.grounded && this.keys.has('Space')) this.velocity.y = 5;
    this.velocity.y = waitForSurface ? 0 : Math.max(-30, this.velocity.y - 9.8 * delta);
    const steps = Math.max(1, Math.ceil(this.velocity.length() * delta / 0.12));
    this.grounded = false;
    for (let step = 0; step < steps; step++) {
      this.position.addScaledVector(this.velocity, delta / steps);
      for (const collider of this.colliders) {
        const collision = resolveCollision(this.position, collider);
        if (!collision) continue;
        this.position.copy(vector(collision.position));
        const normal = vector(collision.normal);
        const speed = this.velocity.dot(normal);
        if (speed < 0) this.velocity.addScaledVector(normal, -speed);
        if (normal.y > 0.5) this.grounded = true;
      }
      for (const { value } of this.meshCollisions.values()) {
        const normal = value.resolve(this.position);
        if (!normal) continue;
        const speed = this.velocity.dot(normal);
        if (speed < 0) this.velocity.addScaledVector(normal, -speed);
        if (normal.y > 0.5) this.grounded = true;
      }
    }
  }

  private animate(time: number): void {
    if (this.disposed) return;
    this.metrics.sample(time);
    const ticks = this.simulationClock.advance(time);
    if (this.enabled) {
      const needsSupport = this.initialSurfaceWait.needsSupport;
      const pendingSurface = needsSupport && this.pendingModelColliders.some(collider => !this.meshCollisions.has(collider.id)
        && !this.objects.get(collider.id)?.userData.modelFailed && !!resolveCollision(this.position, collider));
      let actualSupport = false;
      if (needsSupport) {
        for (const { value } of this.meshCollisions.values()) {
          if (value.supports(this.position)) { actualSupport = true; break; }
        }
      }
      const surface = this.initialSurfaceWait.update(time, pendingSurface, actualSupport);
      if (surface.started) this.options.onStatus('Loading the walkable geometry around you…', 'info');
      const waitForSurface = surface.waiting;
      for (let tick = 0; tick < ticks; tick++) this.simulateMovement(this.simulationClock.stepSeconds, waitForSurface);
      if (this.position.y < this.spawn.y - 100) { this.setSpawn(this.spawn); this.options.onStatus('Returned to spawn after falling outside the world.', 'warning'); }
      if (time - this.lastPose > 50) { this.options.onPose(this.getPose()); this.lastPose = time; }
    }
    const rotation = new THREE.Quaternion().setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ'));
    this.camera.quaternion.copy(rotation);
    this.camera.position.copy(this.position).add(new THREE.Vector3(0, 0.65, 0));
    if (this.thirdPerson) {
      const anchor = this.camera.position.clone();
      const desired = anchor.clone().add(new THREE.Vector3(0, 0.3, 3).applyQuaternion(rotation));
      this.camera.position.copy(constrainCamera(anchor, desired, this.colliders));
    }
    this.self.position.copy(this.position);
    this.self.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw);
    for (const avatar of [this.self, ...this.avatars.values()]) (avatar.userData.avatarLabel as THREE.Object3D|undefined)?.quaternion.copy(this.camera.quaternion).premultiply(avatar.quaternion.clone().invert());
    if (time - this.lastLightSelection > 250) {
      this.lastLightSelection = time;
      const location = new THREE.Vector3();
      const ranked = [...this.localLights].map(light => {
        light.getWorldPosition(location);
        const distanceSquared = location.distanceToSquared(this.camera.position);
        return { light, strength: light.intensity / Math.max(1, distanceSquared), inRange: !light.distance || distanceSquared < light.distance * light.distance };
      }).filter(item => item.inRange).sort((a, b) => b.strength - a.strength);
      // Bound fragment-light work for large worlds; retain the strongest local
      // contributions at the visitor, plus the separate sun and ambient light.
      for (const light of [...this.pointSlots, ...this.spotSlots]) light.intensity = 0;
      let points = 0, spots = 0;
      for (const { light } of ranked.filter(item => this.entities.get(item.light.parent?.parent?.userData.entityID)?.visible !== false).slice(0, 8)) {
        const slot = light instanceof THREE.SpotLight ? this.spotSlots[spots++] : this.pointSlots[points++];
        light.getWorldPosition(slot.position);
        slot.color.copy(light.color); slot.intensity = light.intensity; slot.distance = light.distance; slot.decay = light.decay;
        if (slot instanceof THREE.SpotLight && light instanceof THREE.SpotLight) {
          light.target.getWorldPosition(slot.target.position);
          slot.angle = light.angle; slot.penumbra = light.penumbra;
        }
      }
    }
    if (this.presentationEnabled) {
      const started = performance.now();
      this.renderer.render(this.scene, this.camera); this.renderedFrames++;
      this.recordLoadPhase('graphicsSubmit', started);
    }
    this.frame = requestAnimationFrame(next => this.animate(next));
  }

  dispose(): void {
    this.disposed = true; this.enabled = false;
    cancelAnimationFrame(this.frame); this.abort.abort(); this.resizeObserver.disconnect();
    for (const manager of this.loadManagers) manager.abort();
    this.loadManagers.clear();
    if (document.pointerLockElement === this.canvas) document.exitPointerLock();
    for (const root of this.modelBatches.keys()) this.restoreModelBatch(root);
    for (const root of this.objects.values()) this.modelGeometry.get(root)?.revoke();
    for (const object of [...this.objects.values(), ...this.avatars.values(), this.self]) disposeObject(object);
    this.avatarModels.clear();
    for (const { value } of this.meshCollisions.values()) value.dispose();
    this.meshCollisions.clear();
    this.renderer.dispose(); this.canvas.remove();
  }
}
