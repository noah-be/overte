// SPDX-License-Identifier: Apache-2.0
import * as THREE from 'three';
import { BrowserWorld } from '../src/world';

type Cull = 'CULL_BACK' | 'CULL_FRONT' | 'CULL_NONE' | null;
interface Input { url: string; cull: Cull; unlit?: boolean; lightZ?: -1 | 1 }
/** Generated native-readable asset, loaded and material-overridden through the
 * real World. Controlled lighting/camera are fixture state, never a mutation
 * of loaded geometry/materials to manufacture the expected pixel result. */
export async function auditWorldNativeCull(input: Input) {
  const host = document.createElement('div'); host.style.cssText = 'position:fixed;left:0;top:0;width:512px;height:384px;'; document.body.append(host);
  const warnings: string[] = [];
  const world = new BrowserWorld(host, { nativeCullDefaults: true, resolveAsset: url => url,
    onPose() {}, onInteract() {}, onStatus(message, kind) { if (kind === 'warning' || kind === 'error') warnings.push(message); } });
  // Freeze presentation while loaders, classification and actual shader warmup
  // finish. No physics or moving visitor camera is needed for this pixel audit.
  world.setPresentationEnabled(false);
  const internal = world as unknown as {
    camera: THREE.PerspectiveCamera; renderer: THREE.WebGLRenderer;
    objects: Map<string, THREE.Group>; nativeWinding: WeakMap<THREE.Group, {convertedMeshes: number}>;
  };
  const gl = internal.renderer.getContext();
  if (!(gl instanceof WebGL2RenderingContext)) throw Error('Actual WebGL2 backend is required');
  try {
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.z = (input.lightZ ?? -1) * -100;
    for (const child of [...world.scene.children]) if (child instanceof THREE.Light) world.scene.remove(child);
    world.scene.add(light, light.target); world.scene.background = new THREE.Color(0);
    const data = { name: 'authored-face-rgb', model: 'hifi_pbr', unlit: input.unlit ?? true, albedo: [1, 1, 1],
      ...(input.cull === null ? {} : { cullFaceMode: input.cull }) };
    world.setEntities([
      { id: 'model', type: 'Model', modelURL: new URL(input.url,location.href).href, dimensions: { x: 5, y: 2, z: .1 }, position: { x: 0, y: 0, z: 0 }, collisionless: true },
      { id: 'material', type: 'Material', parentID: 'model', parentMaterialName: '0', materialData: JSON.stringify({materials: data}) },
    ]);
    const deadline = performance.now() + 15000; let ready = false;
    while (performance.now() < deadline) {
      const root = internal.objects.get('model');
      if(root?.userData.modelFailed)throw Error(warnings.join('; ') || 'Actual World model loading failed');
      const installed: THREE.Mesh[] = [];
      root?.traverse(object => { if (object instanceof THREE.Mesh && object.geometry.getAttribute('position')?.count === 6) installed.push(object); });
      if (root?.userData.shadersReady === true && world.getPerformance().compilingGraphics === 0 && world.getPerformance().loadedModels === 1
        && internal.nativeWinding.get(root)?.convertedMeshes === 1 && installed.length === 2
        && installed.every(mesh => !Array.isArray(mesh.material) && mesh.material.name === 'authored-face-rgb')) { ready = true; break; }
      await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
    }
    const root = internal.objects.get('model');
    if (!ready || !root?.userData.shadersReady || world.getPerformance().loadedModels !== 1) throw Error('Actual World model/material warmup did not complete');
    if (warnings.length) throw Error(warnings.join('; '));
    const scope = internal.nativeWinding.get(root); if (!scope || scope.convertedMeshes !== 1) throw Error('Actual World did not compensate its one mirrored node');
    internal.camera.position.set(0, 0, 4); internal.camera.quaternion.set(0, 0, 0, 1); internal.camera.updateMatrixWorld();
    const meshes: THREE.Mesh[] = [];
    root.traverse(object => { if (object instanceof THREE.Mesh && object.geometry.getAttribute('position')?.count === 6) meshes.push(object); });
    if (meshes.length !== 2) throw Error('Actual loaded positive/mirrored meshes are required');
    const materials = meshes.map(mesh => mesh.material as THREE.Material), versions = materials.map(material => material.version);
    const programs = internal.renderer.info.programs?.length, calls: number[] = [];
    for (let frame = 0; frame < 20; frame++) { internal.renderer.render(world.scene, internal.camera); calls.push(internal.renderer.info.render.calls); }
    const pixels = [-1.5, 1.5].map(x => {
      const point = new THREE.Vector3(x, 0, .05).project(internal.camera), pixel = new Uint8Array(4);
      gl.readPixels(Math.floor((point.x * .5 + .5) * gl.drawingBufferWidth), Math.floor((point.y * .5 + .5) * gl.drawingBufferHeight), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
      return [...pixel];
    });
    return { webgl2: true, pixels, calls, sides: materials.map(material => material.side), vertexColors: materials.map(material => material.vertexColors),
      convertedMeshes: scope.convertedMeshes, versionsStable: JSON.stringify(versions) === JSON.stringify(materials.map(material => material.version)),
      programsStable: programs === internal.renderer.info.programs?.length, warnings };
  } finally { world.dispose(); internal.renderer.forceContextLoss(); host.remove(); }
}
