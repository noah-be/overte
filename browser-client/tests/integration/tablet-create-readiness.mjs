// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {open} from 'node:fs/promises';
import {constants} from 'node:fs';
import {createHash} from 'node:crypto';

export const PREFIX='BROWSER_CREATE_READINESS ';

// The script is fixed and read-only. No visitor text, URL, selector, source or
// command is interpolated into it. Its result remains in the owned private log.
export const CREATE_READINESS_QUERY=String.raw`(function(){
 var path=String(location.pathname),route=/\/system\/create\/entityProperties\/html\/entityProperties\.html$/.test(path)?'properties':/\/system\/create\/entityList\/html\/entityList\.html$/.test(path)?'list':null;
 if(!route)return null;
 function elementRect(e){if(!e)return null;var r=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:r.x,y:r.y,width:r.width,height:r.height,visible:r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden',enabled:e.disabled!==true&&!(e.getAttribute&&e.getAttribute('disabled')==='disabled')};}
 function rect(id){return elementRect(document.getElementById(id));}
 function visibleOne(selector){var list=document.querySelectorAll(selector),found=[];if(list.length>64)return null;for(var i=0;i<list.length&&i<64;i++){var r=elementRect(list[i]);if(r&&r.visible)found.push(r);}return found.length===1?found[0]:null;}
 var fonts=[],required=['Raleway-Regular','Raleway-Bold','FiraSans-SemiBold'];
 if(document.fonts)document.fonts.forEach(function(f){if(fonts.length<16)fonts.push({family:String(f.family).slice(0,64),status:String(f.status)});});
 var labels=document.querySelectorAll('#properties-pages label'),rows=document.querySelectorAll('#entity-table-body tr');
 var out={route:route,readyState:String(document.readyState),eventBridge:!!(window.EventBridge&&typeof EventBridge.emitWebEvent==='function'),fontsStatus:document.fonts?String(document.fonts.status):'unavailable',fonts:fonts,requiredFonts:required.map(function(f){return {family:f,loaded:!!document.fonts&&document.fonts.check('13px '+f)};}),viewport:{width:innerWidth,height:innerHeight},labelCount:Math.min(labels.length,4096),rowCount:Math.min(rows.length,4096),controls:{}};
 var ids=route==='properties'?['property-name','property-id','tab-base','tab-shape','tab-spatial','property-color','property-color-red','property-color-green','property-color-blue','property-localDimensions-x','property-localDimensions-y','property-localDimensions-z']:['filter-search','delete','entity-table-header','entity-table-body'];
 ids.forEach(function(id){out.controls[id]=rect(id);});
 if(route==='properties'){out.section=typeof currentTab==='string'&&['base','shape','spatial'].indexOf(currentTab)>=0?currentTab:null;var swatch=document.getElementById('property-color');out.controls['section-title']=out.section?visibleOne({'base':'#properties-base .labelTabHeader','shape':'#properties-shape .labelTabHeader','spatial':'#properties-spatial .labelTabHeader'}[out.section]):null;out.colorPickerActive=!!(swatch&&swatch.getAttribute&&swatch.getAttribute('active')==='true');out.controls['picker-red']=visibleOne('.colpick_rgb_r input');out.controls['picker-green']=visibleOne('.colpick_rgb_g input');out.controls['picker-blue']=visibleOne('.colpick_rgb_b input');var id=document.getElementById('property-id');var value=id?String(id.value||id.textContent||'').trim():'';out.selectedUUID=/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)?value:null;}
 if(route==='list'){
  function count(id){var e=document.getElementById(id),v=e?String(e.textContent||'').trim():'';return /^\d{1,4}$/.test(v)&&Number(v)<=4096?Number(v):null;}
  out.visibleEntityCount=count('visible-entities-count');out.selectedEntityCount=count('selected-entities-count');out.visibleRows=[];
  if(rows.length<=64)for(var j=0;j<rows.length;j++){
   var row=rows[j],id=row.dataset?String(row.dataset.entityID||''):'',r=elementRect(row);
   if(/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(id)&&r&&r.visible)out.visibleRows.push({id:id,rect:r});
  }
 }
 return out;
})()`;

