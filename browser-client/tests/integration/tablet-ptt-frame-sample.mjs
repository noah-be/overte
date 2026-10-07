// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Fixed authored test observer only. Serialize these pure functions directly in
// locator.evaluate; do not yield between committed-frame and canvas reads.
export function currentPttFrameMetadata(){
 const frame=window.__pttAudit.frame;
 return frame?{sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,
  width:frame.width,height:frame.height,tabletRect:frame.tabletRect}:null;
}
export function samplePttDisplayedControl(el,point){
 const frame=window.__pttAudit.frame;
 if(!frame)return {refusal:'no-displayed-frame'};
 if(frame.sequence!==point.sequence)return {refusal:'frame-sequence-changed'};
 if(frame.revision!==point.revision)return {refusal:'frame-revision-changed'};
 if(frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-navigation-changed'};
 const rect=point.rect,x=Math.floor(rect.x*el.width/frame.width),y=Math.floor(rect.y*el.height/frame.height),width=Math.ceil(rect.width*el.width/frame.width),height=Math.ceil(rect.height*el.height/frame.height);
 const numbers=[x,y,width,height,el.width,el.height,frame.width,frame.height];
 if(!numbers.every(Number.isSafeInteger)||width<8||height<8||width>256||height>256||width*height>65536||x<0||y<0||x+width>el.width||y+height>el.height)return {refusal:'mapped-control-out-of-bounds'};
 const image=el.getContext('2d').getImageData(x,y,width,height);
 // JS executes synchronously: neither an ACK message nor its canvas draw can
 // interleave inside this task. Retain the guard even for an authored trap.
 if(window.__pttAudit.frame!==frame||frame.sequence!==point.sequence||frame.revision!==point.revision||frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,frame:{sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,width:frame.width,height:frame.height},canvas:{width:el.width,height:el.height},image:{width,height,rgba:Array.from(image.data)},nativePNG:frame.data};
}
export function freshPttClickCoordinates(el,point){
 const frame=window.__pttAudit.frame;
 if(!frame)return {refusal:'no-displayed-frame'};
 if(frame.sequence!==point.sequence)return {refusal:'frame-sequence-changed'};
 if(frame.revision!==point.revision)return {refusal:'frame-revision-changed'};
 if(frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-navigation-changed'};
 const box=el.getBoundingClientRect();
 if(![box.x,box.y,box.width,box.height,frame.width,frame.height,point.x,point.y].every(Number.isFinite)||box.width<=0||box.height<=0||frame.width<=0||frame.height<=0||point.x<0||point.y<0||point.x>=frame.width||point.y>=frame.height)return {refusal:'canvas-bounds-refused'};
 if(window.__pttAudit.frame!==frame||frame.sequence!==point.sequence||frame.revision!==point.revision||frame.navigationSequence!==point.navigationSequence)return {refusal:'frame-changed-during-sample'};
 return {refusal:null,x:box.x+point.x/frame.width*box.width,y:box.y+point.y/frame.height*box.height};
}
export function incrementPttRefusal(counts,reason){
 const allowed=['no-displayed-frame','native-control-not-qualified','frame-sequence-changed','frame-revision-changed','frame-navigation-changed','frame-changed-during-sample','mapped-control-out-of-bounds','canvas-bounds-refused'];
 if(!allowed.includes(reason))throw Error('Unknown PTT calibration refusal');
 const previous=counts[reason]??0;if(!Number.isSafeInteger(previous)||previous<0||previous>=1000000)throw Error('Invalid PTT calibration refusal count');counts[reason]=previous+1;
}
