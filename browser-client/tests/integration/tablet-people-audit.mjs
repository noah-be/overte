// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
export const PEOPLE_AUDIT_PREFIX='BROWSER_TABLET_PEOPLE_AUDIT ';
export const PEOPLE_AUDIT_QML=String.raw`    property int peopleAuditCount: 0
    property int peopleAuditBytes: 0
    function peopleAudit(item,message) {
        if(peopleAuditCount>=512||peopleAuditBytes>=524288)return;
        var budget={nodes:0,truncated:false},pals=[],rows=[];
        function visit(node,depth,fn){
            if(!node||depth>24||budget.nodes>=4096){budget.truncated=true;return;}
            budget.nodes++;fn(node);
            if(node.children){if(node.children.length>256)budget.truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,fn);}
        }
        function visible(node){var n=node;for(var d=0;n&&d<32;d++,n=n.parent){if(n.visible===false||n.opacity===0)return false;if(n===item)return true;}return false;}
        function uuid(value){return typeof value==='string'&&/^\{?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\}?$/i.test(value)?value:null;}
        function rect(node){var p=node.mapToItem(item,0,0),r={x:Number(p.x),y:Number(p.y),width:Number(node.width),height:Number(node.height)};if(![r.x,r.y,r.width,r.height].every(function(n){return isFinite(n)&&Math.abs(n)<=65536;})||r.width<=0||r.height<=0)return null;return r;}
        visit(item,0,function(node){if(Array.isArray(node.nearbyUserModelData)&&typeof node.currentlyEditingDisplayName==='boolean'&&typeof node.iAmAdmin==='boolean'&&visible(node)){if(pals.length<2)pals.push(node);else budget.truncated=true;}});
        var pal=pals.length===1?pals[0]:null;
        if(pal&&pal.activeTab==='nearbyTab'&&pal.nearbyUserModelData.length<=32){
            visit(pal,0,function(cell){
                if(cell.isCheckBox!==true||!visible(cell)||!cell.children||cell.children.length>256)return;
                var names=[],checks=[];
                for(var i=0;i<cell.children.length;i++){var child=cell.children[i];if(uuid(child.uuid))names.push(child.uuid);if(typeof child.checked==='boolean'&&child.boxSize===24&&child.isRedCheck===true&&visible(child))checks.push(child);}
                if(names.length!==1||checks.length!==1)return;
                var model=pal.nearbyUserModelData.filter(function(row){return row&&row.sessionId===names[0];});
                if(model.length!==1)return;var checkbox=checks[0],r=rect(checkbox);if(!r)return;
                if(rows.length>=32){budget.truncated=true;return;}
                rows.push({sessionId:names[0],ignore:model[0].ignore===true,nativeIgnore:Users.getIgnoreStatus(names[0])===true,checked:checkbox.checked===true,enabled:checkbox.enabled===true,visible:model[0].isPresent===true,rect:r});
            });
        }
        var body=JSON.stringify({version:1,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,scope:'native-people-nearby',palCount:pals.length,activeTab:pal&&pal.activeTab==='nearbyTab'?'nearby':'other',admin:pal?pal.iAmAdmin:null,nodes:budget.nodes,truncated:budget.truncated,rows:rows});
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
 for(const line of text.split('\n')){const at=line.indexOf(PEOPLE_AUDIT_PREFIX);if(at<0)continue;const body=line.slice(at+PEOPLE_AUDIT_PREFIX.length);assert(Buffer.byteLength(body)<=16384);const r=JSON.parse(body);keys(r,['version','sequence','revision','navigationSequence','scope','palCount','activeTab','admin','nodes','truncated','rows']);
  assert(r.version===1&&number(r.sequence)&&r.sequence>0&&number(r.revision)&&r.revision>0&&number(r.navigationSequence));assert(r.scope==='native-people-nearby'&&number(r.palCount,2)&&number(r.nodes,4096)&&typeof r.truncated==='boolean'&&['nearby','other'].includes(r.activeTab)&&[true,false,null].includes(r.admin));assert(Array.isArray(r.rows)&&r.rows.length<=32);
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
