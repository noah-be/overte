// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {test,expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {RESPONSIVE_CREATE_CSS,CREATE_LAYOUT_SOURCE_SHA256} from '../gateway/create-responsive-overrides.mjs';

const nativeHTML=await readFile(new URL('../../scripts/system/create/entityProperties/html/entityProperties.html',import.meta.url),'utf8');
if(createHash('sha256').update(nativeHTML).digest('hex')!==CREATE_LAYOUT_SOURCE_SHA256['system/create/entityProperties/html/entityProperties.html'])throw Error('Native Properties HTML fixture changed');
const style=await readFile(new URL('../../scripts/system/html/css/edit-style.css',import.meta.url),'utf8');
const tabs=await readFile(new URL('../../scripts/system/html/css/tabs.css',import.meta.url),'utf8');
for(const [name,value] of [['system/html/css/edit-style.css',style],['system/html/css/tabs.css',tabs]])
 if(createHash('sha256').update(value).digest('hex')!==CREATE_LAYOUT_SOURCE_SHA256[name])throw Error('Native layout fixture source changed');
const widget=await readFile(new URL('../../scripts/system/create/entityProperties/html/js/draggableNumber.js',import.meta.url),'utf8');
const fullVector=await readFile(new URL('../../scripts/system/create/entityProperties/html/js/entityProperties.js',import.meta.url),'utf8');
if(createHash('sha256').update(widget).digest('hex')!=='7f4acaa0dce2de9f6816eef074d3c5ac77fd9a74f9c486b9c061a43506057016'||createHash('sha256').update(fullVector).digest('hex')!=='085ab1c8248eeca61efa11eff4148f5493d2b933d167143cb1173ff8764c6a65')throw Error('Native widget fixture source changed');
function nativeFunction(name:string,expected:string):string{
 const marker='function '+name+'(';if(fullVector.split(marker).length!==2)throw Error('Native widget fixture boundary changed');
 const start=fullVector.indexOf(marker),end=fullVector.indexOf('\n}\n',start)+3;if(end<=start)throw Error('Native widget fixture boundary changed');
 const result=fullVector.slice(start,end);if(createHash('sha256').update(result).digest('hex')!==expected)throw Error('Native widget fixture function changed');return result;
}
// These actual repository function bytes are identical to packaged f91d15a.
const vector=nativeFunction('createVec3Property','beb0274332561195647b4508ef6fa90501bc67b088e220515c9d3f1c98b3b6d3')+'\n'+nativeFunction('createTupleNumberInput','135ecdb2a14e059637919fc93ca4139b40c34b4accce4767506924304c2bb256');

