// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
const uuid=/^\{?[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}?$/i;
export function assertIsolatedCreateTarget(gateway,domain){
 const url=new URL(gateway);assert(['127.0.0.1','localhost'].includes(url.hostname)&&url.protocol==='http:'&&!url.username&&!url.password,'Create proof only admits an owned loopback gateway');
 assert.equal(domain,'overte://127.0.0.2:45102','Create proof refuses public or alternative domains');
}
export function domainEntities(snapshot){assert(Array.isArray(snapshot)&&snapshot.length<=64,'Bounded native entity observation required');return snapshot.filter(e=>e.entityHostType==='domain'&&e.clientOnly!==true);}
export function baselineIdentity(snapshot){
 const values=domainEntities(snapshot);assert.equal(values.length,7,'Exactly the seven preserved lab entities must exist before Create');
 assert(values.every(e=>uuid.test(e.id)&&typeof e.name==='string'&&e.name.startsWith('Browser Lab ')&&typeof e.type==='string'),'Every baseline entity must have the expected actual native identity');
 assert.equal(new Set(values.map(e=>e.id)).size,7);return values.map(e=>({id:e.id,name:e.name,type:e.type})).sort((a,b)=>a.id.localeCompare(b.id));
}
export function assertBaseline(snapshot,baseline){const actual=domainEntities(snapshot);for(const e of baseline){const found=actual.find(x=>x.id===e.id);assert(found&&found.name===e.name&&found.type===e.type,'A preserved baseline entity changed identity');}}
export function discoverOwnedShape(before,after){
 const baseline=baselineIdentity(before);assertBaseline(after,baseline);const created=domainEntities(after).filter(e=>!baseline.some(b=>b.id===e.id));
 assert.equal(created.length,1,'Exactly one new domain entity must follow the genuine Shape click');const value=created[0];assert(uuid.test(value.id)&&(value.type==='Shape'||value.type==='Box')&&value.shape==='Cube'&&!value.locked,'Only the single unlocked newly created Cube can be owned by this proof');
 assert(!value.parentID||/^\{?0{8}-0{4}-0{4}-0{4}-0{12}\}?$/.test(value.parentID),'New fixture must be independent');assert.equal(value.children?.length||0,0,'Fixture deletion must not recursively delete children');return {...value};
}
export function validateCreateCoordinates(input){
 assert(input&&input.version===1&&/^[0-9a-f]{64}$/.test(input.propertiesPNG_SHA256)&&/^[0-9a-f]{64}$/.test(input.listPNG_SHA256),'A versioned map from actual captured native UI is required');
 const result={version:1,propertiesPNG_SHA256:input.propertiesPNG_SHA256,listPNG_SHA256:input.listPNG_SHA256};
 for(const field of ['name','shapeTab','colorRed','colorGreen','colorBlue','transformTab','dimensionX','dimensionY','dimensionZ','listSearch','listRow','listDelete']){const p=input[field];assert(Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[0]<480&&p[1]>=40&&p[1]<706,`Actual calibrated native ${field} coordinate required`);result[field]=[...p];}
 if(input.colorSwatch!==undefined){const p=input.colorSwatch;assert(Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)&&p[0]>=0&&p[0]<480&&p[1]>=40&&p[1]<706&&/^[0-9a-f]{64}$/.test(input.colorPickerPNG_SHA256),'Actual calibrated native color swatch and picker PNG are required');result.colorSwatch=[...p];result.colorPickerPNG_SHA256=input.colorPickerPNG_SHA256;}
 return result;
}
export function assertExpectedShape(entity,{id,name,color,dimensions}){
 assert(entity&&entity.id===id&&(entity.type==='Shape'||entity.type==='Box')&&entity.shape==='Cube'&&entity.name===name,'Actual owned Shape identity/name must agree');
 for(const key of ['red','green','blue'])assert.equal(entity.color?.[key],color[key],'Actual native/browser color must agree');
 for(const key of ['x','y','z'])assert(Math.abs(entity.dimensions?.[key]-dimensions[key])<0.0001,'Actual native/browser dimensions must agree');
}
