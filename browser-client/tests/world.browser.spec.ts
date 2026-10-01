// SPDX-License-Identifier: Apache-2.0
// These are renderer component checks using synthetic entities, not domain-compatibility evidence.
import { expect, test } from '@playwright/test';
import type { Page } from '@playwright/test';

async function centerPixel(page: Page): Promise<number[]> {
  const screenshot = await page.locator('#renderer-test canvas').screenshot();
  return page.evaluate(async base64 => {
    const image = await createImageBitmap(await (await fetch(`data:image/png;base64,${base64}`)).blob());
    const canvas = document.createElement('canvas'); canvas.width = image.width; canvas.height = image.height;
    const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0);
    const result = [...context.getImageData(image.width / 2, image.height / 2, 1, 1).data];
    image.close(); return result;
  }, screenshot.toString('base64'));
}

test.beforeEach(async ({ page }) => {
  // Do not initialize the application/session controller for component tests.
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body></body></html>' }));
  await page.goto('/');
  await page.evaluate(async () => {
    const modulePath = '/src/world.ts';
    const { BrowserWorld } = await import(/* @vite-ignore */ modulePath);
    document.body.innerHTML = '<div id="renderer-test" style="width:800px;height:600px"></div>';
    const state = window as unknown as { world: InstanceType<typeof BrowserWorld>; statuses: string[]; selected: string[]; poses: unknown[]; assetResolver?: (url: string) => string };
    state.statuses = []; state.selected = []; state.poses = [];
    state.world = new BrowserWorld(document.getElementById('renderer-test')!, {
      resolveAsset: (url: string) => state.assetResolver ? state.assetResolver(url) : url,
      onPose: (pose: unknown) => state.poses.push(pose),
      onInteract: (entity: { id: string }) => state.selected.push(entity.id),
      onStatus: (message: string) => state.statuses.push(message),
    });
    state.world.setSpawn({ x: 0, y: 0.85, z: 0 });
    state.world.setEntities([
      { id: 'floor', type: 'Box', position: { x: 0, y: -0.5, z: 0 }, dimensions: { x: 30, y: 1, z: 30 } },
      { id: 'wall', type: 'Box', position: { x: 0, y: 1.5, z: -3 }, dimensions: { x: 5, y: 3, z: 0.2 }, color: { red: 220, green: 70, blue: 30 } },
    ]);
    state.world.setEnabled(true);
  });
  const backend = await page.evaluate(() => {
    const renderer = (window as any).world.renderer;
    const context = renderer.getContext();
    return {webgl2:context instanceof WebGL2RenderingContext, version:context.getParameter(context.VERSION)};
  });
  expect(backend.webgl2).toBe(true);
  expect(backend.version).toContain('WebGL 2.0');
});

test.afterEach(async ({ page }) => {
  await page.evaluate(() => (window as unknown as { world?: { dispose(): void } }).world?.dispose());
});

test('rendered entity is picked, floor supports walking and wall blocks it', async ({ page }) => {
  await expect(page.locator('#renderer-test canvas')).toBeVisible();
  await page.waitForTimeout(150);
  await page.evaluate(() => (window as any).world.interact());
  expect(await page.evaluate(() => (window as any).selected)).toEqual(['wall']);
  await page.keyboard.down('KeyW');
  await page.waitForTimeout(500);
  await page.evaluate(() => (window as any).world.setEnabled(true));
  try {
    // Software rendering may run below real time: wait for the actual wall collision.
    await expect.poll(() => page.evaluate(() => (window as any).world.getPose().position.z)).toBeCloseTo(-2.62, 3);
    // Keep the key held until the collision also stops forward velocity.
    await expect.poll(() => page.evaluate(() => (window as any).world.getPose().velocity.z)).toBeCloseTo(0, 3);
  } finally {
    await page.keyboard.up('KeyW');
  }
  const pose = await page.evaluate(() => (window as any).world.getPose());
  const wire = await page.evaluate(() => JSON.parse(JSON.stringify((window as any).world.getPose())));
  expect(wire.orientation).toEqual({ x: 0, y: 0, z: 0, w: 1 });
  expect(pose.position.z).toBeGreaterThan(-2.621);
  expect(pose.position.z).toBeLessThan(-2.5);
  expect(pose.position.y).toBeCloseTo(0.85, 2);
  await page.evaluate(() => (window as any).world.setEntities([]));
  await page.waitForTimeout(50);
  await page.evaluate(() => (window as any).world.interact());
  expect(await page.evaluate(() => (window as any).selected)).toEqual(['wall']);
  expect(await page.evaluate(() => (window as any).statuses.at(-1))).toContain('No object');
});

