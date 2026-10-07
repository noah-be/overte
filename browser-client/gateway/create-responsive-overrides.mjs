// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {createHash} from 'node:crypto';
import {constants} from 'node:fs';
import {open,writeFile,realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

export const CREATE_LAYOUT_SOURCE_SHA256=Object.freeze({
  "system/create/entityProperties/html/entityProperties.html": "c18c51e1da164423ff0429201bfff3168d32c0e20fbfd519f257435847e34ea6",
  "system/html/css/edit-style.css": "23d94b2461b5ef665a73c66db3a6b843dcb74e9dd230861efc7511ee25eea40a",
  "system/html/css/tabs.css": "ceb37ed1b0853ef469d6788943f4d85dd95bfb706027b8d97e80fef2d4b55967",
  "system/create/entityProperties/html/js/entityProperties.js": "5e31fbdc3e577dd13663c0d9ee429f7c816bf1c7c91f45ea62438a6b575e08d5",
  "system/create/entityProperties/html/js/draggableNumber.js": "0db027332a899e6186309c6e800010a63a08701636a2e1ece3aed8f229a19ff8"
});
const HTML='system/create/entityProperties/html/entityProperties.html';
export const RESPONSIVE_CREATE_CSS=`
/* Owned browser worker: preserve native controls and their event handlers. */
@media (max-width: 600px) {
 #properties-list {min-width:0;max-width:100%;box-sizing:border-box;}
 #properties-list .tabsTableFrame {display:table;table-layout:fixed;width:100%;max-width:100%;}
 /* Native global tbody is display:block; restore the table row group only
    in this owned narrow layout, otherwise its first content cell collapses. */
 #properties-list .tabsTableFrame > tbody {display:table-row-group;}
 #properties-list .tabsFrame {width:32px;}
 #properties-list .tabsPropertiesFrame {width:auto;min-width:0;}
 #properties-list .tabsPropertiesPage, #properties-list .labelTabHeader {min-width:0;max-width:100%;overflow-wrap:break-word;}
 #properties-list .container {flex-flow:column nowrap;min-width:0;box-sizing:border-box;}
 #properties-list .container > label {width:auto;min-width:0;max-width:none;margin-bottom:6px;}
 #properties-list .container > .value {width:100%;min-width:0;}
 #properties-list .container .row {min-width:0;flex-wrap:wrap;}
 #properties-list .xyz.fstuple, #properties-list .pyr.fstuple, #properties-list .vec3rgb.fstuple {
   left:0;width:100%;min-width:0;box-sizing:border-box;gap:18px;padding-left:16px;
 }
 #properties-list .draggable-number.fstuple {left:0;width:0;min-width:0;flex:1 1 0;box-sizing:border-box;}
 #properties-list .draggable-number.fstuple + .draggable-number.fstuple {margin-left:0;}
 #properties-list .draggable-number.fstuple input {right:0;margin:0;}
}
`;
export function responsiveCreateHTML(original){
 if(typeof original!=='string'||createHash('sha256').update(original).digest('hex')!==CREATE_LAYOUT_SOURCE_SHA256[HTML])throw Error('Unsupported installed Create Properties layout version');
 const marker='    </head>';
 if(original.split(marker).length!==2)throw Error('Unsupported installed Create Properties layout version');
 return original.replace(marker,'        <style id="browser-create-responsive-layout">'+RESPONSIVE_CREATE_CSS+'</style>\n'+marker);
}
export function buildResponsiveCreateHTML(sources){
 for(const [name,expected] of Object.entries(CREATE_LAYOUT_SOURCE_SHA256)){
  if(typeof sources[name]!=='string'||createHash('sha256').update(sources[name]).digest('hex')!==expected)
   throw Error('Unsupported installed Create Properties layout version');
 }
 return responsiveCreateHTML(sources[HTML]);
}
async function boundedSource(filename){
 const handle=await open(filename,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
 try{const stat=await handle.stat();if(!stat.isFile()||stat.size>1024*1024)throw Error('Unsupported installed Create Properties source');
  const bytes=Buffer.alloc(1024*1024+1),{bytesRead}=await handle.read(bytes,0,bytes.length,0);
  if(bytesRead>1024*1024)throw Error('Unsupported installed Create Properties source');return bytes.subarray(0,bytesRead).toString('utf8');
 }finally{await handle.close();}
}
/** Cache the exact operator-selected package at startup, then copy only this HTML per visitor. */
export async function loadBrowserCreatePackage(defaultScriptsURL){
 const url=new URL(defaultScriptsURL);
 if(url.protocol!=='file:'||url.host||path.basename(fileURLToPath(url))!=='defaultScripts.js')throw Error('Invalid installed Create Properties path');
 const root=await realpath(path.dirname(fileURLToPath(url))),sources={};
 for(const name of Object.keys(CREATE_LAYOUT_SOURCE_SHA256))sources[name]=await boundedSource(path.join(root,name));
 const generated=buildResponsiveCreateHTML(sources),target=path.join(root,HTML);
 return {sourceHashes:{...CREATE_LAYOUT_SOURCE_SHA256},async prepare(directory){
  const source=path.join(directory,'browser-create-properties.html');
  await writeFile(source,generated,{mode:0o600,flag:'wx'});
  return {readOnlyOverrides:[{source,target}]};
 }};
}
