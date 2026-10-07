// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Visitor-owned avatar values only. This DTO never carries account/configuration data.
const encoder=new TextEncoder();
const record=value=>value&&typeof value==='object'&&!Array.isArray(value);
const keys=(value,allowed)=>record(value)&&Object.keys(value).every(key=>allowed.includes(key));
export const MAX_PERSONA_BYTES=48*1024;
export const DEFAULT_AVATAR_URLS=new Set(['resource:/meshes\/defaultAvatar_full.fst','qrc:/meshes\/defaultAvatar_full.fst','resource:/meshes/mannequin/mannequin.fbx','qrc:/meshes/mannequin/mannequin.fbx']);
function text(value,max,bytes,empty=false){if(typeof value!=='string'||(!empty&&!value.trim())||value.length>max||encoder.encode(value).byteLength>bytes||/[\x00-\x1f\x7f]/.test(value))throw Error('Invalid visitor avatar text.');return value;}
export function personaAssetURL(value){
    text(value,4096,16384);
    const resource=/^(qrc|resource):\/+((?:meshes\/defaultAvatar_full\.fst|meshes\/mannequin\/mannequin\.fbx))$/.exec(value);
    if(resource)return resource[1]+':/'+resource[2];
    if(DEFAULT_AVATAR_URLS.has(value))return value;
    if(value.startsWith('atp:')){if(!/^atp:(?:\/[A-Za-z0-9_.%+@~-]+)+$/.test(value)||/%(?:2f|5c|00)/i.test(value)||value.split('/').some(part=>['.','..'].includes(decodeURIComponent(part))))throw Error('Invalid visitor avatar asset address.');return value;}
    const url=new URL(value);
    if(!['https:','http:'].includes(url.protocol)||!url.hostname||url.username||url.password||url.hash)throw Error('Only approved HTTP, ATP and fixed default-avatar resources are supported.');
    return url.href;
}
function finite(value,min,max){if(typeof value!=='number'||!Number.isFinite(value)||value<min||value>max)throw Error('Invalid visitor avatar number.');return value;}
function vector(value,min,max){if(!keys(value,['x','y','z'])||!['x','y','z'].every(key=>Object.hasOwn(value,key)))throw Error('Invalid visitor avatar vector.');return {x:finite(value.x,min,max),y:finite(value.y,min,max),z:finite(value.z,min,max)};}
function quaternion(value){if(!keys(value,['x','y','z','w'])||!['x','y','z','w'].every(key=>Object.hasOwn(value,key)))throw Error('Invalid visitor avatar rotation.');const result={x:finite(value.x,-1,1),y:finite(value.y,-1,1),z:finite(value.z,-1,1),w:finite(value.w,-1,1)};if(Math.abs(Object.values(result).reduce((sum,n)=>sum+n*n,0)-1)>.02)throw Error('Invalid visitor avatar rotation.');return result;}
export const WEARABLE_FIELDS=['type','name','modelURL','localPosition','localRotation','dimensions','registrationPoint','parentJointIndex','relayParentJoints','visible','locked','collisionless','ignoreForCollisions','ignorePickIntersection','canCastShadow','dynamic','useOriginalPivot','alpha','shapeType','compoundShapeURL','color','textures','userData','renderLayer','damping','angularDamping','friction','restitution','density','lifetime','gravity','velocity','angularVelocity','acceleration'];
export function validatePersonaWearable(value){
    if(!keys(value,['properties'])||!keys(value.properties,WEARABLE_FIELDS)||value.properties.type!=='Model')throw Error('This avatar favorite contains unsupported wearable properties.');
    const source=value.properties,result={type:'Model'};
    for(const [key,item] of Object.entries(source)){
        if(key==='type')continue;
        if(key==='name')result.name=text(item,256,1024,true);
        else if(key==='modelURL')result[key]=personaAssetURL(item);
        else if(key==='compoundShapeURL')result[key]=item===''?'':personaAssetURL(item);
        else if(['localPosition','gravity','velocity','angularVelocity','acceleration'].includes(key))result[key]=vector(item,-32768,32768);
        else if(key==='localRotation')result[key]=quaternion(item);
        else if(key==='dimensions')result[key]=vector(item,0,32768);
        else if(key==='registrationPoint')result[key]=vector(item,0,1);
        else if(key==='parentJointIndex'){if(!Number.isSafeInteger(item)||item< -1||item>999)throw Error('Invalid avatar wearable joint.');result[key]=item;}
        else if(['relayParentJoints','visible','locked','collisionless','ignoreForCollisions','ignorePickIntersection','canCastShadow','dynamic','useOriginalPivot'].includes(key)){if(typeof item!=='boolean')throw Error('Invalid avatar wearable flag.');result[key]=item;}
        else if(['alpha','damping','angularDamping','friction','restitution'].includes(key))result[key]=finite(item,0,1);
        else if(key==='density')result[key]=finite(item,0,1e6);
        else if(key==='lifetime')result[key]=finite(item,-1,1e9);
        else if(key==='color'){if(!keys(item,['red','green','blue']))throw Error('Invalid avatar wearable color.');result[key]={red:finite(item.red,0,255),green:finite(item.green,0,255),blue:finite(item.blue,0,255)};}
        else if(key==='shapeType'){if(!['none','box','sphere','capsule-x','capsule-y','capsule-z','cylinder-x','cylinder-y','cylinder-z','hull','simple-hull','compound','static-mesh','ellipsoid','circle','plane'].includes(item))throw Error('Unsupported avatar wearable collision shape.');result[key]=item;}
        else if(key==='renderLayer'){if(!['world','front','hud'].includes(item))throw Error('Unsupported avatar wearable render layer.');result[key]=item;}
        else if(key==='textures'){
            text(item,8192,8192,true);if(item===''){result[key]='';continue;}const mappings=JSON.parse(item);
            if(!record(mappings)||Object.keys(mappings).length>64)throw Error('Invalid avatar wearable textures.');
            const clean=Object.create(null);for(const [name,url] of Object.entries(mappings)){text(name,256,1024);clean[name]=personaAssetURL(url);}result[key]=JSON.stringify(clean);
        }else if(key==='userData'){
            text(item,4096,4096,true);if(item===''){result[key]='';continue;}const data=JSON.parse(item);
            if(!keys(data,['grabbableKey'])||!keys(data.grabbableKey,['grabbable','cloneable','triggerable','ignoreIK'])||Object.values(data.grabbableKey).some(flag=>typeof flag!=='boolean'))throw Error('Unsupported avatar wearable user data.');
            result[key]=JSON.stringify({grabbableKey:{...data.grabbableKey}});
        }
    }
    return {properties:result};
}
export function validateVisitorPersona(value={}){
    if(!keys(value,['displayName','avatarURL','avatarScale','avatarFavorites']))throw Error('Visitor persona contains unsupported fields.');
    const result={};
    if(Object.hasOwn(value,'displayName'))result.displayName=text(value.displayName,256,1024,true);
    if(Object.hasOwn(value,'avatarURL'))result.avatarURL=personaAssetURL(value.avatarURL);
    if(Object.hasOwn(value,'avatarScale'))result.avatarScale=finite(value.avatarScale,.005,1000);
    if(Object.hasOwn(value,'avatarFavorites')){
        if(!Array.isArray(value.avatarFavorites)||value.avatarFavorites.length>100)throw Error('Visitor avatar favorites exceed their limit.');
        const names=new Set();result.avatarFavorites=value.avatarFavorites.map(favorite=>{
            if(!keys(favorite,['name','avatarURL','avatarScale','avatarIcon','avatarEntities']))throw Error('Unsupported visitor avatar favorite.');
            const name=text(favorite.name,64,256).trim();if(names.has(name))throw Error('Avatar favorite names must be unique.');names.add(name);
            const entry={name,avatarURL:personaAssetURL(favorite.avatarURL),avatarScale:finite(favorite.avatarScale,.005,1000)};
            if(Object.hasOwn(favorite,'avatarIcon'))entry.avatarIcon=favorite.avatarIcon===''?'':personaAssetURL(favorite.avatarIcon);
            if(Object.hasOwn(favorite,'avatarEntities')){if(!Array.isArray(favorite.avatarEntities)||favorite.avatarEntities.length>32)throw Error('Avatar favorite wearables exceed their limit.');entry.avatarEntities=favorite.avatarEntities.map(validatePersonaWearable);}
            return entry;
        });
    }
    if(encoder.encode(JSON.stringify(result)).byteLength>MAX_PERSONA_BYTES)throw Error('Visitor avatar preferences exceed 48 KiB.');
    return result;
}
