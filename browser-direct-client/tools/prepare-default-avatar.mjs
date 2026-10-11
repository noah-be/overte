// SPDX-License-Identifier: Apache-2.0
// Modified for Overte direct browser compatibility: retain immutable Woody origin,
// contributor attribution and the repository's reviewed FBX changes in packaged notices.
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
await writeFile(path.join(destination, 'LICENSE.txt'),
    'Original character: Woody. Published by High Fidelity; original contributor Haptic Monkey. Apache-2.0.\n' +
    'Overte removed broken eye-blink blendshape normals from the imported FBX, replacing the previous baked FBX.\n' +
    'The fork FBX normalizes skin weights; the other five assets retain native 2026.04.1 bytes.\n' +
    'Immutable origin, license metadata and import links are recorded in manifest.json.\n\n' +
    license.trimEnd() + '\n\n' + apache);
await writeFile(path.join(destination, 'manifest.json'), JSON.stringify({
    version: 1,
    source: 'Overte fork default mannequin with normalized skin weights; other assets retain native 2026.04.1 bytes',
    license: 'LICENSE.txt',
    nativeAssetRevision: 'b4e7ddd976ce3e019b781540ed6186a7d31bf1d3',
    nativeAssetModification: 'Normalize skin-cluster weights without changing geometry, joint transforms, materials or textures.',
    originalCharacter: 'Woody',
    attribution: { publisher: 'High Fidelity', originalContributor: 'Haptic Monkey', license: 'Apache-2.0' },
    immutableProvenance: {
        licenseMetadata: 'https://raw.githubusercontent.com/overte-org/overte-content/ed9ac884c274990210f6c62fed7f5e8837d170aa/Bazaar/Avatars/woody/resource.json',
        packageMetadata: 'https://raw.githubusercontent.com/overte-org/overte-content/095127bbdee8311e3f06349cf3d450dd3e1c3a28/Bazaar/Avatars/woody/package.json.backup',
        repositoryImport: 'https://github.com/overte-org/overte/commit/e8d79cfb9baa38cd7a8f4f63d509330b9c306f1b',
        repositoryModification: 'Removed broken eye-blink blendshape normals from the imported FBX, replacing the previous baked FBX. The fork subsequently normalized skin-cluster weights in b4e7ddd976ce3e019b781540ed6186a7d31bf1d3; bundled bytes are verified fork resources, not claimed identical to the hosted original or the 2026.04.1 FBX.'
    },
    assets: validated.map(({ relativePath, bytes, sha256 }) => ({ path: relativePath, bytes, sha256 })),
}, null, 2) + '\n');
console.log('Prepared six verified native default-avatar assets and their license in public/default-avatar/.');
