// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
export const PEOPLE_AUDIT_PREFIX='BROWSER_TABLET_PEOPLE_AUDIT ';
// BrowserTablet acknowledges only frame/revision. The navigation generation
// comes from the actual outgoing navigation command, never an invented ACK field.
export function createPeopleFrameAcknowledgement(){
 let navigation=0;
 const positive=value=>Number.isSafeInteger(value)&&value>0;
 return function observe(message,frames){
  if(!message||message.type!=='tablet'||!positive(message.sequence))return null;
  if(['open','home','back','close'].includes(message.action)){
   if(message.sequence>navigation)navigation=message.sequence;
   return null;
  }
  if(message.action!=='frameAck'||message.displayed!==true||!navigation||message.sequence<=navigation
    ||!positive(message.revision)||!positive(message.frameSequence)||!Array.isArray(frames)||frames.length>16)return null;
  if(message.navigationSequence!==undefined&&message.navigationSequence!==navigation)return null;
  const candidates=frames.filter(frame=>frame?.type==='tablet'&&frame.kind==='frame'
    &&frame.sequence===message.frameSequence&&frame.revision===message.revision&&frame.navigationSequence===navigation);
  return candidates.length===1?candidates[0]:null;
 };
}
export const PEOPLE_AUDIT_QML=String.raw`    property int peopleAuditCount: 0
    property int peopleAuditBytes: 0
    function peopleAudit(item,message) {
        if(peopleAuditCount>=512||peopleAuditBytes>=524288)return;
        var budget={nodes:0,truncated:false},refusals={nullNode:false,depthExceeded:false,nodeLimit:false,repeatedNode:false,childLimit:false,palLimit:false,rowLimit:false,homeButtonLimit:false},paintedTraversal={prunedInvisible:0,visibilityUnknown:false,ownerRefused:false},depthVisibility={depthInvisible:false,depthVisible:false,depthUnknown:false},depthVisibilityReads=0,pals=[],rows=[],cells=[],homeButtons=[],seen=new Set();
        function excludedPaintedAncestry(node){
            var n=node,path=new Set(),witness=false;
            for(var d=0;n&&d<32;d++,n=n.parent){
                if(path.has(n))return false;path.add(n);
                if(n.visible===false||n.opacity===0)witness=true;
                if(n===item)return witness;
            }
            return false;
        }
        function visit(node,depth,owner,expectedParent){
            if(!node){budget.truncated=true;refusals.nullNode=true;return;}
            if(budget.nodes>=4096){budget.truncated=true;refusals.nodeLimit=true;return;}
            if(seen.has(node)){budget.truncated=true;refusals.repeatedNode=true;return;}
            seen.add(node);budget.nodes++;
            var painted;
            try{
                if(node!==item&&node.parent!==expectedParent){budget.truncated=true;paintedTraversal.ownerRefused=true;return;}
                painted=visible(node);
                if(painted===false){
                    if(excludedPaintedAncestry(node)){paintedTraversal.prunedInvisible++;return;}
                    budget.truncated=true;paintedTraversal.visibilityUnknown=true;return;
                }
                if(painted!==true){budget.truncated=true;paintedTraversal.visibilityUnknown=true;return;}
            }catch(error){budget.truncated=true;paintedTraversal.visibilityUnknown=true;return;}
            if(depth>24){
                budget.truncated=true;refusals.depthExceeded=true;
                if(depthVisibilityReads>=32)depthVisibility.depthUnknown=true;
                else {depthVisibilityReads++;depthVisibility.depthVisible=true;}
                return;
            }
            if(Array.isArray(node.nearbyUserModelData)&&typeof node.currentlyEditingDisplayName==='boolean'&&typeof node.iAmAdmin==='boolean'&&visible(node)){
                if(pals.length<2)pals.push(node);else {budget.truncated=true;refusals.palLimit=true;}owner=node;
            }
            if(node.text==='PEOPLE'&&node.sortOrder===7&&typeof node.isActive==='boolean'&&typeof node.buttonIndex==='number'&&visible(node)){if(homeButtons.length<2)homeButtons.push(node);else {budget.truncated=true;refusals.homeButtonLimit=true;}}
            // Hidden branches cannot contain an original painted control. The
            // direct hidden NameCard UUID read below remains unchanged.
            if(owner&&node.isCheckBox===true&&visible(node)&&node.children&&node.children.length<=256)cells.push({owner:owner,cell:node});
            if(node.children){if(node.children.length>256){budget.truncated=true;refusals.childLimit=true;}for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,owner,node);}
        }
        function visible(node){var n=node;for(var d=0;n&&d<32;d++,n=n.parent){if(n.visible===false||n.opacity===0)return false;if(n===item)return true;}return false;}
        function uuid(value){return typeof value==='string'&&/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)?value:null;}
        function rect(node){var p=node.mapToItem(item,0,0),r={x:Number(p.x),y:Number(p.y),width:Number(node.width),height:Number(node.height)};if(![r.x,r.y,r.width,r.height].every(function(n){return isFinite(n)&&Math.abs(n)<=65536;})||r.width<=0||r.height<=0)return null;return r;}
        visit(item,0,null);
        var pal=pals.length===1?pals[0]:null;
        if(pal&&pal.activeTab==='nearbyTab'&&pal.nearbyUserModelData.length<=32){
            cells.forEach(function(entry){
                if(entry.owner!==pal)return;var cell=entry.cell;
                var names=[],checks=[];
                for(var i=0;i<cell.children.length;i++){var child=cell.children[i];if(uuid(child.uuid))names.push(child.uuid);if(typeof child.checked==='boolean'&&child.boxSize===24&&child.isRedCheck===true&&visible(child))checks.push(child);}
                if(names.length!==1||checks.length!==1)return;
                var model=pal.nearbyUserModelData.filter(function(row){return row&&row.sessionId===names[0];});
                if(model.length!==1)return;var checkbox=checks[0],r=rect(checkbox);if(!r)return;
                if(rows.length>=32){budget.truncated=true;refusals.rowLimit=true;return;}
                rows.push({sessionId:names[0],ignore:model[0].ignore===true,nativeIgnore:Users.getIgnoreStatus(names[0])===true,checked:checkbox.checked===true,enabled:checkbox.enabled===true,visible:model[0].isPresent===true,rect:r});
            });
        }
        var body=JSON.stringify({version:1,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,scope:'native-people-nearby',palCount:pals.length,activeTab:pal&&pal.activeTab==='nearbyTab'?'nearby':'other',admin:pal?pal.iAmAdmin:null,nodes:budget.nodes,truncated:budget.truncated,refusals:refusals,depthVisibility:depthVisibility,paintedTraversal:paintedTraversal,rows:rows,homeButtonCount:homeButtons.length,homeButton:homeButtons.length===1?{enabled:homeButtons[0].enabled===true,rect:rect(homeButtons[0])}:null});
        if(body.length>16384||peopleAuditBytes+body.length>524288)return;peopleAuditCount++;peopleAuditBytes+=body.length;
        console.log("BROWSER_TABLET_PEOPLE_AUDIT "+body);
    }
`;
export function instrumentPeopleAudit(qml){
 assert(typeof qml==='string'&&qml.length<=128*1024&&!qml.includes(PEOPLE_AUDIT_PREFIX));
 const marker='    function fromScript(message) {',capture='                var item=target();activeCapture=message;';
 assert.equal(qml.split(marker).length,2);assert.equal(qml.split(capture).length,2);
 return qml.replace(marker,PEOPLE_AUDIT_QML+marker).replace(capture,capture+'\n                peopleAudit(item,message);');
}
const uuid=value=>typeof value==='string'&&/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value);
const keys=(value,allowed)=>{assert(value&&typeof value==='object'&&!Array.isArray(value));assert(Object.keys(value).every(k=>allowed.includes(k)));};
const number=(v,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&v>=0&&v<=max;
export const canonicalPeopleID=value=>{assert(uuid(value));return value.replace(/[{}]/g,'').toLowerCase();};
export function parsePeopleAudit(text){
 assert(typeof text==='string'&&Buffer.byteLength(text)<=4*1024*1024);const entries=[];
 for(const line of text.split('\n')){const at=line.indexOf(PEOPLE_AUDIT_PREFIX);if(at<0)continue;const body=line.slice(at+PEOPLE_AUDIT_PREFIX.length);assert(Buffer.byteLength(body)<=16384);const r=JSON.parse(body);keys(r,['version','sequence','revision','navigationSequence','scope','palCount','activeTab','admin','nodes','truncated','refusals','depthVisibility','paintedTraversal','rows','homeButtonCount','homeButton']);
  assert(r.version===1&&number(r.sequence)&&r.sequence>0&&number(r.revision)&&r.revision>0&&number(r.navigationSequence));assert(r.scope==='native-people-nearby'&&number(r.palCount,2)&&number(r.nodes,4096)&&typeof r.truncated==='boolean'&&['nearby','other'].includes(r.activeTab)&&[true,false,null].includes(r.admin));assert(Array.isArray(r.rows)&&r.rows.length<=32);
  if(r.refusals!==undefined){const fields=['nullNode','depthExceeded','nodeLimit','repeatedNode','childLimit','palLimit','rowLimit',...(r.homeButtonCount!==undefined?['homeButtonLimit']:[])];keys(r.refusals,fields);assert(Object.keys(r.refusals).length===fields.length&&fields.every(key=>typeof r.refusals[key]==='boolean'));assert(!fields.some(key=>r.refusals[key])||r.truncated===true);}
  if(r.depthVisibility!==undefined){const fields=['depthInvisible','depthVisible','depthUnknown'];keys(r.depthVisibility,fields);assert(Object.keys(r.depthVisibility).length===fields.length&&fields.every(key=>typeof r.depthVisibility[key]==='boolean'));assert(!fields.some(key=>r.depthVisibility[key])||(r.truncated===true&&r.refusals?.depthExceeded===true));}
  if(r.paintedTraversal!==undefined){keys(r.paintedTraversal,['prunedInvisible','visibilityUnknown','ownerRefused']);assert(Object.keys(r.paintedTraversal).length===3&&number(r.paintedTraversal.prunedInvisible,4096)&&typeof r.paintedTraversal.visibilityUnknown==='boolean'&&typeof r.paintedTraversal.ownerRefused==='boolean');assert(!(r.paintedTraversal.visibilityUnknown||r.paintedTraversal.ownerRefused)||r.truncated===true);}
  if(r.homeButtonCount!==undefined||r.homeButton!==undefined){assert(r.homeButtonCount!==undefined&&r.homeButton!==undefined&&number(r.homeButtonCount,2));if(r.homeButton){keys(r.homeButton,['enabled','rect']);assert(typeof r.homeButton.enabled==='boolean');if(r.homeButton.rect){keys(r.homeButton.rect,['x','y','width','height']);assert(['x','y','width','height'].every(k=>typeof r.homeButton.rect[k]==='number'&&Number.isFinite(r.homeButton.rect[k])&&Math.abs(r.homeButton.rect[k])<=65536));assert(r.homeButton.rect.width>0&&r.homeButton.rect.height>0);}}else assert(r.homeButton===null);}
  for(const row of r.rows){keys(row,['sessionId','ignore','nativeIgnore','checked','enabled','visible','rect']);keys(row.rect,['x','y','width','height']);assert(uuid(row.sessionId)&&['ignore','nativeIgnore','checked','enabled','visible'].every(k=>typeof row[k]==='boolean'));assert(row.rect&&['x','y','width','height'].every(k=>typeof row.rect[k]==='number'&&Number.isFinite(row.rect[k])&&Math.abs(row.rect[k])<=65536));assert(row.rect.width>0&&row.rect.height>0);}
  entries.push(r);if(entries.length>32)entries.shift();
 }return entries;
}
export function peopleIgnoreControl(records,frame,peerID,ignored){
 assert(typeof ignored==='boolean');const id=canonicalPeopleID(peerID);
 const r=records.findLast(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.navigationSequence===frame.navigationSequence);
 if(!r||r.truncated||r.palCount!==1||r.activeTab!=='nearby'||r.admin!==false)return null;
 const matches=r.rows.filter(row=>canonicalPeopleID(row.sessionId)===id);if(matches.length!==1)return null;
 const row=matches[0];if(!row.visible||!row.enabled||row.ignore!==ignored||row.nativeIgnore!==ignored||row.checked!==ignored)return null;
 const box=row.rect;assert(frame.tabletRect&&['width','height'].every(k=>Number.isSafeInteger(frame[k])&&frame[k]>0&&frame[k]<=4096));
 assert(box.x>=0&&box.y>=0&&box.x+box.width<=frame.width&&box.y+box.height<=frame.height,'Ignore control must entirely fit the acknowledged native capture');
 return {x:box.x+box.width/2,y:box.y+box.height/2,rect:box,sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence};
}

export function peopleHomeControl(records,frame){
 if(!frame||!frame.tabletRect||!number(frame.width,4096)||!number(frame.height,4096)||frame.width<1||frame.height<1)return null;
 const r=records.findLast(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.navigationSequence===frame.navigationSequence);
 if(!r||r.truncated||r.palCount!==0||r.homeButtonCount!==1||!r.homeButton?.enabled||!r.homeButton.rect)return null;
 const box=r.homeButton.rect;if(box.x<0||box.y<0||box.x+box.width>frame.width||box.y+box.height>frame.height)return null;
 return {x:box.x+box.width/2,y:box.y+box.height/2,rect:{...box},sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence};
}
// Serialize the exact existing audited parser/qualifier and its tiny dependencies.
export function peopleAuditBrowserBindingsSource(){
 return 'const assert=value=>{if(!value)throw Error("Owned native People audit refused");};const Buffer={byteLength:value=>new TextEncoder().encode(value).length};const PEOPLE_AUDIT_PREFIX='+JSON.stringify(PEOPLE_AUDIT_PREFIX)+';const keys=('+keys.toString()+');const number=('+number.toString()+');const uuid=('+uuid.toString()+');const canonicalPeopleID=('+canonicalPeopleID.toString()+');const parsePeopleAudit=('+parsePeopleAudit.toString()+');const peopleIgnoreControl=('+peopleIgnoreControl.toString()+');const peopleHomeControl=('+peopleHomeControl.toString()+');';
}

export function encodeValidatedPeopleRecords(records){
 assert(Array.isArray(records)&&records.length<=32);
 const text=records.map(record=>PEOPLE_AUDIT_PREFIX+JSON.stringify(record)).join('\n');
 assert(Buffer.byteLength(text)<=32*(16384+256));
 assert.equal(parsePeopleAudit(text).length,records.length);
 return text;
}
