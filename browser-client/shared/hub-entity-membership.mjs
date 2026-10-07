// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Private lab membership only; no names, URLs, poses, tokens or whole entities. */
export function projectWorldEntityMembership(entities,objects){
 const refused=reason=>({schema:1,status:'refused',reason});
 const id=value=>typeof value==='string'&&/^(?:\{)?[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?:\})?$/i.test(value);
 const type=value=>typeof value==='string'&&/^[A-Za-z][A-Za-z0-9]{0,63}$/.test(value);
 if(!(entities instanceof Map)||!(objects instanceof Map))return refused('source-shape');
 if(entities.size>4096||objects.size>4096||entities.size+objects.size>8192)return refused('record-budget');
 const entityRows=[],slotRows=[];
 for(const [key,entity]of entities){if(!id(key)||!entity||!type(entity.type))return refused('source-shape');entityRows.push([key,entity.type]);}
 for(const [key,root]of objects){if(!id(key)||!root||!root.userData)return refused('source-shape');const entity=entities.get(key),kind=entity?.type??'missing';if(!type(kind))return refused('source-shape');
  slotRows.push([key,kind,root.userData.modelLoaded===true,root.userData.modelFailed===true,root.userData.shadersReady===true,root.userData.modelGeometryReady===true]);}
 entityRows.sort((a,b)=>a[0].localeCompare(b[0]));slotRows.sort((a,b)=>a[0].localeCompare(b[0]));
 const result={schema:1,status:'complete',entityRows,slotRows};if(new TextEncoder().encode(JSON.stringify(result)).byteLength>512*1024)return refused('byte-budget');return result;
}
/** Self-contained serializable same-task collector. Existing native WS map only. */
export function collectHubEntityMembership(){
 const refused=reason=>({schema:1,status:'refused',reason});
 const id=value=>typeof value==='string'&&/^(?:\{)?[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}(?:\})?$/i.test(value);
 const type=value=>typeof value==='string'&&/^[A-Za-z][A-Za-z0-9]{0,63}$/.test(value);
 try{const source=window.__hubEntitySummary;if(!(source instanceof Map)||source.size>4096)return refused('record-budget');
  const nativeRows=[];for(const [key,value]of source){if(!id(key)||!value||!type(value.type))return refused('source-shape');nativeRows.push([key,value.type]);}nativeRows.sort((a,b)=>a[0].localeCompare(b[0]));
  const world=window.__overte?.entityModelMembership;if(!world||world.schema!==1||world.status!=='complete')return refused('world-unavailable');
  if(!Array.isArray(world.entityRows)||!Array.isArray(world.slotRows)||nativeRows.length+world.entityRows.length+world.slotRows.length>8192)return refused('record-budget');
  for(const row of world.entityRows)if(!Array.isArray(row)||row.length!==2||!id(row[0])||!type(row[1]))return refused('source-shape');
  for(const row of world.slotRows)if(!Array.isArray(row)||row.length!==6||!id(row[0])||!type(row[1])||row.slice(2).some(v=>typeof v!=='boolean'))return refused('source-shape');
  const projectedWorld={schema:1,status:'complete',entityRows:world.entityRows.map(row=>[row[0],row[1]]),slotRows:world.slotRows.map(row=>[row[0],row[1],row[2],row[3],row[4],row[5]])};
  const result={schema:1,status:'complete',scope:'private-native-received-and-owned-world-membership-same-task',nativeRows,world:projectedWorld};
  if(new TextEncoder().encode(JSON.stringify(result)).byteLength>512*1024)return refused('byte-budget');return result;
 }catch{return refused('source-refused');}
}
