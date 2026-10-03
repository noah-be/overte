// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserWorld} from '../src/world';
function owner(){const world=Object.create(BrowserWorld.prototype) as any;Object.assign(world,{disposed:false,enabled:true,presentationEnabled:true,abort:new AbortController()});return world;}
test('actual World lazily owns one frame source; presentation pause and world lifetime cancel rather than schedule renders',()=>{
 const world=owner(),frames=world.getGraphicsScanFrames();assert.equal(frames,world.getGraphicsScanFrames());let cancellations=0;
 frames.subscribe(()=>{},()=>cancellations++);assert(world.graphicsScanPresentationVisible());world.setPresentationEnabled(false);assert.equal(cancellations,1);assert.equal(frames.active,false);assert.equal(world.graphicsScanPresentationVisible(),false);
 world.setPresentationEnabled(true);frames.subscribe(()=>{},()=>cancellations++);world.abort.abort();assert.equal(cancellations,2);assert.equal(frames.active,false);world.disposed=true;assert.throws(()=>world.getGraphicsScanFrames(),{name:'AbortError'});assert.throws(()=>world.getGraphicsEnvironment(),{name:'AbortError'});
});
test('actual World capability getter reads only fixed numeric limits/current drawing buffer/context attributes, never vendor or graphs',()=>{
 const world=owner(),old=Object.getOwnPropertyDescriptor(globalThis,'WebGL2RenderingContext'),reads:number[]=[];
 class Context {MAX_VIEWPORT_DIMS=1;MAX_TEXTURE_SIZE=2;MAX_RENDERBUFFER_SIZE=3;drawingBufferWidth=1280;drawingBufferHeight=800;getContextAttributes(){return {antialias:true};}getParameter(key:number){reads.push(key);if(key===1)return new Int32Array([8192,8192]);if(key===2||key===3)return 8192;throw Error('Undeclared driver query');}}
 Object.defineProperty(globalThis,'WebGL2RenderingContext',{value:Context,configurable:true});const context=new Context();world.renderer={getContext:()=>context};
 try{const caps=world.getGraphicsEnvironment();assert.deepEqual(caps,{webgl2:true,contextAntialias:true,maximumTextureDimension:8192,maximumRenderbufferDimension:8192,maximumViewportWidth:8192,maximumViewportHeight:8192,drawingBufferWidth:1280,drawingBufferHeight:800});assert.deepEqual(reads,[1,2,3]);context.drawingBufferWidth=640;assert.equal(world.getGraphicsEnvironment().drawingBufferWidth,640);}finally{world.abort.abort();if(old)Object.defineProperty(globalThis,'WebGL2RenderingContext',old);else Reflect.deleteProperty(globalThis,'WebGL2RenderingContext');}
});
test('actual World snapshot render cannot manufacture a visible-frame scanner sample',async()=>{
 const world=owner(),frames=world.getGraphicsScanFrames();let observations=0,renders=0;
 frames.subscribe(()=>observations++,()=>{});world.renderer={render(){renders++;}};world.canvas={toBlob(callback:(blob:Blob)=>void){callback(new Blob(['authored fixture']));}};
 try{await world.captureScene();assert.equal(renders,1);assert.equal(observations,0);assert.equal(frames.active,true);}finally{world.abort.abort();}
});
