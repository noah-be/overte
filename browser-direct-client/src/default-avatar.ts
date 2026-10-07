// SPDX-License-Identifier: Apache-2.0
const files = new Set([
    'defaultAvatar_full.fst', 'mannequin/mannequin.fbx', 'mannequin/Eyes.png',
    'mannequin/lambert1_Base_Color.png', 'mannequin/lambert1_Normal_OpenGL.png',
    'mannequin/lambert1_Roughness.png',
]);

/** Only the public, version-matched bundled mannequin resources bypass the asset gateway. */
export function defaultAvatarAsset(input:string, baseURL:string):string | undefined {
    const native = /^(?:qrc|resource):\/+meshes\/(.+)$/.exec(input);
    if (native && files.has(native[1])) return new URL(`/default-avatar/${native[1]}`,baseURL).href;
    let address:URL;
    try { address = new URL(input,baseURL); } catch { return; }
    if (address.origin !== new URL(baseURL).origin || address.search || address.hash
        || !address.pathname.startsWith('/default-avatar/') || !files.has(address.pathname.slice('/default-avatar/'.length))) return;
    return address.href;
}