test('repeated closed Tablet states preserve a held world movement key', async ({ page }) => {
  const before = await page.evaluate(() => (window as any).world.getPose().position.x);
  await page.keyboard.down('KeyD');
  try {
    // Ordinary native Tablet refreshes repeatedly report the same closed state.
    // They must not synthesize key release during an otherwise continuous walk.
    await page.evaluate(() => {
      const proof = window as any;
      proof.repeatClosedTablet = window.setInterval(() => proof.world.setInputEnabled(true), 16);
    });
    await expect.poll(async () => await page.evaluate(() => (window as any).world.getPose().position.x) - before,
      {timeout:10000}).toBeGreaterThan(0.6);
  } finally {
    await page.keyboard.up('KeyD');
    await page.evaluate(() => window.clearInterval((window as any).repeatClosedTablet));
  }
});

test('unsupported entity is explained and reconnect clears stale geometry', async ({ page }) => {
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setEntities([{ id: 'web', type: 'Web', name: 'Old web panel' }]);
    world.setEnabled(false);
    world.setAvatars([]);
    world.setEntities([]);
    world.setEnabled(true);
    world.setSpawn({ x: 0, y: 1, z: 0 });
  });
  expect(await page.evaluate(() => (window as any).statuses)).toContain('Old web panel: Web rendering is not supported by this first version.');
  await page.waitForTimeout(100);
  await page.evaluate(() => (window as any).world.interact());
  expect(await page.evaluate(() => (window as any).selected)).toEqual([]);
});

test('steep upward look in avatar view keeps the camera above the actual floor', async ({ page }) => {
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setEntities([{ id: 'floor', type: 'Box', position: { x: 0, y: -0.25, z: 0 }, dimensions: { x: 20, y: 0.5, z: 20 } }]);
    world.setSpawn({ x: 0, y: 0.85, z: 0 }, { x: Math.sin(0.7), y: 0, z: 0, w: Math.cos(0.7) });
    window.dispatchEvent(new KeyboardEvent('keydown', { code: 'KeyV' }));
    window.dispatchEvent(new KeyboardEvent('keyup', { code: 'KeyV' }));
  });
  await expect.poll(() => page.evaluate(() => (window as any).world.camera.position.y)).toBeCloseTo(0.08, 2);
  const pixel = await centerPixel(page);
  expect(pixel[2]).toBeGreaterThan(150);
  expect(pixel[2]).toBeGreaterThan(pixel[0]);
  expect(await page.evaluate(() => (window as any).world.getPose().position.y)).toBeCloseTo(0.85, 2);
});

test('other participants are rendered at received positions and removed on departure', async ({ page }) => {
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setEnabled(false); world.setEntities([]); world.setLocalAvatar('self');
    world.setAvatars([
      { id: 'self', displayName: 'Own native bridge', position: { x: 0, y: 0.85, z: -1 } },
      { id: 'peer', displayName: 'Native participant', position: { x: 0, y: 0.85, z: -3 } },
    ]);
  });
  await page.waitForTimeout(50);
  const visible = await centerPixel(page);
  expect(visible[0]).toBeGreaterThan(150);
  expect(visible[0]).toBeGreaterThan(visible[2]);
  await page.evaluate(() => (window as any).world.setAvatars([{ id: 'peer', position: { x: 3, y: 0.85, z: -3 } }]));
  await page.waitForTimeout(50);
  const moved = await centerPixel(page);
  expect(moved[0]).toBeLessThan(100);
  await page.evaluate(() => (window as any).world.setAvatars([]));
  await page.waitForTimeout(50);
  expect(await centerPixel(page)).toEqual(moved);
});

