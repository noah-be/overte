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
