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

/** Deterministic pixel-overlap area reduction. Canvas implementations select
 * different minification kernels even with imageSmoothingQuality='high'; the
 * authored detail oracle must apply one explicit kernel to both screenshot and
 * source. Source alpha is composed per input pixel before encoded-RGB reduction.
 * No source resize, tone/brightness adjustment, image mutation or retained input.
 */
export function weightedAreaImagePixels({rgba,width,height,crop={x:0,y:0,width,height},grid=64,composeNativeAlpha=false}){
 if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||height<1||width>16384||height>16384||width*height>4*1024*1024)throw Error('Image area sampler exceeds the bounded four-megapixel input');
 if(!(rgba instanceof Uint8Array||rgba instanceof Uint8ClampedArray)||rgba.length!==width*height*4)throw Error('Image area sampler requires exact bounded RGBA bytes');
 if(!Number.isInteger(grid)||grid<1||grid>64||typeof composeNativeAlpha!=='boolean')throw Error('Invalid bounded Image sample grid/options');
 if(!crop||!['x','y','width','height'].every(k=>Number.isFinite(crop[k]))||crop.x<0||crop.y<0||crop.width<=0||crop.height<=0||crop.x+crop.width>width||crop.y+crop.height>height)throw Error('Image sample crop must remain inside the actual input');
 const rgb=[],mask=[],dx=crop.width/grid,dy=crop.height/grid;let mean=0,square=0;
 for(let oy=0;oy<grid;oy++)for(let ox=0;ox<grid;ox++){
  const x0=crop.x+ox*dx,x1=Math.min(width,crop.x+crop.width,crop.x+(ox+1)*dx),y0=crop.y+oy*dy,y1=Math.min(height,crop.y+crop.height,crop.y+(oy+1)*dy);let r=0,g=0,b=0,area=0;
  for(let y=Math.floor(y0);y<Math.ceil(y1);y++)for(let x=Math.floor(x0);x<Math.ceil(x1);x++){
   const weight=(Math.min(x1,x+1)-Math.max(x0,x))*(Math.min(y1,y+1)-Math.max(y0,y));if(weight<=0)continue;
   const at=(y*width+x)*4;let red=rgba[at],green=rgba[at+1],blue=rgba[at+2];
   if(composeNativeAlpha&&rgba[at+3]!==255){const composed=compositeImagePixel(red,green,blue,rgba[at+3]);red=composed[0];green=composed[1];blue=composed[2];}
   r+=red*weight;g+=green*weight;b+=blue*weight;area+=weight;
  }
  if(!(area>0)||!Number.isFinite(area))throw Error('Image crop is too small for a finite sample cell');r=Math.min(255,Math.max(0,r/area));g=Math.min(255,Math.max(0,g/area));b=Math.min(255,Math.max(0,b/area));rgb.push(r,g,b);mask.push(r>130&&b>100&&r>g*1.5+25&&b>g*1.5+25?1:0);const total=r+g+b;mean+=total;square+=total*total;
 }
 const count=grid*grid;return{rgb,mask,backgroundCoverage:mask.reduce((a,b)=>a+b,0)/count,variance:Math.max(0,square/count-(mean/count)**2)};
}
