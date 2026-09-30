// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { assetDependency, constrainCamera, entityCollider, entityTransform, parseMaterialData, poseRecord, quaternion, resolveCollision, unsupportedEntityEffects, vector } from './world-data';
import type { Avatar, Collider, Entity, MaterialData, Pose, Quat, Vec3 } from './world-data';
export type { Avatar, Entity, Pose, Vec3 } from './world-data';

export interface WorldOptions {
  resolveAsset(url: string): string;
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
  private readonly avatars = new Map<string, THREE.Group>();
  private readonly resizeObserver: ResizeObserver;
  private readonly abort = new AbortController();
  private readonly loadManagers = new Set<THREE.LoadingManager>();
  private readonly raycaster = new THREE.Raycaster();
  private colliders: Collider[] = [];
  private keys = new Set<string>();
  private position = new THREE.Vector3(0, 1, 0);
  private spawn = new THREE.Vector3(0, 1, 0);
  private velocity = new THREE.Vector3();
  private yaw = 0;
  private pitch = 0;
  private grounded = false;
  private enabled = false;
  private thirdPerson = false;
  private localAvatarID = '';
  private readonly self: THREE.Group;
  private frame = 0;
  private previous = 0;
  private lastPose = 0;
  private disposed = false;
  private touchMove = new THREE.Vector2();
  private touchOrigin?: THREE.Vector2;
  private touchLast?: THREE.Vector2;
  private touchMode: 'move' | 'look' = 'move';

