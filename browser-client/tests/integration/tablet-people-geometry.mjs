// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Self-contained factory: its exact source is installed by the owned harness only.
export function createPeopleGeometryProof(){
 const canonical=value=>typeof value==='string'?value.replace(/[{}]/g,'').toLowerCase():null;
 const same=(left,right)=>left.length===right.length&&JSON.stringify([...left].sort())===JSON.stringify([...right].sort());
 function rows(render){
  if(!render||render.censored!==false||render.orphanRoots!==0||!Array.isArray(render.rows)||render.rows.length>128)return null;
  if(render.remoteRoots!==render.rows.length||render.attachedRoots!==render.rows.length||render.renderableRoots!==render.rows.length)return null;
  const ids=render.rows.map(row=>canonical(row.id));
  if(ids.some(id=>!id)||new Set(ids).size!==ids.length||render.rows.some(row=>row.attached!==true||row.visible!==true
    ||typeof row.rig!=='boolean'||!Number.isSafeInteger(row.rootObjectID)||row.rootObjectID<0||!Number.isSafeInteger(row.geometryMeshes)||row.geometryMeshes<1))return null;
  if(render.rigRoots!==render.rows.filter(row=>row.rig).length||render.fallbackRoots!==render.rows.filter(row=>!row.rig).length)return null;
  return ids;
 }
 function ready(snapshot,self,render,count){
  const ids=rows(render);if(!ids||!Array.isArray(snapshot)||!canonical(self))return false;
  const all=snapshot.map(value=>canonical(value.id));
  if(all.some(id=>!id)||new Set(all).size!==all.length||!all.includes(canonical(self)))return false;
  const expected=all.filter(id=>id!==canonical(self));
  return count===expected.length&&same(ids,expected);
 }
 function ignored({snapshot,self,batches,count,render,before,peer}){
  if(!ready(snapshot,self,render,count)||!before||count!==before.count-1||!Array.isArray(batches)||batches.length<3)return false;
  const oldRows=rows(before.geometry);if(!oldRows)return false;
  const target=canonical(peer),oldIDs=before.ids.map(canonical),expected=oldIDs.filter(id=>id!==target);
  if(!target||!oldRows.includes(target)||snapshot.some(value=>canonical(value.id)===target))return false;
  if(!batches.slice(-3).every(batch=>Array.isArray(batch.ids)&&same(batch.ids.map(canonical),expected)))return false;
  return same(rows(render),oldRows.filter(id=>id!==target))&&render.rows.every(row=>{
   const previous=before.geometry.rows.find(old=>canonical(old.id)===canonical(row.id));return previous&&row.rootObjectID===previous.rootObjectID;
  });
 }
 function restored({snapshot,self,count,render,before,peer}){
  if(!ready(snapshot,self,render,count)||count!==before.count||!same(rows(render),rows(before.geometry)||[]))return false;
  const target=canonical(peer),previous=before.geometry.rows.find(row=>canonical(row.id)===target),current=render.rows.find(row=>canonical(row.id)===target);
  return !!previous&&!!current&&current.rootObjectID!==previous.rootObjectID&&render.rows.every(row=>{
   if(canonical(row.id)===target)return true;
   const old=before.geometry.rows.find(item=>canonical(item.id)===canonical(row.id));return old&&old.rootObjectID===row.rootObjectID;
  });
 }
 return {ready,ignored,restored};
}
