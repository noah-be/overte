// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';
import {PEOPLE_AUDIT_PREFIX,PEOPLE_AUDIT_QML,parsePeopleAudit,peopleIgnoreControl,instrumentPeopleAudit} from './tablet-people-audit.mjs';
const peer='{22222222-2222-2222-2222-222222222222}';
function fixture(){const output=[],reads=[];let ignore=false;
 const item={visible:true,opacity:1,width:480,height:706,parent:null,children:[]},pal={visible:true,opacity:1,parent:item,currentlyEditingDisplayName:false,iAmAdmin:false,activeTab:'nearbyTab',nearbyUserModelData:[{sessionId:peer,ignore:false,isPresent:true}],children:[]};item.children=[pal];
 const cell={visible:true,opacity:1,parent:pal,isCheckBox:true,children:[]};pal.children=[cell];
 const name={uuid:peer,visible:false,parent:cell},box={visible:true,opacity:1,parent:cell,checked:false,boxSize:24,isRedCheck:true,enabled:true,width:24,height:24,mapToItem(target){assert.equal(target,item);return{x:400,y:250};}};cell.children=[name,box];
 const ctx={console:{log:text=>output.push(text)},Users:{getIgnoreStatus(id){reads.push(id);assert.equal(id,peer);return ignore;},ignore(){throw Error('Read-only audit must never set native controls');}}};vm.runInNewContext(PEOPLE_AUDIT_QML.replace('    property int peopleAuditCount: 0','    var peopleAuditCount=0;').replace('    property int peopleAuditBytes: 0','    var peopleAuditBytes=0;')+'\nthis.audit=peopleAudit;',ctx);
 return{item,pal,box,output,reads,audit:()=>ctx.audit(item,{sequence:4,revision:2,navigationSequence:7}),setIgnored(value){ignore=value;pal.nearbyUserModelData[0].ignore=value;box.checked=value;}};
}
const frame={sequence:4,revision:2,navigationSequence:7,width:480,height:706,tabletRect:{x:0,y:0,width:480,height:706}};
test('actual fixed QML audit reads hidden NameCard UUID and painted native checkbox without invoking an action',()=>{
 const f=fixture();f.audit();const rows=parsePeopleAudit(f.output.join('\n'));assert.equal(rows.length,1);assert.deepEqual(f.reads,[peer]);const p=peopleIgnoreControl(rows,frame,peer,false);assert.deepEqual(p.rect,{x:400,y:250,width:24,height:24});assert.equal(p.x,412);assert.equal(p.y,262);
 f.setIgnored(true);f.audit();assert(peopleIgnoreControl(parsePeopleAudit(f.output.join('\n')),frame,peer,true));assert.equal(peopleIgnoreControl(parsePeopleAudit(f.output.join('\n')),frame,peer,false),null);
});
test('stale capture/navigation, ambiguous peer and admin rows never authorize a click',()=>{
 const f=fixture();f.audit();const records=parsePeopleAudit(f.output.join('\n'));for(const key of ['sequence','revision','navigationSequence'])assert.equal(peopleIgnoreControl(records,{...frame,[key]:frame[key]+1},peer,false),null);
 const duplicate=structuredClone(records);duplicate[0].rows.push(duplicate[0].rows[0]);assert.equal(peopleIgnoreControl(duplicate,frame,peer,false),null);
 records[0].admin=true;assert.equal(peopleIgnoreControl(records,frame,peer,false),null);
});
test('source bounds, capture clipping and mismatched actual native ignore state refuse',()=>{
 const f=fixture();f.audit();const records=parsePeopleAudit(f.output.join('\n'));records[0].rows[0].nativeIgnore=true;assert.equal(peopleIgnoreControl(records,frame,peer,false),null);records[0].rows[0].nativeIgnore=false;records[0].rows[0].rect.x=475;assert.throws(()=>peopleIgnoreControl(records,frame,peer,false),/entirely fit/);
 assert.throws(()=>parsePeopleAudit('x'.repeat(4*1024*1024+1)));const many=structuredClone(records[0]);many.rows=Array.from({length:33},()=>records[0].rows[0]);assert.throws(()=>parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify(many)));
});
test('bounded QML traversal marks truncation and retains no clickable partial result',()=>{
 const f=fixture();f.item.children.push(...Array.from({length:257},()=>({visible:true,parent:f.item,children:[]})));f.audit();const records=parsePeopleAudit(f.output.join('\n'));assert.equal(records[0].truncated,true);assert.equal(peopleIgnoreControl(records,frame,peer,false),null);
});
test('instrumentation only appends a fixed capture-time read; production source untouched and repeated/unknown hooks refuse',()=>{
 const source=readFileSync(new URL('../../gateway/tablet-capture.qml',import.meta.url),'utf8'),result=instrumentPeopleAudit(source);assert(result.includes(PEOPLE_AUDIT_QML));assert.equal(result.replace(PEOPLE_AUDIT_QML,'').replace('\n                peopleAudit(item,message);',''),source);
 assert.throws(()=>instrumentPeopleAudit(result));assert.throws(()=>instrumentPeopleAudit(source.replace('var item=target();activeCapture=message;','unknown')));
 assert(!PEOPLE_AUDIT_QML.includes('Users.ignore('));assert(!PEOPLE_AUDIT_QML.includes('runJavaScript'));assert(!PEOPLE_AUDIT_QML.includes('click('));
});

test('private audit emission has a hard count/byte cap and unknown schema fields refuse',()=>{
 const f=fixture();for(let i=0;i<700;i++)f.audit();assert.equal(f.output.length,512);assert(Buffer.byteLength(f.output.join('\n'))<=524288+512*PEOPLE_AUDIT_PREFIX.length+512);
 const record=parsePeopleAudit(f.output[0])[0];record.credential='must-not-be-retained';assert.throws(()=>parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify(record)));
});
