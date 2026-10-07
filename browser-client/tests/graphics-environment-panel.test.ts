// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';
import {GraphicsEnvironmentPanel} from '../src/graphics-environment-panel';
import {GraphicsEnvironmentScan} from '../src/graphics-environment-scan';
import {GraphicsScanFrames} from '../src/graphics-scan-frames';
import {DEFAULT_BROWSER_GRAPHICS} from '../shared/browser-graphics.mjs';
class Element extends EventTarget {style={};children:Element[]=[];disabled=false;textContent='';type='';setAttribute(){}append(...items:Element[]){this.children.push(...items);}remove(){}}
test('actual panel disables Scan during Apply and cannot describe an in-flight prior setting as unchanged',async()=>{
 const previous=Object.getOwnPropertyDescriptor(globalThis,'document');const doc=Object.assign(new EventTarget(),{visibilityState:'visible',createElement:()=>new Element()});
 Object.defineProperty(globalThis,'document',{value:doc,configurable:true});
 const abort=new AbortController(),frames=new GraphicsScanFrames(abort.signal);let state={...DEFAULT_BROWSER_GRAPHICS},resolve!:(value:typeof state)=>void;
 const scanner=new GraphicsEnvironmentScan({frames,document:doc as unknown as Document,current:()=>true,presentationVisible:()=>true,settings:()=>state,
 capabilities:()=>({webgl2:true,contextAntialias:true,maximumTextureDimension:8192,maximumRenderbufferDimension:8192,maximumViewportWidth:8192,maximumViewportHeight:8192,drawingBufferWidth:1280,drawingBufferHeight:800}),
 applyResolution:()=>new Promise(yes=>{resolve=yes;})});
 const toolbar=new Element();let showWorld=0;const panel=new GraphicsEnvironmentPanel(toolbar as unknown as HTMLElement,scanner,{showWorld:()=>{showWorld++;},showResultIfCurrent(){}});
 const [scan,apply,status]=toolbar.children[0].children;
 try{
  scan.dispatchEvent(new Event('click'));for(let i=0;i<=40;i++)frames.publish({timestampMs:i*50,cpuSubmitMs:1,ready:true});await new Promise<void>(yes=>setImmediate(yes));
  assert.equal(scan.disabled,false);assert.equal(apply.disabled,false);assert.equal(showWorld,1);
  apply.dispatchEvent(new Event('click'));assert.equal(scan.disabled,true);assert.equal(apply.disabled,true);
  scan.dispatchEvent(new Event('click'));assert.equal(showWorld,1);assert.equal(frames.active,false);
  panel.cancel();assert.equal(scan.disabled,true);assert.match(status.textContent,/previously requested setting may have applied/);assert(!status.textContent.includes('settings are unchanged'));
  state={...state,resolutionPercent:90};resolve(state);await new Promise<void>(yes=>setImmediate(yes));assert.equal(scan.disabled,false);
  assert.match(status.textContent,/previously requested setting may have applied/);
 }finally{panel.dispose();abort.abort();if(previous)Object.defineProperty(globalThis,'document',previous);else Reflect.deleteProperty(globalThis,'document');}
});
