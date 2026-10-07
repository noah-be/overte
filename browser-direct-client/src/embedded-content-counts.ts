// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
/** Snapshot only the existing bounded records. No URL/digest is returned or retained. */
export function embeddedContentCounts(entries:Iterable<{key:string;bytes:number}>){
 const contents=new Map<string,number>();let count=0,bytes=0;
 for(const entry of entries){
  if(++count>256)throw Error('Embedded content observer exceeds 256 entries');
  if(typeof entry.key!=='string'||entry.key.length>128||!Number.isSafeInteger(entry.bytes)||entry.bytes<1||entry.bytes>8*1024*1024)throw Error('Invalid embedded content observer record');
  const match=/^[1-9]\d*\|(image\/(?:png|jpeg|bmp|webp))\|([a-f0-9]{64})$/.exec(entry.key);if(!match)throw Error('Invalid embedded content observer identity');
  bytes+=entry.bytes;if(bytes>128*1024*1024)throw Error('Embedded content observer exceeds 128 MiB');
  const content=match[1]+'|'+match[2],prior=contents.get(content);
  if(prior!==undefined&&prior!==entry.bytes)throw Error('Inconsistent embedded content byte identity');
  contents.set(content,entry.bytes);
 }
 const distinctContentBytes=[...contents.values()].reduce((sum,value)=>sum+value,0);
 return {distinctContents:contents.size,repeatedContentEntries:count-contents.size,distinctContentBytes,repeatedContentBytes:bytes-distinctContentBytes};
}
