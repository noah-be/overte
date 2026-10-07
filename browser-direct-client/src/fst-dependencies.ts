// SPDX-License-Identifier: Apache-2.0
import {assetDependency} from './world-data';

/** Match native ModelCache: texdir is relative to the FST's baseURL, not the FBX. */
export function fstDependencies(source:string, mapping:string):{model:string;textures?:string} {
    const field = (key:string) => new RegExp(`^[\\t ]*${key}[\\t ]*=[\\t ]*([^\\r\\n]*)`,'m').exec(mapping)?.[1]?.trim();
    const filename = field('filename');
    if (!filename) throw Error('FST mapping has no filename');
    const base = assetDependency(source,field('baseURL') || '');
    const texdir = field('texdir');
    return {model:assetDependency(base,filename),...(texdir === undefined ? {} : {
        textures:assetDependency(base,texdir.endsWith('/') ? texdir : `${texdir}/`),
    })};
}