test('the original native mannequin renders skinned geometry and applies live named joint poses', async({page}) => {
  await page.evaluate(async() => {
    const path = '/src/default-avatar.ts', {defaultAvatarAsset} = await import(path);
    (window as any).assetResolver = (url:string) => defaultAvatarAsset(url,window.location.href) || url;
    const world = (window as any).world;
    world.setEnabled(false); world.setEntities([]); world.setLocalAvatar('self');
    world.setAvatars([{id:'peer',position:{x:0,y:.85,z:-3},skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst'}]);
  });
  await expect.poll(() => page.evaluate(() => (window as any).world.getPerformance().loadedAvatars)).toBe(1);
  const rest = await page.evaluate(() => {
    const root = (window as any).world.avatars.get('peer'); const skins:any[] = [], bones:any[] = [];
    root.traverse((object:any) => {if (object.isSkinnedMesh) skins.push(object); if (object.isBone && object.name === 'Head') bones.push(object);});
    return {skins:skins.length,head: bones.map(bone => ({position:bone.position.toArray(),rotation:bone.quaternion.toArray(),parent:bone.parent.name}))};
  });
  expect(rest.skins).toBe(2); expect(rest.head.length).toBeGreaterThan(0);
  await expect.poll(async() => {const pixel = await centerPixel(page);return Math.max(...pixel.slice(0,3));}).toBeGreaterThan(100);
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setAvatars([{id:'peer',position:{x:0,y:.85,z:-3},skeletonModelURL:'qrc:////meshes/defaultAvatar_full.fst',
      jointNames:['body','face','Head'],jointRotations:[{x:0,y:0,z:0,w:1},{x:0,y:0,z:0,w:1},{x:0,y:Math.sin(.4),z:0,w:Math.cos(.4)}]}]);
  });
  const posed = await page.evaluate(() => {
    const bones:any[] = []; (window as any).world.avatars.get('peer').traverse((object:any) => {if(object.isBone && object.name === 'Head') bones.push(object);});
    return bones.map(bone => ({position:bone.position.toArray(),rotation:bone.quaternion.toArray(),parent:bone.parent.name}));
  });
  const canonical = posed.filter(bone => bone.parent !== 'Head'), bindings = posed.filter(bone => bone.parent === 'Head');
  expect(canonical.length).toBeGreaterThan(0);
  for (const bone of canonical) expect(bone.rotation[1]).toBeCloseTo(Math.sin(.4),5);
  for (const bone of bindings) expect(bone.rotation).toEqual([0,0,0,1]);
  expect(posed.map(bone => bone.position)).toEqual(rest.head.map(bone => bone.position));
  await page.evaluate(() => (window as any).world.setAvatars([]));
  expect(await page.evaluate(() => (window as any).world.getPerformance().loadedAvatars)).toBe(0);
});

test('native Material data overrides primitive surfaces and survives parent updates', async ({ page }) => {
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setEnabled(false);
    const box = { id: 'box', type: 'Box', position: { x: 0, y: 1.5, z: -3 }, dimensions: { x: 2, y: 2, z: 0.1 }, color: { red: 255, green: 0, blue: 0 } };
    const material = { id: 'material', type: 'Material', parentID: 'box', materialURL: 'materialData', materialData: JSON.stringify({ materials: { albedo: [0, 0, 1], roughness: 0.4, metallic: 0.1, unlit: true } }) };
    (window as any).materialFixture = { box, material };
    world.setEntities([box, material]);
  });
  await page.waitForTimeout(100);
  const pixel = await centerPixel(page);
  expect(pixel[2]).toBeGreaterThan(150);
  expect(pixel[2]).toBeGreaterThan(pixel[0] * 2);
  await page.evaluate(() => {
    const { box, material } = (window as any).materialFixture;
    (window as any).world.setEntities([{ ...box, color: { red: 0, green: 255, blue: 0 } }, material]);
  });
  await page.waitForTimeout(100);
  expect(await centerPixel(page)).toEqual(pixel);
  await page.evaluate(() => (window as any).world.removeEntities(['material']));
  await expect.poll(async() => (await centerPixel(page))[1]).toBeGreaterThan(150);
  const restored = await centerPixel(page);
  expect(restored[1]).toBeGreaterThan(restored[2] * 2);
});