// Use the actual authored Properties table/body, including its native placeholder
// row. The generated property keeps loaded()'s exact width:100% inline wrapper;
// omitting that wrapper incorrectly permits the original three axes to shrink.
const bodyStart=nativeHTML.indexOf('        <div id="properties-list">'),bodyEnd=nativeHTML.indexOf('        <div id="uiCreateChildEntityAssistant"');
if(bodyStart<0||bodyEnd<=bodyStart)throw Error('Native Properties HTML boundary changed');
const nativeBody=nativeHTML.slice(bodyStart,bodyEnd);
const resourceSHA256:Record<string,string>={"Raleway-Regular.ttf":"20e4ae409ffbe8bfd2af14d7f717398408ae8b481005beccb83d62ef4052b681","Raleway-Light.ttf":"b3d8986142d28fd27c5158b5d24b072bbed301b1763fe0bfe3076a631e8ea0ca","Raleway-Bold.ttf":"ca9de8b3be7ccd4b80774a9c7dd56a98c49c276771c5957729b5958d1d579112","Raleway-SemiBold.ttf":"b7680f30199f65ce3b2620713f7cb27a175560ea7402e0b4cba01c5d54508a17","FiraSans-SemiBold.ttf":"95386ec5d6fe6c9e670a61412a29b835e2911b2c263a1092f60c2a947ccc9211","AnonymousPro-Regular.ttf":"6a3502f45cd580a77e61ac5eec75a7ea699c27e295596806b514d3a04d89165b","hifi-glyphs.ttf":"908ed9b7917dd9af32e51ee1836616a25e9265d4b7e766d537c944b181a4c83b","vircadia_glyphs.ttf":"d00f7c329da7556c8a8787916b0a7219e37a44804ac45a88b458a953fef6286f","spatial.png":"fcf7d26ed8f7aa59aeb05f16cbb384e48b05d52f504b3c07cbca5d23de2f8472"};
async function nativeResource(name:string){
 const bytes=await readFile(new URL(name==='spatial.png'?'../../scripts/system/create/entityProperties/html/tabs/spatial.png':'../../interface/resources/fonts/'+name,import.meta.url));
 if(createHash('sha256').update(bytes).digest('hex')!==resourceSHA256[name])throw Error('Native widget resource changed');return bytes;
}
async function layout(page:any,width:number,responsive:boolean){
 await page.goto('about:blank');
 await page.setViewportSize({width,height:706});
 // Load the actual native fonts, not fallback Latin letters for HiFi-Glyphs D.
 // Otherwise the right arrow itself can incorrectly cover a small input's center.
 await page.route('http://native-layout.test/**',async(route:any)=>{
  const name=new URL(route.request().url()).pathname.split('/').at(-1)||'';
  if(['Raleway-Regular.ttf','Raleway-Light.ttf','Raleway-Bold.ttf','Raleway-SemiBold.ttf','FiraSans-SemiBold.ttf','AnonymousPro-Regular.ttf','hifi-glyphs.ttf','vircadia_glyphs.ttf'].includes(name)){
   await route.fulfill({body:await nativeResource(name),contentType:'font/ttf'});return;
  }
  if(name==='spatial.png'){await route.fulfill({body:await nativeResource(name),contentType:'image/png'});return;}
  await route.abort();
 });
 const content=nativeBody.replace('<div id="tabs" class="tabsContainer"></div>','<div id="tabs" class="tabsContainer"><button id="tab-spatial"><img src="tabs/spatial.png"></button></div>').replace('<!-- each property is added at runtime in entityProperties -->','<div class="section major" id="properties-spatial"><div class="tab-section-header"><div class="labelTabHeader">Spatial</div></div><div class="property container" id="div-property-localDimensions"><label><span class="">Local Dimensions</span></label><div id="dimension-value" style="width: 100%;"></div></div></div>');
 await page.setContent(`<base href="http://native-layout.test/scripts/system/create/entityProperties/html/"><style>${style}\n${tabs}\n${responsive?RESPONSIVE_CREATE_CSS:''}</style>${content}`);
 await page.addScriptTag({content:widget});
 await page.addScriptTag({content:`const VECTOR_ELEMENTS={X_NUMBER:0,Y_NUMBER:1,Z_NUMBER:2};function createDragStartFunction(){return function(){};}function createDragEndFunction(){return function(){};}function createMultiDiffStepFunction(){return function(){};}function createEmitNumberPropertyComponentUpdateFunction(property,axis){return function(){window.layoutEffects.push({axis,value:Number(this.value)});};}\n${vector}\nwindow.layoutEffects=[];window.nativeNumbers=createVec3Property({elementID:'property-localDimensions',data:{vec3Type:'xyz',subLabels:['x','y','z'],step:.01,decimals:4,min:0,max:10000}},document.getElementById('dimension-value'));window.nativeNumbers.forEach(function(n,i){n.setValue(i+1);});`});
 await page.evaluate(async()=>{for(const font of ['HiFi-Glyphs','Raleway-Regular','Raleway-SemiBold','FiraSans-SemiBold']){await document.fonts.load('15px "'+font+'"');if(!document.fonts.check('15px "'+font+'"'))throw Error('Required native font failed');}await document.fonts.ready;});
 return page.locator('.draggable-number');
}
test('authentic native widgets fit all three axes at320/480/600 pixels and genuine editing keeps native handlers',async({page})=>{
 for(const width of [320,480,600]){
  const controls=await layout(page,width,true);
  for(let axis=0;axis<3;axis++){
   const text=controls.nth(axis).locator('.text'),box=await text.boundingBox();expect(box).not.toBeNull();expect(box!.width).toBeGreaterThan(25);expect(box!.x).toBeGreaterThanOrEqual(0);expect(box!.x+box!.width).toBeLessThanOrEqual(width);
   const left=await controls.nth(axis).locator('.left-arrow').boundingBox(),right=await controls.nth(axis).locator('.right-arrow').boundingBox();expect(left).not.toBeNull();expect(right).not.toBeNull();
   // Native glyph arrows are actual hit targets. A nominally visible text box
   // must retain space between them, and its genuine click must reach text.
   expect(box!.width).toBeGreaterThan(left!.width+right!.width);
   expect(await text.evaluate((el:Element)=>{const b=el.getBoundingClientRect();return document.elementFromPoint(b.x+b.width/2,b.y+b.height/2)===el;})).toBe(true);
   await text.click();const input=controls.nth(axis).locator('input[type=number]');await expect(input).toBeFocused();await input.press('Control+a');await page.keyboard.type(String((axis+1)/10));await input.press('Enter');await expect(input).toHaveValue(((axis+1)/10).toFixed(4));expect(Number(await input.inputValue())).toBe((axis+1)/10);
   expect(await page.evaluate(()=>(window as any).layoutEffects.at(-1))).toEqual({axis:['x','y','z'][axis],value:(axis+1)/10});
  }
  expect(await page.evaluate(()=>[...new Set((window as any).layoutEffects.map((effect:any)=>effect.axis))])).toEqual(['x','y','z']);
 }
});
test('480pixel negative control is clipped without adaptation and desktop layout remains exact',async({page})=>{
 const clipped=await layout(page,480,false);expect((await clipped.nth(2).locator('.text').boundingBox())!.x).toBeGreaterThanOrEqual(480);
 const before=await layout(page,800,false),reference=await before.evaluateAll((items:Element[])=>items.map(item=>{const b=item.getBoundingClientRect();return[b.x,b.y,b.width,b.height];}));
 const after=await layout(page,800,true);expect(await after.evaluateAll((items:Element[])=>items.map(item=>{const b=item.getBoundingClientRect();return[b.x,b.y,b.width,b.height];}))).toEqual(reference);
});
