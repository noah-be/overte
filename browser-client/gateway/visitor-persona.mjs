// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import path from 'node:path';
import {mkdir,writeFile} from 'node:fs/promises';
import {validateVisitorPersona,DEFAULT_AVATAR_URLS} from '../shared/visitor-persona.mjs';
import {approvedAssetAddress} from './validation.mjs';

// Syntactic browser validation is deliberately separate from operator-approved asset origins.
export function approvedVisitorPersona(value, origins) {
    const clean=validateVisitorPersona(value);
    const check=url=>{if(url&& !DEFAULT_AVATAR_URLS.has(url)&&!url.startsWith('atp:'))approvedAssetAddress(url,origins);};
    if(clean.avatarURL)check(clean.avatarURL);
    for(const favorite of clean.avatarFavorites||[]){check(favorite.avatarURL);check(favorite.avatarIcon);
        for(const wearable of favorite.avatarEntities||[]){const p=wearable.properties;check(p.modelURL);check(p.compoundShapeURL);
            if(p.textures)for(const url of Object.values(JSON.parse(p.textures)))check(url);}}
    return clean;
}
export function nativeAvatarBookmarks(persona) {
    const result=Object.create(null);
    for(const favorite of validateVisitorPersona(persona).avatarFavorites||[]){
        result[favorite.name]={version:3,avatarUrl:favorite.avatarURL,avatarScale:favorite.avatarScale,avatarIcon:favorite.avatarIcon||'',
            avatarEntites:favorite.avatarEntities||[]};
    }
    return result;
}
export async function prepareVisitorPersona(directory, value, origins, organization='Overte') {
    const persona=approvedVisitorPersona(value,origins);
    if(!/^Overte(?: - (?:Dev|Nightly|PR[0-9]{1,10}))?$/.test(organization))throw Error('Unsupported native persona application organization.');
    if(Object.hasOwn(persona,'avatarFavorites')){
        // QStandardPaths::AppDataLocation uses organization/application. Never copy an operator profile.
        const target=path.join(directory,'data',organization,'Interface');
        await mkdir(target,{recursive:true,mode:0o700});
        await writeFile(path.join(target,'avatarbookmarks.json'),JSON.stringify(nativeAvatarBookmarks(persona)),{flag:'wx',mode:0o600});
    }
    return persona;
}
export function acceptedNativePersona(message,origins) {
    const result={},warnings=[];
    for(const key of ['displayName','avatarURL','avatarScale']){
        if(message[key]!==undefined){try{Object.assign(result,approvedVisitorPersona({[key]:message[key]},origins));}
            catch{warnings.push('A native avatar value is unsupported or uses an unapproved asset origin. Its saved browser value was preserved.');}}
    }
    if(message.avatarFavorites!==undefined){try{Object.assign(result,approvedVisitorPersona({avatarFavorites:message.avatarFavorites},origins));}
        catch{warnings.push('Native avatar favorites contain unsupported wearable data, exceed 48 KiB, or use an unapproved asset origin. Saved browser favorites were preserved.');}}
    return {persona:result,warnings:[...new Set(warnings)]};
}