test('defined skybox, haze and custom material shaders show warnings while basic geometry remains usable', async ({ page }) => {
  await page.evaluate(() => {
    const world = (window as any).world;
    world.setEnabled(false);
    world.setEntities([
      { id: 'box', type: 'Box', position: { x: 0, y: 1.5, z: -3 }, dimensions: { x: 2, y: 2, z: 0.1 } },
      { id: 'material', type: 'Material', parentID: 'box', materialURL: 'materialData', materialData: JSON.stringify({ materials: { model: 'hifi_shader_simple', procedural: { fragmentShaderURL: 'https://example.test/unused.fs' }, albedo: [0, 1, 0], unlit: true } }) },
      { id: 'zone', type: 'Zone', name: 'Sky zone', skyboxMode: 'enabled', hazeMode: 'enabled' },
      { id: 'plain-zone', type: 'Zone', name: 'Plain zone', skyboxMode: 'inherit', hazeMode: 'disabled' },
    ]);
  });
  await expect.poll(() => page.evaluate(() => (window as any).statuses)).toContain('Sky zone: zone skybox and zone haze effects are not supported. Basic world rendering remains available.');
  expect(await page.evaluate(() => (window as any).statuses)).toContain('Custom shader or toon materials are not supported. Basic material colors and textures are used instead.');
  expect(await page.evaluate(() => (window as any).statuses.some((message: string) => message.includes('Plain zone')))).toBe(false);
  const pixel = await centerPixel(page);
  expect(pixel[1]).toBeGreaterThan(150);
  expect(pixel[1]).toBeGreaterThan(pixel[0] * 2);
  await page.evaluate(() => (window as any).world.interact());
  expect(await page.evaluate(() => (window as any).selected)).toEqual(['box']);
});

for (const source of ['https://assets.example.test/models/triangle.gltf', 'atp:/models/triangle.gltf']) {
test(`glTF geometry and texture render through rewritten ${source.split(':')[0]} asset dependencies`, async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()); });
  const positions = Buffer.from(new Float32Array([-0.5, -0.5, 0, 0.5, -0.5, 0, 0, 0.5, 0, 0, 0, 1, 0, 0.5, 1]).buffer);
  const gltf = {
    asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0, TEXCOORD_0: 1 }, material: 0 }] }],
    buffers: [{ byteLength: positions.length, uri: 'triangle.bin' }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36 }, { buffer: 0, byteOffset: 36, byteLength: 24 }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0] }, { bufferView: 1, componentType: 5126, count: 3, type: 'VEC2' }],
    materials: [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 }, metallicFactor: 0, roughnessFactor: 1 }, doubleSided: true }],
    textures: [{ source: 0 }], images: [{ uri: 'color.png' }],
  };
  const requested: string[] = [];
  await page.route('**/test-assets/proxy?*', async route => {
    const url = new URL(route.request().url()).searchParams.get('source')!;
    requested.push(url);
    if (url.endsWith('triangle.gltf')) await route.fulfill({ contentType: 'model/gltf+json', body: JSON.stringify(gltf) });
    else if (url.endsWith('triangle.bin')) await route.fulfill({ contentType: 'application/octet-stream', body: positions });
    else await route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==', 'base64') });
  });
  await page.evaluate(source => {
    (window as any).assetResolver = (url: string) => `${location.origin}/test-assets/proxy?source=${encodeURIComponent(url)}`;
    (window as any).world.setEnabled(false);
    (window as any).world.setEntities([{ id: 'model', type: 'Model', name: 'Test model', modelURL: source, position: { x: 0, y: 1.5, z: -3 }, dimensions: { x: 2, y: 2, z: 0.1 } }]);
  }, source);
  await expect.poll(() => page.evaluate(() => (window as any).statuses)).toContain('Loaded Test model');
  expect(requested).toContain(source.replace('triangle.gltf', 'triangle.bin'));
  expect(requested).toContain(source.replace('triangle.gltf', 'color.png'));
  expect(consoleErrors).toEqual([]);
  const pixel = await centerPixel(page);
  expect(pixel[1]).toBeGreaterThan(100);
  expect(pixel[1]).toBeGreaterThan(pixel[0] * 2);
  await page.evaluate(() => (window as any).world.interact());
  expect(await page.evaluate(() => (window as any).selected)).toEqual(['model']);
});
}

