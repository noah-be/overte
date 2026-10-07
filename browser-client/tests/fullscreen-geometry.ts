// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
/** Authored test-only reference: independent viewport layout, never measured target dimensions. */
export function createFullscreenViewportReference(){
    if(document.getElementById('fullscreen-viewport-reference'))throw Error('Duplicate authored viewport reference');
    const reference=document.createElement('div');reference.id='fullscreen-viewport-reference';reference.setAttribute('aria-hidden','true');
    Object.assign(reference.style,{position:'fixed',inset:'0',width:'auto',height:'auto',margin:'0',padding:'0',border:'0',boxSizing:'border-box',transform:'none',visibility:'hidden',pointerEvents:'none'});
    document.body.append(reference);
}
/** Serialize this exact function through page.evaluate; read-only public DOM APIs. */
export function readFullscreenViewportGeometry(){
    const target=document.getElementById('fullscreen-tablet-owner'),reference=document.getElementById('fullscreen-viewport-reference'),viewport=window.visualViewport;
    const box=(element:Element|null)=>{if(!element)return null;const r=element.getBoundingClientRect();return {left:r.left,top:r.top,right:r.right,bottom:r.bottom,width:r.width,height:r.height};};
    return {owner:!!target&&document.fullscreenElement===target,targetConnected:target?.isConnected===true,referenceConnected:reference?.isConnected===true,referenceOwned:reference?.parentElement===document.body,
        topLevel:window===window.top,visible:document.visibilityState==='visible',nativeDPR:devicePixelRatio,inner:{width:innerWidth,height:innerHeight},target:box(target),reference:box(reference),
        viewport:viewport?{width:viewport.width,height:viewport.height,offsetLeft:viewport.offsetLeft,offsetTop:viewport.offsetTop,scale:viewport.scale}:null};
}
export function removeFullscreenViewportReference(){document.getElementById('fullscreen-viewport-reference')?.remove();}
export type FullscreenViewportGeometry=ReturnType<typeof readFullscreenViewportGeometry>;
export function assertFullscreenViewportGeometry(value:FullscreenViewportGeometry){
    assert.equal(value.owner,true);assert.equal(value.targetConnected,true);assert.equal(value.referenceConnected,true);assert.equal(value.referenceOwned,true);assert.equal(value.topLevel,true);assert.equal(value.visible,true);
    assert(Number.isFinite(value.nativeDPR)&&value.nativeDPR>0&&value.nativeDPR<=8);
    for(const v of Object.values(value.inner))assert(Number.isSafeInteger(v)&&v>0&&v<=16384);
    assert(value.viewport);assert.equal(value.viewport.scale,1);assert.equal(value.viewport.offsetLeft,0);assert.equal(value.viewport.offsetTop,0);
    for(const v of [value.viewport.width,value.viewport.height])assert(Number.isFinite(v)&&v>0&&v<=16384);
    assert(value.target&&value.reference);
    for(const box of [value.target,value.reference])for(const v of Object.values(box))assert(Number.isFinite(v)&&Math.abs(v)<=16384);
    assert.equal(value.reference.left,0);assert.equal(value.reference.top,0);assert(value.reference.width>0&&value.reference.height>0);
    assert.equal(value.reference.right,value.reference.width);assert.equal(value.reference.bottom,value.reference.height);
    // Same public DOMRect representation: exact four edges and both dimensions.
    // Do not round to legacy integer innerWidth or compare across different float arithmetic.
    assert.deepEqual(value.target,value.reference);
}
