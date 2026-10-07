// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Compare the original strict full-image oracle, adding bounded authored-pixel
 * diagnostics only. No thresholds, transforms, rendering or pixel edits. */
export function compareRenderedLightImages(a,b){
 for(const value of[a,b])if(!value||!Number.isInteger(value.width)||!Number.isInteger(value.height)||value.width<1||value.height<1||value.width>4096||value.height>4096||!(value.pixels instanceof Uint8ClampedArray||value.pixels instanceof Uint8Array)||value.pixels.length!==value.width*value.height*4)throw Error('Bounded complete RGBA image required');
 if(a.width!==b.width||a.height!==b.height)throw Error('Drawing buffer changed');
 let different=0,maximum=0,foreground=0,changedPixels=0,minX=a.width,minY=a.height,maxX=-1,maxY=-1;
 const changedChannels=[0,0,0,0],sampledPixels=[];
 for(let at=0;at<a.pixels.length;at+=4){
  let changed=false;
  for(let channel=0;channel<4;channel++){
   const delta=Math.abs(a.pixels[at+channel]-b.pixels[at+channel]);
   if(delta){different++;changedChannels[channel]++;changed=true;}
   maximum=Math.max(maximum,delta);
   if(channel!==3&&a.pixels[at+channel]>70)foreground++;
  }
  if(!changed)continue;
  changedPixels++;const pixel=at/4,x=pixel%a.width,y=Math.floor(pixel/a.width);
  minX=Math.min(minX,x);minY=Math.min(minY,y);maxX=Math.max(maxX,x);maxY=Math.max(maxY,y);
  // Only sixteen primitive snapshots survive; never retain either full image.
  if(sampledPixels.length<16){const baselineRGBA=[a.pixels[at],a.pixels[at+1],a.pixels[at+2],a.pixels[at+3]],candidateRGBA=[b.pixels[at],b.pixels[at+1],b.pixels[at+2],b.pixels[at+3]];sampledPixels.push({x,y,baselineRGBA,candidateRGBA});}
 }
 return {different,maximum,foreground,changedPixels,changedChannels,changedPixelBounds:changedPixels?{minX,minY,maxX,maxY}:null,sampledPixels};
}