test('baked FST material mappings resolve metadata to the actual original texture', async ({ page }) => {
  const requested: string[] = [];
  await page.route('**/test-assets/proxy?*', async route => {
    const source = new URL(route.request().url()).searchParams.get('source')!;
    requested.push(source);
    if (source.endsWith('surface.baked.fst')) await route.fulfill({ body: 'filename = surface.obj\nmaterialMap = [{"mat::Wood":"surface.baked.json#Wood"}]\n' });
    else if (source.endsWith('surface.obj')) await route.fulfill({ body: 'v -0.5 -0.5 0\nv 0.5 -0.5 0\nv 0.5 0.5 0\nv -0.5 0.5 0\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nusemtl Wood\nf 1/1 2/2 3/3\nf 1/1 3/3 4/4\n' });
    else if (source.includes('surface.baked.json')) await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ materials: { model: 'hifi_pbr', name: 'Wood', unlit: true, albedo: { red: 1, green: 1, blue: 1 }, albedoMap: 'textures/wood.texmeta.json' } }) });
    else if (source.endsWith('wood.texmeta.json')) await route.fulfill({ contentType: 'application/json', body: JSON.stringify({ original: 'wood.png', compressed: { DXT1: 'wood.ktx' } }) });
    else if (source.endsWith('wood.png')) await route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGNk+M/AwMDAxMDAwMDAAAAMHgEDBINhkwAAAABJRU5ErkJggg==', 'base64') });
    else await route.fulfill({ status: 404, body: 'Unexpected dependency' });
  });
  await page.evaluate(() => {
    (window as any).assetResolver = (url: string) => `${location.origin}/test-assets/proxy?source=${encodeURIComponent(url)}`;
    (window as any).world.setEnabled(false);
    (window as any).world.setEntities([{ id: 'baked', type: 'Model', name: 'Baked surface', modelURL: 'https://assets.example.test/models/surface.baked.fst', position: { x: 0, y: 1.5, z: -3 }, dimensions: { x: 2, y: 2, z: 0.1 } }]);
  });
  await expect.poll(() => page.evaluate(() => (window as any).statuses)).toContain('Loaded Baked surface');
  expect(requested).toContain('https://assets.example.test/models/textures/wood.png');
  expect(requested.some(source => source.endsWith('.ktx'))).toBe(false);
  const pixel = await centerPixel(page);
  expect(pixel[1]).toBeGreaterThan(150);
  expect(pixel[1]).toBeGreaterThan(pixel[0] * 2);
});

test('cyclic FST mappings fail explicitly and do not occupy the loading queue forever', async ({ page }) => {
  let requests = 0;
  await page.route('**/test-assets/cycle.fst', async route => {
    requests++; await route.fulfill({ body: 'filename = cycle.fst\n' });
  });
  await page.evaluate(() => {
    (window as any).world.setEntities([{ id: 'cycle', type: 'Model', name: 'Cyclic mapping', modelURL: `${location.origin}/test-assets/cycle.fst` }]);
  });
  await expect.poll(() => page.evaluate(() => (window as any).statuses.join('\n'))).toContain('mapping contains a cycle');
  expect(requests).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).world.getPerformance().loadingModels)).toBe(0);
});

test('Tablet input focus pauses world movement while gravity and pose replication continue', async ({ page }) => {
  await page.evaluate(() => (window as any).world.setInputEnabled(false));
  const before = await page.evaluate(() => (window as any).world.getPose().position);
  await page.keyboard.down('KeyW'); await page.waitForTimeout(500); await page.keyboard.up('KeyW');
  const after = await page.evaluate(() => (window as any).world.getPose().position);
  expect(after.z).toBeCloseTo(before.z, 5);
  expect(after.y).toBeCloseTo(0.85, 2);
  expect(await page.evaluate(() => (window as any).poses.length)).toBeGreaterThan(0);
  await page.evaluate(() => (window as any).world.setInputEnabled(true));
  await page.keyboard.down('KeyW');
  try { await expect.poll(() => page.evaluate(() => (window as any).world.getPose().position.z)).toBeLessThan(before.z - 0.4); }
  finally { await page.keyboard.up('KeyW'); }
});

