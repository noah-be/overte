// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Fixed pinned native ComboBox pixel oracle, serializable into both drivers.
 * No native/QML state is created or read through a scripting shortcut. */
export function measureNativeGraphicsPopup(canvas,rect){
 if(!rect||![rect.x,rect.y,rect.width,rect.height].every(Number.isFinite)||rect.x<0||rect.y<0||rect.width<1||rect.height<1||rect.x+rect.width>canvas.width+1||rect.y+rect.height>canvas.height+1||canvas.width*canvas.height>4_000_000)throw Error('Unsupported native popup canvas bounds');
 const context=canvas.getContext('2d');if(!context)throw Error('Native popup canvas is unavailable');
 const pixels=context.getImageData(0,0,canvas.width,canvas.height).data,rows=[];
 // Inside the pinned225px combo/popup, excluding rounded edges and scrollbar.
 // Closed background is #333/#444; popup background is black at alpha0.9 and
 // its one highlighted delegate is gray128. Neither sliders nor page hover
 // has a187px-wide painted dark/gray four-row popup in this fixed interval.
 for(let y=70;y<400;y++){
  let dark=0,highlight=0,text=0,hash=2166136261;
  for(let x=272;x<459;x++){
   const offset=(Math.min(canvas.height-1,Math.floor(rect.y+y*rect.height/706))*canvas.width+Math.min(canvas.width-1,Math.floor(rect.x+x*rect.width/480)))*4;
   const r=pixels[offset],g=pixels[offset+1],b=pixels[offset+2],a=pixels[offset+3];
   if(a>240&&r<15&&g<15&&b<15)dark++;
   if(a>240&&Math.abs(r-128)<=3&&Math.abs(g-128)<=3&&Math.abs(b-128)<=3)highlight++;
   if(a>240&&r>220&&g>220&&b>220)text++;
   hash=Math.imul(hash^r,16777619);hash=Math.imul(hash^g,16777619);hash=Math.imul(hash^b,16777619);
  }
  rows.push({y,dark,highlight,text,hash:hash>>>0});
 }
 return rows;
}

export function locateNativeGraphicsPopup(rows){
 if(!Array.isArray(rows)||rows.length!==330||rows.some((r,i)=>r.y!==70+i||!['dark','highlight','text'].every(k=>Number.isInteger(r[k])&&r[k]>=0&&r[k]<=187)||!Number.isInteger(r.hash)||r.hash<0||r.hash>0xffffffff))throw Error('Invalid native popup pixel measurements');
 const spans=[];let start=-1,last=-1,painted=0;
 function end(){if(start>=0&&last-start+1>=64&&last-start+1<=244&&painted/(last-start+1)>=.85)spans.push({start,last});start=-1;last=-1;painted=0;}
 for(let i=0;i<rows.length;i++){if(rows[i].dark+rows[i].highlight>=110){if(start>=0&&i-last>5)end();if(start<0)start=i;last=i;painted++;}else if(start>=0&&i-last>5)end();}end();
 const found=[];
 for(const span of spans){const height=span.last-span.start+1,top=rows[span.start].y,rowHeight=(height-2)/4;if(rowHeight<15||rowHeight>60)continue;
  const options=[];
  for(let index=0;index<4;index++){const from=top+1+index*rowHeight,to=top+1+(index+1)*rowHeight;const group=rows.filter(r=>r.y>=Math.ceil(from+2)&&r.y<Math.floor(to-2));const glyphRows=group.filter(r=>r.text>=4).length,paint=group.filter(r=>r.highlight>=110).length;options.push({index,y:(from+to)/2,glyphRows,highlightRows:paint,totalRows:group.length});}
  if(options.some(r=>r.glyphRows<3))continue;
  const selected=options.filter(r=>r.totalRows>0&&r.highlightRows/r.totalRows>=.7);
  if(selected.length!==1||options.some(r=>r.index!==selected[0].index&&r.highlightRows>2))continue;
  let hash=2166136261;for(let i=span.start;i<=span.last;i++)hash=Math.imul(hash^rows[i].hash,16777619);
  found.push({top,height,rowHeight,highlightedIndex:selected[0].index,fingerprint:hash>>>0,options});
 }
 if(found.length>1)throw Error('Ambiguous native resolution popup');return found[0]||null;
}

export function stableNativePopup(previous,current){
 return !!previous?.popup&&!!current?.popup&&previous.revision===current.revision&&current.sequence>previous.sequence&&previous.popup.top===current.popup.top&&previous.popup.height===current.popup.height&&previous.popup.highlightedIndex===current.popup.highlightedIndex&&previous.popup.fingerprint===current.popup.fingerprint;
}
