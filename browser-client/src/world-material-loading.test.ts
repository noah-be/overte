// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {Texture} from 'three';
import {BrowserWorld} from './world';
import type {MaterialData} from './world-data';
const turn=()=>new Promise<void>(resolve=>setTimeout(resolve,0));
const fixture={name:'Authored PBR',albedoMap:'albedo.png',normalMap:'normal.png',roughnessMap:'rough.png',metallicMap:'metal.png',emissiveMap:'glow.png'} satisfies MaterialData;
function deferred(){let resolve!:(value:Texture)=>void,reject!:(error:Error)=>void;const promise=new Promise<Texture>((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};}
function materialTest(){
  const owner=Object.create(BrowserWorld.prototype) as BrowserWorld;
  const state=owner as unknown as {abort:AbortController;options:unknown;texture:(url:string,color:boolean)=>Promise<Texture>;configureAlpha:()=>Promise<void>;makeMaterial:(data:MaterialData,source:string)=>Promise<any>};
  state.abort=new AbortController();state.options={onStatus:()=>{}};state.configureAlpha=async()=>{};
  const requests=new Map<string,{color:boolean;job:ReturnType<typeof deferred>}>();
  state.texture=(url,color)=>{const job=deferred();requests.set(url,{color,job});return job.promise;};
  return {state,requests};
}
test('Authored PBR maps start concurrently and keep their independent color-space roles',async()=>{
  const {state,requests}=materialTest();const pending=state.makeMaterial(fixture,'https://assets.invalid/material.json');
  assert.equal(requests.size,5,'None of the five independent maps waits for an earlier image');
  assert.equal(requests.get('https://assets.invalid/albedo.png')?.color,true);assert.equal(requests.get('https://assets.invalid/normal.png')?.color,false);
  const textures=new Map<string,Texture>();for(const [url,{job}]of requests){const texture=new Texture();textures.set(url,texture);job.resolve(texture);}
  const material=await pending;assert.equal(material.map,textures.get('https://assets.invalid/albedo.png'));assert.equal(material.normalMap,textures.get('https://assets.invalid/normal.png'));assert.equal(material.emissiveMap,textures.get('https://assets.invalid/glow.png'));
  for(const texture of textures.values())texture.dispose();material.dispose();
});
test('One failed map waits for remaining maps and releases late successful texture ownership',async()=>{
  const {state,requests}=materialTest();let settled=false;const pending=state.makeMaterial(fixture,'https://assets.invalid/material.json');pending.then(()=>{settled=true;},()=>{settled=true;});
  requests.get('https://assets.invalid/albedo.png')!.job.reject(Error('Asset permission rejected'));await turn();assert.equal(settled,false,'Cleanup cannot finish while another map can still attach its texture');
  let disposed=0;for(const [url,{job}]of requests){if(url.endsWith('/albedo.png'))continue;const texture=new Texture();texture.addEventListener('dispose',()=>disposed++);job.resolve(texture);}
  await assert.rejects(pending,/Asset permission rejected/);assert.equal(disposed,4,'Every successful map created after a sibling failure is released');
});
