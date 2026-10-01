// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// CPU pixel oracles shared by the genuine native/browser Image fixture.
function checked(sample){
 if(!sample||!Array.isArray(sample.rgb)||sample.rgb.length<3||sample.rgb.length>64*64*3||sample.rgb.length%3||!Array.isArray(sample.mask)||sample.mask.length!==sample.rgb.length/3||!sample.rgb.every(v=>Number.isFinite(v)&&v>=0&&v<=255)||!sample.mask.every(v=>v===0||v===1))throw Error('Invalid bounded Image pixel sample');
 return sample;
}
export function imagePixelComparison(a,b){
 checked(a);checked(b);if(a.rgb.length!==b.rgb.length)throw Error('Image pixel samples must use the same grid');
 const count=a.rgb.length,mae=a.rgb.reduce((sum,v,i)=>sum+Math.abs(v-b.rgb[i]),0)/count,meanA=[0,0,0],meanB=[0,0,0];
 for(let i=0;i<count;i++){meanA[i%3]+=a.rgb[i]/(count/3);meanB[i%3]+=b.rgb[i]/(count/3);}
 let dot=0,aa=0,bb=0;for(let i=0;i<count;i++){const x=a.rgb[i]-meanA[i%3],y=b.rgb[i]-meanB[i%3];dot+=x*y;aa+=x*x;bb+=y*y;}
 return{rgbMAE:mae,correlation:aa>1e-12&&bb>1e-12?dot/Math.sqrt(aa*bb):0,maskMismatch:a.mask.reduce((sum,v,i)=>sum+(v!==b.mask[i]?1:0),0)/a.mask.length};
}
/** Require real authored detail rather than a universal brightness/variance cutoff.
 * Existing RGB-error and pattern thresholds remain fixed. A flat/dark/missing
 * frame cannot correlate with the nonflat SHA-audited source image. */
export function assertLoadedImagePixels(observed,reference){
 const result=imagePixelComparison(observed,reference);
 if(result.rgbMAE>10)throw Error('Actual Image pixels do not match the audited source colors');
 if(result.correlation<.9)throw Error('Actual Image detail or UV orientation does not match the audited source');
 return result;
}
/** Linear-light alpha composition over the fixture's authored unlit magenta.
 * Transparent source pixels must not count as black or hidden texture detail. */
export function compositeImagePixel(r,g,b,alpha){
 if(![r,g,b,alpha].every(v=>Number.isFinite(v)&&v>=0&&v<=255))throw Error('Invalid source Image pixel');
 if(alpha===255)return[r,g,b];if(alpha===0)return[255,0,255];
 const decode=v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;},encode=v=>Math.round(255*(v<=.0031308?12.92*v:1.055*v**(1/2.4)-.055)),a=alpha/255;
 return[encode(decode(r)*a+1-a),encode(decode(g)*a),encode(decode(b)*a+1-a)];
}