test('Snap captures actual local WebGL pixels while the Tablet covers rendering, and refuses ended worlds', async ({ page }) => {
  await page.waitForTimeout(100);
  const result = await page.evaluate(async () => {
    const world = (window as any).world;
    world.setPresentationEnabled(false);
    const before = world.getPerformance().renderedFrames;
    const blob = await world.captureScene();
    const bitmap = await createImageBitmap(blob);
    const canvas = document.createElement('canvas'); canvas.width = bitmap.width; canvas.height = bitmap.height;
    const context = canvas.getContext('2d')!; context.drawImage(bitmap, 0, 0);
    const pixel = [...context.getImageData(bitmap.width / 2, bitmap.height / 2, 1, 1).data];
    bitmap.close();
    world.setEnabled(false);
    let ended = '';
    try { await world.captureScene(); } catch (error) { ended = String(error); }
    return { mime: blob.type, width: canvas.width, height: canvas.height, pixel,
      coveredFrames: world.getPerformance().renderedFrames - before, ended };
  });
  expect(result.mime).toBe('image/png');
  expect(result.width).toBeGreaterThanOrEqual(800); expect(result.height).toBeGreaterThanOrEqual(600);
  expect(result.pixel[0]).toBeGreaterThan(result.pixel[2] * 2);
  expect(result.pixel[3]).toBe(255);
  expect(result.coveredFrames).toBe(0);
  expect(result.ended).toContain('Join a world');
});

test('model authoring lights cannot alter domain lighting or churn shader variants', async ({ page }) => {
  const positions = Buffer.from(new Float32Array([-0.5, -0.5, 0, 0.5, -0.5, 0, 0, 0.5, 0]).buffer);
  const gltf = {
    asset: { version: '2.0' }, extensionsUsed: ['KHR_lights_punctual'],
    extensions: { KHR_lights_punctual: { lights: [{ type: 'directional', color: [0, 0, 1], intensity: 100 }] } },
    scene: 0, scenes: [{ nodes: [0, 1] }], nodes: [{ mesh: 0 }, { extensions: { KHR_lights_punctual: { light: 0 } } }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, material: 0 }] }],
    buffers: [{ byteLength: positions.length, uri: `data:application/octet-stream;base64,${positions.toString('base64')}` }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.length }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [-0.5, -0.5, 0], max: [0.5, 0.5, 0] }],
    materials: [{ pbrMetallicRoughness: { baseColorFactor: [1, 0.1, 0.05, 1], metallicFactor: 0, roughnessFactor: 1 } }],
  };
  await page.route('**/test-assets/authoring.gltf', route => route.fulfill({ contentType: 'model/gltf+json', body: JSON.stringify(gltf) }));
  await expect.poll(() => page.evaluate(() => (window as any).world.getPerformance().compilingGraphics)).toBe(0);
  const initialLights = await page.evaluate(() => { let count = 0; (window as any).world.scene.traverseVisible((object: any) => { if (object.isLight) count++; }); return count; });
  let firstPrograms = 0;
  for (let index = 0; index < 3; index++) {
    await page.evaluate(index => {
      const world = (window as any).world;
      world.setEnabled(false);
      world.upsertEntities([{ id: `authoring-${index}`, type: 'Model', modelURL: `${location.origin}/test-assets/authoring.gltf`, position: { x: index * 4, y: 1.5, z: -3 }, dimensions: { x: 2, y: 2, z: 0.1 } }]);
    }, index);
    await expect.poll(() => page.evaluate(() => (window as any).world.getPerformance().loadedModels)).toBe(index + 1);
    await expect.poll(() => page.evaluate(() => (window as any).world.getPerformance().compilingGraphics)).toBe(0);
    await expect.poll(() => page.evaluate(() => { let count = 0; (window as any).world.scene.traverseVisible((object: any) => { if (object.isLight) count++; }); return count; })).toBe(initialLights);
    const programs = await page.evaluate(() => (window as any).world.renderer.info.programs.length);
    if (index === 0) firstPrograms = programs;
    else expect(programs).toBe(firstPrograms);
  }
  const pixel = await centerPixel(page);
  expect(pixel[0]).toBeGreaterThan(pixel[2] * 2);
});
