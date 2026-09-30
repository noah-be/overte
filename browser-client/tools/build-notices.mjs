// SPDX-License-Identifier: Apache-2.0
// Generate distributable browser notices without requiring network access at build time.
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const threeRoot = path.join(root, 'node_modules/three');
const threePackage = JSON.parse(await readFile(path.join(threeRoot, 'package.json'), 'utf8'));
const threeLicense = await readFile(path.join(threeRoot, 'LICENSE'), 'utf8');
const fflateSource = await readFile(path.join(threeRoot, 'examples/jsm/libs/fflate.module.js'), 'utf8');

// Three.js vendors fflate without its separate LICENSE file. Preserve the complete notice from
// https://raw.githubusercontent.com/101arrowz/fflate/v0.8.2/LICENSE (reviewed 2026-09-30).
const fflateVersion = '0.8.2';
if (!new RegExp(`^version ${fflateVersion.replaceAll('.', '\\.')}\\s*$`, 'm').test(fflateSource)) {
    throw new Error('The vendored fflate version changed. Review and update its full license notice before building.');
}
if (!threeLicense.includes('Permission is hereby granted') || !threeLicense.includes('THE SOFTWARE IS PROVIDED')) {
    throw new Error('The installed Three.js license is missing or incomplete.');
}
const fflateLicense = `MIT License

Copyright (c) 2023 Arjun Barrett

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
`;

const notices = `Third-party notices for the Overte browser distribution

This file accompanies the browser JavaScript bundles. Keep it with the deployed dist/ files.

Three.js ${threePackage.version}
https://github.com/mrdoob/three.js
Complete license copied from the installed Three.js package:

${threeLicense.trimEnd()}

--------------------------------------------------------------------------------

fflate ${fflateVersion}, vendored in Three.js FBXLoader dependencies
https://github.com/101arrowz/fflate/tree/v${fflateVersion}
Complete license from the corresponding upstream release:

${fflateLicense}`;
await writeFile(path.join(root, 'dist/THIRD_PARTY_NOTICES.txt'), notices);
console.log('Wrote dist/THIRD_PARTY_NOTICES.txt (complete Three.js and fflate MIT notices).');
