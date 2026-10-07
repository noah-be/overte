// SPDX-License-Identifier: Apache-2.0
// Focused real Google codec test; generated geometry is not a public-world proof.
import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import draco from 'draco3d';
const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const origin = 'http://127.0.0.1:5180';
const output = path.join(repo, 'build/browser-hub-lab/decoder');
const report = { startedAt: new Date().toISOString(), completed: false, syntheticGeometry: true, nativeWorldProof: false, codec: 'draco3d 1.3.4' };
const positions = [0, 0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 0, 3, 0, 0, 2, 1, 0], original = [2, 0, 1, 0, 2, 1];
function encoded(invalid = false) {
    const module = draco.createEncoderModule({}), mesh = new module.Mesh(), builder = new module.MeshBuilder(), encoder = new module.Encoder(), result = new module.DracoInt8Array();
    try {
        builder.AddFacesToMesh(mesh, 2, new Uint32Array([0, 1, 2, 3, 4, 5]));
        builder.AddFloatAttributeToMesh(mesh, module.POSITION, 6, 3, new Float32Array(positions));
        // The unmodified JS encoder assigns unique IDs consecutively. Native
        // Overte sets 1002 explicitly; filler constant attributes produce that
        // exact unique ID without patching encoded bytes or Google APIs.
        for (let id = 1; id < 1002; id++) builder.AddInt32AttributeToMesh(mesh, module.GENERIC, 6, 1, new Int32Array(6));
        builder.AddInt32AttributeToMesh(mesh, module.GENERIC, 6, 1, new Int32Array(invalid ? [2, -1, 1, 0, 2, 1] : original));
        encoder.SetSpeedOptions(10, 10);
        const count = encoder.EncodeMeshToDracoBuffer(mesh, result);
        assert(count > 0);
        return Uint8Array.from({ length: count }, (_, index) => result.GetValue(index)).buffer;
    } finally { for (const value of [result, encoder, builder, mesh]) module.destroy(value); }
}
let vite, browser;
try {
    try { await fetch(origin, { signal: AbortSignal.timeout(300) }); throw Error('Refusing to reuse an unowned test port'); }
    catch (error) { if (error.message === 'Refusing to reuse an unowned test port') throw error; }
    vite = spawn(process.execPath, ['node_modules/vite/bin/vite.js', '--host', '127.0.0.1', '--port', '5180', '--strictPort'], { cwd: path.join(repo, 'browser-client'), stdio: 'ignore' });
    for (let i = 0; i < 50; i++) { try { if ((await fetch(origin)).ok) break; } catch {} await new Promise(resolve => setTimeout(resolve, 100)); }
    browser = await chromium.launch({ headless: true, args: ['--use-angle=swiftshader', '--disable-dev-shm-usage'] });
    report.browserVersion = browser.version();
    const page = await browser.newPage();
    const valid = encoded(), invalid = encoded(true);
    await page.route(`${origin}/index-valid.drc`, route => route.fulfill({ body: Buffer.from(valid) }));
    await page.route(`${origin}/index-invalid.drc`, route => route.fulfill({ body: Buffer.from(invalid) }));
    await page.goto(origin);
    report.result = await page.evaluate(async () => {
        const { decodeLegacyBakedDraco, disposeLegacyBakedDraco } = await import('/src/baked-draco-legacy.ts');
        const options = { originalIndices: true, materialIDs: false, uv1: false };
        try {
            const mesh = await decodeLegacyBakedDraco(await (await fetch('/index-valid.drc')).arrayBuffer(), options);
            const points = Array.from({ length: mesh.positions.length / 3 }, (_, index) => ({ position: Array.from(mesh.positions).slice(index * 3, index * 3 + 3), original: mesh.originalIndices?.[index] }));
            let invalidRejected = false;
            try { await decodeLegacyBakedDraco(await (await fetch('/index-invalid.drc')).arrayBuffer(), options); }
            catch (error) { invalidRejected = String(error.message).includes('original index'); }
            return { points, integerAttributeType: mesh.originalIndices?.constructor.name, triangles: mesh.indices.length / 3, invalidRejected };
        } finally { disposeLegacyBakedDraco(); }
    });
    assert.equal(report.result.integerAttributeType, 'Uint32Array');
    assert.equal(report.result.points.length, 6);
    assert.equal(report.result.triangles, 2);
    const expected = new Map(original.map((index, at) => [positions.slice(at * 3, at * 3 + 3).join(','), index]));
    for (const point of report.result.points) assert.equal(point.original, expected.get(point.position.join(',')));
    assert.equal(report.result.invalidRejected, true);
    report.completed = true;
} catch (error) { report.error = error.message; process.exitCode = 1; }
finally {
    await browser?.close();
    if (vite) { vite.kill('SIGTERM'); await new Promise(resolve => vite.exitCode !== null ? resolve() : vite.once('exit', resolve)); }
    report.finishedAt = new Date().toISOString();
    await mkdir(output, { recursive: true }); await writeFile(path.join(output, 'baked-draco-original-index.json'), JSON.stringify(report, null, 2) + '\n');
    console.log(JSON.stringify(report));
}
