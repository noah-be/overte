// SPDX-License-Identifier: Apache-2.0
// Copy the fixed repository mannequin into Vite's distributable public directory.
// The reviewed fork mannequin normalizes skin weights; other assets retain the native 2026.04.1 bytes.
import { readFile, mkdir, writeFile, rename } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const client = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const repository = path.dirname(client);
const destination = path.join(client, 'public/default-avatar');
const assets = [
    ['defaultAvatar_full.fst', 2544, '0519e02f2f3d6afe19f680dd824a29f14a3baa65acb06b87ace33b1836717c50'],
    ['mannequin/mannequin.fbx', 3654465, 'b9ca9d23f488bbc579968708895c8d998a0e49a5f24cbfc25157ffaebf14d7a8'],
    ['mannequin/lambert1_Base_Color.png', 1229369, '70b544b69ea325ee03f726694d9392ea8a12ddc66d47559382d142da12b9bdc6'],
    ['mannequin/lambert1_Normal_OpenGL.png', 1177174, 'ead05dbdca83bc70c7546a3bd88ab2d58ccea85fed8f9f19b845cbfcd7b1fc05'],
    ['mannequin/lambert1_Roughness.png', 522873, '2f3c696977e1a8bf888b107f4935c0b3e0dca1bee2540cec8f780228468771a8'],
    ['mannequin/Eyes.png', 22414, 'e8be0da314bfa0e3ad7e0f9d2315dddc38f39510dd421c9edbafc5406086700d'],
];
// Validate the entire fixed set before writing any output. Changes require an explicit
// native compatibility review and manifest update; no network or arbitrary source paths.
const validated = await Promise.all(assets.map(async ([relativePath, bytes, sha256]) => {
    const content = await readFile(path.join(repository, 'interface/resources/meshes', relativePath));
    if (content.length !== bytes || createHash('sha256').update(content).digest('hex') !== sha256) {
        throw new Error(`Default avatar source changed: ${relativePath}. Review the native asset and update the fixed manifest.`);
    }
    return { relativePath, bytes, sha256, content };
}));
await mkdir(destination, { recursive: true });
for (const asset of validated) {
    const output = path.join(destination, asset.relativePath);
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output + '.copy', asset.content);
    await rename(output + '.copy', output);
}
const license = await readFile(path.join(repository, 'LICENSE'), 'utf8');
const apache = await readFile(path.join(repository, 'LICENSES/Apache-2.0.txt'), 'utf8');
await writeFile(path.join(destination, 'LICENSE.txt'), license.trimEnd() + '\n\n' + apache);
await writeFile(path.join(destination, 'manifest.json'), JSON.stringify({
    version: 1,
    source: 'Overte fork default mannequin with normalized skin weights; other assets retain native 2026.04.1 bytes',
    license: 'LICENSE.txt',
    nativeAssetRevision: 'b4e7ddd976ce3e019b781540ed6186a7d31bf1d3',
    nativeAssetModification: 'Normalize skin-cluster weights without changing geometry, joint transforms, materials or textures.',
    assets: validated.map(({ relativePath, bytes, sha256 }) => ({ path: relativePath, bytes, sha256 })),
}, null, 2) + '\n');
console.log('Prepared six verified native default-avatar assets and their license in public/default-avatar/.');