  constructor(private readonly container: HTMLElement, private readonly options: WorldOptions) {
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
    this.self = this.makeAvatar('You', 0x64c5ff);
    this.self.visible = false;
    this.scene.add(this.self);
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
    this.keys.clear();
    this.velocity.set(0, 0, 0);
    this.touchMove.set(0, 0);
    this.self.visible = enabled && this.thirdPerson;
    if (!enabled && document.pointerLockElement === this.canvas) document.exitPointerLock();
  }
  setSpawn(position: Vec3, orientation?: Quat): void {
    this.position.copy(vector(position)); this.spawn.copy(this.position); this.velocity.set(0, 0, 0);
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
    if (own) { this.scene.remove(own); disposeObject(own); this.avatars.delete(id); }
  }
  getPose(): Pose {
    return poseRecord(this.position, new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw), this.velocity);
  }

  /** Replace the domain snapshot, including deletion of entities absent from it. */
  setEntities(values: Entity[]): void {
    const present = new Set(values.map(entity => entity.id));
    this.removeEntities([...this.entities.keys()].filter(id => !present.has(id)));
    this.upsertEntities(values);
  }

  upsertEntities(values: Entity[]): void {
    for (const incoming of values) {
      if (!incoming.id || !incoming.type) continue;
      this.entities.set(incoming.id, { ...this.entities.get(incoming.id), ...incoming });
    }
    for (const entity of this.entities.values()) {
      const unsupportedEffects = unsupportedEntityEffects(entity);
      const transform = entityTransform(entity, this.entities);
      const existing = this.objects.get(entity.id);
      if (existing) { existing.position.copy(transform.position); existing.quaternion.copy(transform.rotation); existing.visible = entity.visible !== false; }
      const signature = JSON.stringify([entity.type, entity.shape,
        entity.parentID, entity.dimensions, entity.registrationPoint, entity.color, entity.alpha, entity.unlit,
        entity.modelURL, entity.textures, entity.imageURL, entity.text, entity.textColor, entity.materialURL, entity.materialData, unsupportedEffects]);
      if (this.signatures.get(entity.id) === signature) continue;
      if (unsupportedEffects.length) this.options.onStatus(`${entity.name || entity.type}: ${unsupportedEffects.join(' and ')} effects are not supported. Basic world rendering remains available.`, 'warning');
      this.signatures.set(entity.id, signature);
      const previous = this.objects.get(entity.id);
      if (previous) { this.scene.remove(previous); disposeObject(previous); }
      const root = new THREE.Group();
      root.userData.entityID = entity.id;
      this.objects.set(entity.id, root);
      this.scene.add(root);
      root.position.copy(transform.position);
      root.quaternion.copy(transform.rotation);
      root.visible = entity.visible !== false;
      void this.populateEntity(entity, root).then(async () => {
        if (this.disposed || this.objects.get(entity.id) !== root || entity.type === 'Material') return;
        for (const attachment of this.entities.values()) if (attachment.type === 'Material' && attachment.parentID === entity.id) await this.applyEntityMaterial(attachment);
      }).catch(error => {
        if (!this.disposed && this.objects.get(entity.id) === root) this.options.onStatus(`Could not load ${entity.name || entity.type}: ${String(error instanceof Error ? error.message : error)}`, 'warning');
      });
    }
    this.colliders = [...this.entities.values()].map(entity => entityCollider(entity, this.entities)).filter((value): value is Collider => !!value);
  }

  removeEntities(ids: string[]): void {
    for (const id of ids) {
      this.entities.delete(id); this.signatures.delete(id);
      const root = this.objects.get(id);
      if (root) { this.scene.remove(root); disposeObject(root); this.objects.delete(id); }
    }
    this.colliders = this.colliders.filter(collider => !ids.includes(collider.id));
  }

  setAvatars(values: Avatar[]): void {
    const present = new Set(values.map(avatar => avatar.id));
    for (const [id, object] of this.avatars) if (!present.has(id)) { this.scene.remove(object); disposeObject(object); this.avatars.delete(id); }
    for (const avatar of values) {
      if (avatar.id === this.localAvatarID || !avatar.position) continue;
      let object = this.avatars.get(avatar.id);
      if (!object) {
        object = this.makeAvatar(avatar.displayName || 'Participant', 0xf3b96a);
        this.avatars.set(avatar.id, object); this.scene.add(object);
      }
      object.position.copy(vector(avatar.position));
      object.quaternion.copy(quaternion(avatar.orientation));
      object.scale.setScalar(Math.min(10, Math.max(0.1, avatar.scale || 1)));
    }
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
    return root;
  }

  private textPlane(text: string, color: string, background = 'transparent'): THREE.Mesh {
    const canvas = document.createElement('canvas'); canvas.width = 1024; canvas.height = 256;
    const context = canvas.getContext('2d')!;
    context.fillStyle = background; context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = color; context.font = '48px sans-serif'; context.textBaseline = 'middle'; context.textAlign = 'center';
    text.split('\n').slice(0, 4).forEach((line, index, lines) => context.fillText(line.slice(0, 140), 512, 128 + (index - (lines.length - 1) / 2) * 54, 1000));
    const texture = new THREE.CanvasTexture(canvas); texture.colorSpace = THREE.SRGBColorSpace;
    return new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: texture, transparent: true, side: THREE.DoubleSide }));
  }

  private baseMaterial(entity: Entity): THREE.Material {
    const color = entity.color ? new THREE.Color(entity.color.red / 255, entity.color.green / 255, entity.color.blue / 255) : new THREE.Color('#cccccc');
    const params = { color, opacity: entity.alpha ?? 1, transparent: (entity.alpha ?? 1) < 1, side: THREE.DoubleSide };
    return entity.unlit ? new THREE.MeshBasicMaterial({ ...params, toneMapped: false }) : new THREE.MeshStandardMaterial({ ...params, roughness: 0.7 });
  }
  private texture(url: string, color = true): Promise<THREE.Texture> {
    return new THREE.TextureLoader().loadAsync(this.options.resolveAsset(url)).then(texture => {
      if (this.disposed) { texture.dispose(); throw new Error('Session ended while loading a texture'); }
      if (color) texture.colorSpace = THREE.SRGBColorSpace;
      return texture;
    });
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
        const model = await this.loadModel(entity.modelURL);
        if (this.objects.get(entity.id) !== root || this.disposed) { disposeObject(model); return; }
        const bounds = new THREE.Box3().setFromObject(model);
        const original = bounds.getSize(new THREE.Vector3());
        if (original.lengthSq() < 1e-12) { disposeObject(model); throw new Error('Model contains no geometry'); }
        model.position.sub(bounds.getCenter(new THREE.Vector3()));
        const normalizer = new THREE.Group(); normalizer.add(model);
        normalizer.scale.set(size.x / Math.max(original.x, 1e-6), size.y / Math.max(original.y, 1e-6), size.z / Math.max(original.z, 1e-6));
        content.add(normalizer);
        if (entity.textures) await this.overrideTextures(model, entity.textures);
        this.options.onStatus(`Loaded ${entity.name || 'model'}`, 'info');
        return;
      }
      case 'Image': {
        if (!entity.imageURL) throw new Error('Image has no asset URL');
        mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: await this.texture(entity.imageURL), side: THREE.DoubleSide, transparent: true })); break;
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
        content.add(light); return;
      }
      case 'Zone': return; // Zone haze, skybox and postprocessing are optional; scene illumination remains readable.
      default: this.options.onStatus(`${entity.name || entity.type}: ${entity.type} rendering is not supported by this first version.`, 'warning'); return;
    }
    if (mesh) { mesh.scale.copy(size); content.add(mesh); }
    if (this.disposed || this.objects.get(entity.id) !== root) disposeObject(content);
  }

  private async loadModel(source: string): Promise<THREE.Object3D> {
    const pathname = source.split(/[?#]/)[0].toLowerCase();
    if (pathname.endsWith('.fst')) {
      const response = await fetch(this.options.resolveAsset(source), { signal: this.abort.signal });
      if (!response.ok) throw new Error(`FST request returned ${response.status}`);
      const mapping = await response.text();
      const filename = /^\s*filename\s*=\s*(.+)\s*$/m.exec(mapping)?.[1]?.trim();
      if (!filename) throw new Error('FST mapping has no filename');
      return this.loadModel(assetDependency(source, filename));
    }
    const manager = new THREE.LoadingManager();
    manager.onError = () => { if (!this.disposed) this.options.onStatus('A model dependency or texture could not be loaded. The model may appear incomplete.', 'warning'); };
    manager.setURLModifier(url => {
      if (/^(?:data:|blob:)/i.test(url)) return url;
      const resolved = /^(?:https?:|atp:)/i.test(url) ? url : assetDependency(source, url);
      return this.options.resolveAsset(resolved);
    });
    this.loadManagers.add(manager);
    try {
      if (pathname.endsWith('.gltf') || pathname.endsWith('.glb')) {
        const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        return (await new GLTFLoader(manager).loadAsync(source)).scene;
      }
      if (pathname.endsWith('.fbx')) {
        const { FBXLoader } = await import('three/addons/loaders/FBXLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        return await new FBXLoader(manager).loadAsync(source);
      }
      if (pathname.endsWith('.obj')) {
        const { OBJLoader } = await import('three/addons/loaders/OBJLoader.js');
        if (this.disposed) throw new Error('Session ended while loading a model');
        return await new OBJLoader(manager).loadAsync(source);
      }
      throw new Error('Unsupported model format (supported: glTF, GLB, FBX, OBJ and FST mappings)');
    } finally { this.loadManagers.delete(manager); }
  }

  private async overrideTextures(root: THREE.Object3D, json: string): Promise<void> {
    const replacements = JSON.parse(json) as Record<string, string>;
    for (const [name, url] of Object.entries(replacements)) {
      if (!url) continue;
      const texture = await this.texture(url);
      root.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          if ('map' in material && ((material as THREE.MeshStandardMaterial).map?.name === name || material.name === name)) {
            (material as THREE.MeshStandardMaterial).map = texture; material.needsUpdate = true;
          }
        }
      });
    }
  }

  private async applyEntityMaterial(entity: Entity): Promise<void> {
    let data = entity.materialData;
    if (entity.materialURL && entity.materialURL !== 'materialData') {
      const response = await fetch(this.options.resolveAsset(entity.materialURL), { signal: this.abort.signal });
      if (!response.ok) throw new Error(`Material request returned ${response.status}`);
      data = await response.text();
    }
    if (!data) throw new Error('Material entity has no material data');
    const materials = parseMaterialData(data);
    const target = this.objects.get(entity.parentID || '');
    if (!target) return;
    const material = await this.makeMaterial(materials[0], entity.materialURL);
    if (this.disposed || this.objects.get(entity.parentID || '') !== target) {
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) value.dispose();
      material.dispose(); return;
    }
    target.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      const selector = entity.parentMaterialName || '0';
      const previous = Array.isArray(object.material) ? object.material : [object.material];
      const next = previous.map((old, index) => selector === 'all' || selector === String(index) || selector === `mat::${old.name}` ? material.clone() : old);
      object.material = Array.isArray(object.material) ? next : next[0];
      previous.forEach((old, index) => { if (old !== next[index]) old.dispose(); });
    });
    material.dispose();
  }

  private async makeMaterial(data: MaterialData, source?: string): Promise<THREE.MeshStandardMaterial | THREE.MeshBasicMaterial> {
    if ((data.model && data.model !== 'hifi_pbr') || data.procedural) {
      this.options.onStatus('Custom shader or toon materials are not supported. Basic material colors and textures are used instead.', 'warning');
    }
    const common = {
      color: data.albedo ? new THREE.Color(...data.albedo as [number, number, number]) : 0xffffff,
      opacity: data.opacity ?? 1, transparent: (data.opacity ?? 1) < 1,
      name: data.name, side: THREE.DoubleSide,
    };
    // Unlit materials keep their declared albedo colors without the scene's filmic light grading.
    const material = data.unlit ? new THREE.MeshBasicMaterial({ ...common, toneMapped: false }) : new THREE.MeshStandardMaterial({
      ...common, roughness: data.roughness ?? 0.7, metalness: data.metallic ?? 0,
      emissive: data.emissive ? new THREE.Color(...data.emissive as [number, number, number]) : 0,
    });
    for (const [key, field, color] of [ ['albedoMap', 'map', true], ['normalMap', 'normalMap', false], ['roughnessMap', 'roughnessMap', false], ['metallicMap', 'metalnessMap', false], ['emissiveMap', 'emissiveMap', true] ] as const) {
      const url = data[key];
      if (url && (field === 'map' || material instanceof THREE.MeshStandardMaterial)) {
        const texture = await this.texture(source && source !== 'materialData' ? assetDependency(source, url) : url, color);
        if (field === 'map') material.map = texture;
        else if (material instanceof THREE.MeshStandardMaterial) material[field] = texture;
      }
    }
    return material;
  }

  private installControls(): void {
    const eventOptions = { signal: this.abort.signal };
    const controlled = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Space', 'ShiftLeft', 'ShiftRight', 'KeyE', 'KeyV']);
    window.addEventListener('keydown', event => {
      if (event.ctrlKey || event.metaKey || event.altKey || (event.code === 'Space' && event.target instanceof HTMLButtonElement)) return;
      if (!this.enabled || event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement || event.target instanceof HTMLSelectElement) return;
      if (!controlled.has(event.code)) return;
      event.preventDefault(); this.keys.add(event.code);
      if (event.code === 'KeyE' && !event.repeat) this.interact();
      if (event.code === 'KeyV' && !event.repeat) { this.thirdPerson = !this.thirdPerson; this.self.visible = this.thirdPerson; }
    }, eventOptions);
    window.addEventListener('keyup', event => this.keys.delete(event.code), eventOptions);
    window.addEventListener('blur', () => this.keys.clear(), eventOptions);
    document.addEventListener('pointerlockchange', () => { if (document.pointerLockElement !== this.canvas) this.keys.clear(); }, eventOptions);
    document.addEventListener('mousemove', event => {
      if (!this.enabled || document.pointerLockElement !== this.canvas) return;
      this.look(event.movementX, event.movementY);
    }, eventOptions);
    this.canvas.addEventListener('click', event => {
      if (event instanceof PointerEvent && event.pointerType === 'touch') return;
      if (this.enabled && document.pointerLockElement !== this.canvas) {
        this.canvas.focus();
        const request = this.canvas.requestPointerLock();
        if (request) request.catch(() => this.options.onStatus('Mouse capture was denied. Click the world again or use touch controls.', 'warning'));
      }
    }, eventOptions);
    this.canvas.addEventListener('dblclick', () => { if (this.enabled) this.interact(); }, eventOptions);
    this.canvas.addEventListener('pointerdown', event => {
      if (!this.enabled || event.pointerType !== 'touch') return;
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

  private animate(time: number): void {
    if (this.disposed) return;
    const delta = this.previous ? Math.min((time - this.previous) / 1000, 0.05) : 0;
    this.previous = time;
    if (this.enabled) {
      const input = new THREE.Vector3(
        Number(this.keys.has('KeyD') || this.keys.has('ArrowRight')) - Number(this.keys.has('KeyA') || this.keys.has('ArrowLeft')) + this.touchMove.x,
        0,
        Number(this.keys.has('KeyS') || this.keys.has('ArrowDown')) - Number(this.keys.has('KeyW') || this.keys.has('ArrowUp')) + this.touchMove.y);
      if (input.lengthSq() > 1) input.normalize();
      input.applyAxisAngle(new THREE.Vector3(0, 1, 0), this.yaw).multiplyScalar(this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 5 : 2.8);
      this.velocity.x = input.x; this.velocity.z = input.z;
      if (this.grounded && this.keys.has('Space')) this.velocity.y = 5;
      this.velocity.y = Math.max(-30, this.velocity.y - 9.8 * delta);
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
      }
      if (this.position.y < this.spawn.y - 100) { this.position.copy(this.spawn); this.velocity.set(0, 0, 0); this.options.onStatus('Returned to spawn after falling outside the world.', 'warning'); }
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
    for (const avatar of [this.self, ...this.avatars.values()]) avatar.children.at(-1)?.quaternion.copy(this.camera.quaternion).premultiply(avatar.quaternion.clone().invert());
    this.renderer.render(this.scene, this.camera);
    this.frame = requestAnimationFrame(next => this.animate(next));
  }

  dispose(): void {
    this.disposed = true; this.enabled = false;
    cancelAnimationFrame(this.frame); this.abort.abort(); this.resizeObserver.disconnect();
    for (const manager of this.loadManagers) manager.abort();
    this.loadManagers.clear();
    if (document.pointerLockElement === this.canvas) document.exitPointerLock();
    for (const object of [...this.objects.values(), ...this.avatars.values(), this.self]) disposeObject(object);
    this.renderer.dispose(); this.canvas.remove();
  }
}