/** Instrument only a copied test gateway helper, never the shipping source. */
export function instrumentCreateReadiness(qml){
 assert(typeof qml==='string'&&qml.length<128*1024);
 const marker='    function fromScript(message) {';
 const capture='                var item=target();activeCapture=message;';
 assert.equal(qml.split(marker).length,2,'The reviewed capture helper entry must be unique');
 assert.equal(qml.split(capture).length,2,'The reviewed capture target must be unique');
 assert(!qml.includes(PREFIX),'Refuse repeated audit instrumentation');
 const source=JSON.stringify(CREATE_READINESS_QUERY);
 const functions=`    property var createAuditPending: ({})
    function createAudit(item, message) {
        var budget={nodes:0,views:0};
        function visit(node,depth) {
            if(!node||depth>24||++budget.nodes>4096||node.visible===false)return;
            if(typeof node.runJavaScript==="function"&&budget.views<4) {
                var url=String(node.url||""),route=/\\/system\\/create\\/entityProperties\\/html\\/entityProperties\\.html$/.test(url)?"properties":/\\/system\\/create\\/entityList\\/html\\/entityList\\.html$/.test(url)?"list":null;
                if(route&&!createAuditPending[route]) {
                    budget.views++;createAuditPending[route]=true;
                    var origin=node.mapToItem(item,0,0),width=Number(node.width),height=Number(node.height),loading=typeof node.loading==="boolean"?node.loading:null;
                    node.runJavaScript(${source},function(result){
                        createAuditPending[route]=false;
                        if(!result||result.route!==route||!node.visible||String(node.url||"")!==url)return;
                        console.log("${PREFIX}"+JSON.stringify({sequence:message.sequence,revision:message.revision,web:{x:origin.x,y:origin.y,width:width,height:height,loading:loading},dom:result}));
                    });
                }
            }
            if(node.children)for(var i=0;i<node.children.length;i++)visit(node.children[i],depth+1);
        }
        visit(item,0);
    }
`;
 return qml.replace(marker,functions+marker).replace(capture,capture+'\n                createAudit(item,message);');
}

export function parseCreateReadiness(text){
 assert(typeof text==='string'&&text.length<=4*1024*1024,'The owned readiness log must be bounded');
 const result=[];for(const line of text.split('\n')){const index=line.indexOf(PREFIX);if(index<0)continue;const body=line.slice(index+PREFIX.length);assert(body.length<=16384,'Readiness records must be bounded');const entry=JSON.parse(body);assert(Number.isSafeInteger(entry.sequence)&&entry.sequence>0&&Number.isSafeInteger(entry.revision)&&entry.revision>0);assert(['properties','list'].includes(entry.dom?.route));result.push(entry);if(result.length>32)result.shift();}return result;
}

