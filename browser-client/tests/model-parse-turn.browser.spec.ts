// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Genuine FBX/HTML image component proof; no public-world speed or native claim.
import { expect, test } from '@playwright/test';
import { modelFloorFbx } from './fixtures/model-floor';

test('task-scheduled genuine FBX preserves all geometry/material/image data and queued revocation', async ({ page }, testInfo) => {
  let requests = 0;
  await page.route(/^http:\/\/127\.0\.0\.1:\d+\/$/, route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><body></body>' }));
  await page.route('**/parse-turn/*/floor.png', async route => {
    requests++;
    await route.fulfill({ contentType: 'image/png', body: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64') });
  });
  await page.goto('/');
  const result = await page.evaluate(async fbx => {
    const turnPath = '/src/model-parse-turn.ts', worldPath='/src/world.ts', collisionPath='/src/mesh-collision.ts';
    // page.evaluate is serialized outside Vite's import transformation.
    // An ordinary fixture module lets Vite resolve the real package imports.
    const modulesPath='/tests/model-parse-turn-modules.ts';
    const [{ ModelParseTurn }, { BrowserWorld }, { MeshCollision }, THREE, { FBXLoader }] = await Promise.all([
      import(/* @vite-ignore */ turnPath) as Promise<typeof import('../src/model-parse-turn')>,
      import(/* @vite-ignore */ worldPath) as Promise<typeof import('../src/world')>,
      import(/* @vite-ignore */ collisionPath) as Promise<typeof import('../src/mesh-collision')>,
      import(/* @vite-ignore */ modulesPath).then(module => module.THREE) as Promise<typeof import('three')>,
      import(/* @vite-ignore */ modulesPath) as Promise<typeof import('./model-parse-turn-modules')>
    ]);
    const bytes = new TextEncoder().encode(fbx).buffer; const controller = new AbortController(); const owner = new ModelParseTurn(controller.signal);
    const imageEvents: { scheduled: boolean; parsed: number }[] = [];
    let approved=true;
    const actual=BrowserWorld.prototype as unknown as {parseTexturedModel(manager:import('three').LoadingManager,parse:()=>import('three').Object3D,signal:AbortSignal,weight:number):Promise<import('three').Object3D>};
    const context=Object.create(BrowserWorld.prototype);
    Object.assign(context,{abort:controller,disposed:false,modelParseEpoch:new AbortController(),parseTurnCounts:{capacityFallbacks:0},recordLoadPhase(){},options:{modelParseTurn:false,captureAssetAuthority:()=>({generation:'owned-browser-fixture',assertCurrent(){if(!approved)throw new DOMException('Fixture approval revoked','AbortError');}})}});
    const graphs: import('three').Object3D[] = [];
    const dispose = (graph: import('three').Object3D) => graph.traverse(node => {
      if (node instanceof THREE.Mesh) { node.geometry.dispose(); for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
        if ('map' in material) (material.map as import('three').Texture | null)?.dispose(); material.dispose();
      } }
    });
    const snapshot = async (graph: import('three').Object3D) => {
      const records: unknown[] = [];
      graph.traverse(node => {
        if (!(node instanceof THREE.Mesh)) return;
        const attributes = node.geometry.attributes as Record<string, import('three').BufferAttribute>;
        records.push({ index: node.geometry.index ? [...node.geometry.index.array] : null, attributes: Object.fromEntries(Object.entries(attributes).map(([key, value]) => [key, { itemSize: value.itemSize, normalized: value.normalized, array: [...value.array] }])), groups: node.geometry.groups });
        for (const material of Array.isArray(node.material) ? node.material : [node.material]) {
          const map = 'map' in material ? material.map as import('three').Texture | null : null;
          const image = map?.image as HTMLImageElement | undefined;
          if (!image || !image.complete || image.naturalWidth !== 1 || image.naturalHeight !== 1) throw Error('Actual decoded image required');
          const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
          const context = canvas.getContext('2d')!; context.drawImage(image, 0, 0);
          records.push({ side: material.side, opacity: material.opacity, transparent: material.transparent, color: 'color' in material ? (material.color as import('three').Color).toArray() : null, pixels: [...context.getImageData(0, 0, 1, 1).data], wrap: [map!.wrapS, map!.wrapT], uv: [...map!.offset.toArray(), ...map!.repeat.toArray()] });
        }
      });
      if (!records.length) throw Error('Actual parsed mesh required');
      const bounds=new THREE.Box3().setFromObject(graph),size=bounds.getSize(new THREE.Vector3());
      const contact=new THREE.Vector3(bounds.min.x+size.x*.2,bounds.min.y+.85,bounds.min.z+size.z*.2);
      const collision=new MeshCollision(graph);
      try{records.push({actualTriangleSupport:collision.supports(contact),outsideSupport:collision.supports(contact.clone().add(new THREE.Vector3(1000,0,1000)))});}
      finally{collision.dispose();}
      return JSON.stringify(records);
    };
    let resourceOrdinal=0;
    const parse = async (scheduled: boolean) => {
      const manager = new THREE.LoadingManager();
      // Distinct authored dependency URLs exercise twelve real image loads.
      // Reusing one URL lets Three's already-loaded image cache satisfy eleven
      // parsers, which does not prove the asynchronous dependency boundary.
      const resourcePath=location.origin+'/parse-turn/'+resourceOrdinal+++'/';
      manager.onProgress = url => { if (url !== 'browser-internal-model-parse') imageEvents.push({ scheduled, parsed: owner.stats.parsed }); };
      context.options.modelParseTurn=scheduled;context.modelParseTurn=scheduled?owner:undefined;
      const graph = await actual.parseTexturedModel.call(context,manager,
        () => new FBXLoader(manager).parse(bytes, resourcePath),controller.signal,bytes.byteLength);
      graphs.push(graph); return snapshot(graph);
    };
    try {
      const baseline = await Promise.all(Array.from({ length: 6 }, () => parse(false)));
      const prepared = Array.from({ length: 6 }, () => parse(true));
      await Promise.resolve(); const parsedBeforeTask = owner.stats.parsed;
      const scheduled = await Promise.all(prepared);
      const reader = new AbortController(); let cancelledParserCalls = 0;
      const cancelled = owner.run(() => ++cancelledParserCalls, { signal: reader.signal, weight: bytes.byteLength }); reader.abort();
      let cancelledName = ''; try { await cancelled; } catch (error) { cancelledName = (error as Error).name; }
      let revokedParserCalls=0;context.options.modelParseTurn=true;context.modelParseTurn=owner;
      const revoked=actual.parseTexturedModel.call(context,new THREE.LoadingManager(),()=>{revokedParserCalls++;return new FBXLoader().parse(bytes,location.origin+'/parse-turn/');},controller.signal,bytes.byteLength);
      approved=false;let revokedName='';try{await revoked;}catch(error){revokedName=(error as Error).name;}
      return { revokedParserCalls,revokedName,baseline, scheduled, parsedBeforeTask, cancelledName, cancelledParserCalls, stats: owner.stats,
        actualImageCompletionEvents: imageEvents.length,
        // An observation, not a fairness/performance oracle: HTML can select
        // another task source or deliver all images after all six parsers.
        scheduledImagesBeforeLastParse: imageEvents.filter(event => event.scheduled && event.parsed < 6).length };
    } finally { controller.abort(); owner.dispose(); graphs.forEach(dispose); }
  }, modelFloorFbx);
  await testInfo.attach('actual-authored-fbx-parser-observations', {
    body: Buffer.from(JSON.stringify(result)), contentType: 'application/json'
  });
  expect(result.scheduled).toEqual(result.baseline);
  expect(result.baseline.every(record=>JSON.parse(record).some((value:{actualTriangleSupport?:boolean;outsideSupport?:boolean})=>value.actualTriangleSupport===true&&value.outsideSupport===false))).toBe(true);
  expect(result.revokedParserCalls).toBe(0);expect(result.revokedName).toBe('AbortError');
  expect(result.parsedBeforeTask).toBe(0); expect(result.stats.parsed).toBe(6);
  expect(result.stats.queuedBytes).toBe(0); expect(result.stats.taskChannelOpen).toBe(false);
  expect(result.cancelledName).toBe('AbortError'); expect(result.cancelledParserCalls).toBe(0);
  expect(result.actualImageCompletionEvents).toBe(12);
  expect(requests).toBe(12);
});