export async function readCreateWorkerLog(profile){
 const handles=[];try{let dir=await open(profile,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(dir);
  for(const name of ['data','Overte','Interface','Logs']){dir=await open('/proc/self/fd/'+dir.fd+'/'+name,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);handles.push(dir);}
  const file=await open('/proc/self/fd/'+dir.fd+'/overte-log.txt',constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);handles.push(file);const info=await file.stat();assert(info.isFile()&&info.size<=4*1024*1024);const bytes=Buffer.alloc(info.size);const {bytesRead}=await file.read(bytes,0,bytes.length,0);return bytes.subarray(0,bytesRead).toString('utf8');
 }finally{for(const file of handles.reverse())await file.close();}
}

export async function assertRuntimeCreateAudit(profile,shippingSource){
 const dir=await open(profile,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);let file;
 try{file=await open('/proc/self/fd/'+dir.fd+'/tablet-capture.qml',constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);const info=await file.stat();assert(info.isFile()&&info.size<=128*1024);const bytes=Buffer.alloc(info.size);const {bytesRead}=await file.read(bytes,0,bytes.length,0);const source=bytes.subarray(0,bytesRead).toString('utf8');assert.equal(source,instrumentCreateReadiness(shippingSource),'The dedicated test worker must contain the exact reviewed fixed readonly audit before any Create mutation');return createHash('sha256').update(source).digest('hex');}
 finally{await file?.close();await dir.close();}
}

export function readyCreateView(records,frame,route,ownID,section){
 // A DOM callback from a destroyed or preceding tab cannot authorize a newer
 // calibration screenshot; require the exact actually displayed capture.
 const entry=records.findLast(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.dom.route===route);
 if(!entry||entry.web.loading===true)return null;const d=entry.dom;
 if(d.readyState!=='complete'||d.eventBridge!==true||d.fontsStatus!=='loaded'||d.requiredFonts?.length!==3||d.requiredFonts.some(f=>!f.loaded))return null;
 if(route==='properties'){
  if(section!==undefined){assert(['base','shape','spatial','colorPicker'].includes(section),'Unsupported native Create section');if(d.section!==(section==='colorPicker'?'shape':section))return null;}
  if(section==='shape'&&d.controls['property-color']?.visible!==true)return null;
  if(section==='spatial'&&!['x','y','z'].every(axis=>d.controls['property-localDimensions-'+axis]?.visible&&d.controls['property-localDimensions-'+axis]?.enabled))return null;
  if(section==='colorPicker'&&(!d.colorPickerActive||!['red','green','blue'].every(channel=>d.controls['picker-'+channel]?.visible&&d.controls['picker-'+channel]?.enabled)))return null;
  if(d.selectedUUID?.replace(/[{}]/g,'').toLowerCase()!==ownID.replace(/[{}]/g,'').toLowerCase()||d.labelCount<5)return null;
  if(!d.controls['tab-base']?.visible)return null;
  if(section===undefined||section==='base'){if(!['property-name','property-id'].every(id=>d.controls[id]?.visible)||d.controls['property-name'].enabled!==true)return null;}
  else if(!d.controls['section-title']?.visible)return null;
 }else if(d.rowCount<1||!['filter-search','delete','entity-table-header','entity-table-body'].every(id=>d.controls[id]?.visible))return null;
 return entry;
}

export function controlPaintBox(entry,id,frame){
 const r=entry.dom.controls[id],web=entry.web;assert(r?.visible&&entry.dom.viewport.width>0&&entry.dom.viewport.height>0);
 const x=web.x+r.x*web.width/entry.dom.viewport.width,y=web.y+r.y*web.height/entry.dom.viewport.height,width=r.width*web.width/entry.dom.viewport.width,height=r.height*web.height/entry.dom.viewport.height;
 assert([x,y,width,height].every(Number.isFinite)&&x>=0&&y>=0&&width>0&&height>0&&x+width<=frame.width&&y+height<=frame.height,'Control pixels must remain within the actual captured surface');return {x,y,width,height};
}

/** Native section headings can exceed the narrow WebEngine viewport. Only
 * their genuinely visible text is inspected; editable controls remain strict. */
export function headingPaintBox(entry,frame){
 const r=entry.dom.controls['section-title'],web=entry.web,viewport=entry.dom.viewport;
 assert(r?.visible&&[r.x,r.y,r.width,r.height,web.x,web.y,web.width,web.height,viewport.width,viewport.height,frame.width,frame.height].every(Number.isFinite));
 assert(viewport.width>0&&viewport.height>0&&web.width>0&&web.height>0&&r.width>0&&r.height>0&&web.x>=0&&web.y>=0&&web.x+web.width<=frame.width&&web.y+web.height<=frame.height,'Heading viewport must be within the actual captured surface');
 const left=web.x+r.x*web.width/viewport.width,top=web.y+r.y*web.height/viewport.height;
 const right=left+r.width*web.width/viewport.width,bottom=top+r.height*web.height/viewport.height;
 const x=Math.max(web.x,left),y=Math.max(web.y,top),width=Math.min(web.x+web.width,right)-x,height=Math.min(web.y+web.height,bottom)-y;
 assert(width>6&&height>6,'Native heading must have a genuinely visible paint area');return {x,y,width,height};
}

export async function readCreateReadiness(profile){return parseCreateReadiness(await readCreateWorkerLog(profile));}

/** Derive genuine click coordinates only from the exact displayed audit. */
export function controlTabletPoint(entry,id,frame){
 assert(entry.sequence===frame.sequence&&entry.revision===frame.revision,'Native control geometry must match the displayed capture');
 assert(entry.dom.controls[id]?.enabled!==false,'Native control must be editable');
 const rect=entry.dom.controls[id],viewport=entry.dom.viewport;assert(rect&&[rect.x,rect.y,rect.width,rect.height,viewport.width,viewport.height].every(Number.isFinite)&&rect.x>=0&&rect.y>=0&&rect.width>0&&rect.height>0&&rect.x+rect.width<=viewport.width&&rect.y+rect.height<=viewport.height,'Native editable control must be fully visible inside its WebEngine viewport');
 const box=controlPaintBox(entry,id,frame);return boxTabletPoint(box,frame);
}
function boxTabletPoint(box,frame){
 const r=frame.tabletRect;assert(r&&[r.x,r.y,r.width,r.height].every(Number.isFinite)&&r.width>0&&r.height>0&&r.x>=0&&r.y>=0&&r.x+r.width<=frame.width&&r.y+r.height<=frame.height,'Actual native tablet rectangle is required');
 const point=[(box.x+box.width/2-r.x)*480/r.width,(box.y+box.height/2-r.y)*706/r.height];
 assert(point.every(Number.isFinite)&&point[0]>=0&&point[0]<480&&point[1]>=40&&point[1]<706,'Genuine control must be inside the displayed tablet');return point;
}
export function readyFilteredOwnList(records,frame,ownID){
 const entry=readyCreateView(records,frame,'list',ownID);
 if(!entry||entry.dom.visibleEntityCount!==1||!Array.isArray(entry.dom.visibleRows)||entry.dom.visibleRows.length!==1)return null;
 const row=entry.dom.visibleRows[0],canonical=id=>String(id).replace(/[{}]/g,'').toLowerCase();
 if(canonical(row.id)!==canonical(ownID)||!row.rect?.visible||row.rect.enabled===false)return null;
 // Existing editable-control crop bounds apply equally to the exact row.
 const copy={...entry,dom:{...entry.dom,controls:{...entry.dom.controls,ownRow:row.rect}}};
 return {...entry,ownRowPoint:controlTabletPoint(copy,'ownRow',frame)};
}
