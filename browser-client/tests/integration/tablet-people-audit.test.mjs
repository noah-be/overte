// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFileSync} from 'node:fs';
import {PEOPLE_AUDIT_PREFIX,PEOPLE_AUDIT_QML,parsePeopleAudit,peopleIgnoreControl,instrumentPeopleAudit} from './tablet-people-audit.mjs';
const peer='{22222222-2222-2222-2222-222222222222}';
function fixture(qml=PEOPLE_AUDIT_QML){const output=[],reads=[];let ignore=false;
 const item={visible:true,opacity:1,width:480,height:706,parent:null,children:[]},pal={visible:true,opacity:1,parent:item,currentlyEditingDisplayName:false,iAmAdmin:false,activeTab:'nearbyTab',nearbyUserModelData:[{sessionId:peer,ignore:false,isPresent:true}],children:[]};item.children=[pal];
 const cell={visible:true,opacity:1,parent:pal,isCheckBox:true,children:[]};pal.children=[cell];
 const name={uuid:peer,visible:false,parent:cell},box={visible:true,opacity:1,parent:cell,checked:false,boxSize:24,isRedCheck:true,enabled:true,width:24,height:24,mapToItem(target){assert.equal(target,item);return{x:400,y:250};}};cell.children=[name,box];
 const ctx={console:{log:text=>output.push(text)},Users:{getIgnoreStatus(id){reads.push(id);assert.equal(id,peer);return ignore;},ignore(){throw Error('Read-only audit must never set native controls');}}};vm.runInNewContext(qml.replace('    property int peopleAuditCount: 0','    var peopleAuditCount=0;').replace('    property int peopleAuditBytes: 0','    var peopleAuditBytes=0;')+'\nthis.audit=peopleAudit;',ctx);
 return{item,pal,cell,box,output,reads,audit:()=>ctx.audit(item,{sequence:4,revision:2,navigationSequence:7}),setIgnored(value){ignore=value;pal.nearbyUserModelData[0].ignore=value;box.checked=value;}};
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

test('large genuine-shaped Pal subtree is visited once within the unchanged4096 budget and yields the original native checkbox',()=>{
 const f=fixture();let visited=0;
 for(let i=0;i<20;i++){
  const branch={parent:f.pal,children:[]};
  for(let j=0;j<125;j++){const leaf={parent:branch,children:[]};Object.defineProperty(leaf,'nearbyUserModelData',{get(){visited++;return undefined;}});branch.children.push(leaf);}
  f.pal.children.push(branch);
 }
 f.audit();const records=parsePeopleAudit(f.output.join('\n'));
 assert.equal(visited,2500,'Original node recognition must run once per distinct leaf');
 assert.equal(records[0].nodes,2525);assert.equal(records[0].truncated,false);assert.equal(records[0].palCount,1);
 assert.deepEqual(f.reads,[peer]);assert(peopleIgnoreControl(records,frame,peer,false));
});

test('shared/cyclic graph, true node exhaustion and ambiguous Pal still fail closed without a second walk',()=>{
 const duplicate=fixture();duplicate.item.children.push(duplicate.pal);duplicate.audit();assert.equal(parsePeopleAudit(duplicate.output[0])[0].truncated,true);
 const cyclic=fixture();cyclic.cell.children.push(cyclic.cell);cyclic.audit();assert.equal(parsePeopleAudit(cyclic.output[0])[0].truncated,true);
 const big=fixture();for(let i=0;i<40;i++){const branch={parent:big.pal,children:[]};for(let j=0;j<125;j++)branch.children.push({parent:branch,children:[]});big.pal.children.push(branch);}big.audit();const record=parsePeopleAudit(big.output[0])[0];assert.equal(record.nodes,4096);assert.equal(record.truncated,true);assert.equal(peopleIgnoreControl([record],frame,peer,false),null);
 const ambiguous=fixture();ambiguous.item.children.push({...ambiguous.pal,children:[],parent:ambiguous.item});ambiguous.audit();assert.equal(peopleIgnoreControl(parsePeopleAudit(ambiguous.output[0]),frame,peer,false),null);
});

test('similar control outside the discovered Pal ancestry is never inspected as a peer control',()=>{
 const f=fixture();const foreign={parent:f.item,children:[]};Object.defineProperty(foreign,'isCheckBox',{get(){throw Error('Unowned cell predicate must not be evaluated');}});f.item.children.push(foreign);
 f.audit();const records=parsePeopleAudit(f.output[0]);assert.equal(records[0].rows.length,1);assert.deepEqual(f.reads,[peer]);assert(peopleIgnoreControl(records,frame,peer,false));
});

test('original double-walk negative control exhausts4096 on the same2525-node scene that the single-pass auditor accepts',()=>{
 const actual=PEOPLE_AUDIT_QML;
 const start=actual.indexOf('        function visit('),end=actual.indexOf('        function visible(',start);
 const oldVisit="        function visit(node,depth,fn){\n            if(!node||depth>24||budget.nodes>=4096){budget.truncated=true;return;}\n            budget.nodes++;fn(node);\n            if(node.children){if(node.children.length>256)budget.truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,fn);}\n        }\n";
 const old=(actual.slice(0,start)+oldVisit+actual.slice(end))
  .replace('        visit(item,0,null);',"        visit(item,0,function(node){if(Array.isArray(node.nearbyUserModelData)&&typeof node.currentlyEditingDisplayName==='boolean'&&typeof node.iAmAdmin==='boolean'&&visible(node)){if(pals.length<2)pals.push(node);else budget.truncated=true;}});")
  .replace('            cells.forEach(function(entry){\n                if(entry.owner!==pal)return;var cell=entry.cell;',"            visit(pal,0,function(cell){\n                if(cell.isCheckBox!==true||!visible(cell)||!cell.children||cell.children.length>256)return;");
 const f=fixture(old);for(let i=0;i<20;i++){const branch={parent:f.pal,children:[]};for(let j=0;j<125;j++)branch.children.push({parent:branch,children:[]});f.pal.children.push(branch);}
 f.audit();const record=parsePeopleAudit(f.output[0])[0];assert.equal(record.nodes,4096);assert.equal(record.truncated,true);assert.equal(peopleIgnoreControl([record],frame,peer,false),null);
});


test('fixed refusal bits distinguish original null/depth/node/duplicate/child bounds without relaxing truncated click refusal',()=>{
 const cases=[];
 const missing=fixture();missing.item.children.push(null);cases.push([missing,'nullNode']);
 const deep=fixture();let parent=deep.pal;for(let i=0;i<26;i++){const next={parent,children:[]};parent.children.push(next);parent=next;}cases.push([deep,'depthExceeded']);
 const nodes=fixture();for(let i=0;i<40;i++){const branch={parent:nodes.pal,children:[]};for(let j=0;j<125;j++)branch.children.push({parent:branch,children:[]});nodes.pal.children.push(branch);}cases.push([nodes,'nodeLimit']);
 const repeat=fixture();repeat.item.children.push(repeat.pal);cases.push([repeat,'repeatedNode']);
 const children=fixture();children.item.children.push(...Array.from({length:257},()=>({parent:children.item,children:[]})));cases.push([children,'childLimit']);
 for(const [f,reason] of cases){f.audit();const record=parsePeopleAudit(f.output[0])[0];assert.equal(record.truncated,true);assert.deepEqual(Object.entries(record.refusals).filter(([,value])=>value).map(([key])=>key),[reason]);assert.equal(peopleIgnoreControl([record],frame,peer,false),null);}
});

test('original Pal and peer-row limit branches have separate scalar diagnostic bits',()=>{
 const pals=fixture();pals.item.children.push({...pals.pal,parent:pals.item,children:[]},{...pals.pal,parent:pals.item,children:[]});pals.audit();const p=parsePeopleAudit(pals.output[0])[0];assert.equal(p.refusals.palLimit,true);assert.equal(p.truncated,true);assert.equal(peopleIgnoreControl([p],frame,peer,false),null);
 const rows=fixture();for(let i=0;i<32;i++){const cell={visible:true,opacity:1,parent:rows.pal,isCheckBox:true,children:[]},name={uuid:peer,parent:cell},box={...rows.box,parent:cell};cell.children=[name,box];rows.pal.children.push(cell);}rows.audit();const r=parsePeopleAudit(rows.output[0])[0];assert.equal(r.rows.length,32);assert.equal(r.refusals.rowLimit,true);assert.equal(r.truncated,true);assert.equal(peopleIgnoreControl([r],frame,peer,false),null);
});

test('strict optional fixed diagnostic schema preserves old records and never accepts private strings or contradictory refusal',()=>{
 const f=fixture();f.audit();const r=parsePeopleAudit(f.output[0])[0];assert(Object.values(r.refusals).every(value=>value===false));assert(peopleIgnoreControl([r],frame,peer,false));
 const legacy=structuredClone(r);delete legacy.refusals;assert.deepEqual(parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify(legacy)),[legacy]);
 for(const refusals of [{},{...r.refusals,unknown:true},{...r.refusals,depthExceeded:'private data'},{...r.refusals,nodeLimit:1},{...r.refusals,repeatedNode:true}])assert.throws(()=>parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify({...r,refusals})));
 assert(!Object.keys(r.refusals).some(key=>/id|name|url|text|path/i.test(key)));
});


test('existing depth refusal classifies only the original painted ancestry predicate and never admits a click',()=>{
 for(const kind of ['visible','hidden','transparent','throw']){
  const f=fixture();let parent=f.pal;for(let i=0;i<24;i++){const child={parent,children:[]};parent.children.push(child);parent=child;}
  if(kind==='visible')parent.visible=true;
  if(kind==='hidden')parent.visible=false;
  if(kind==='transparent')parent.opacity=0;
  if(kind==='throw')Object.defineProperty(parent,'visible',{get(){throw Error('Private source getter diagnostic');}});
  f.audit();const r=parsePeopleAudit(f.output[0])[0];assert.equal(r.refusals.depthExceeded,true);assert.equal(r.truncated,true);assert.equal(peopleIgnoreControl([r],frame,peer,false),null);
  assert.deepEqual(r.depthVisibility,{depthInvisible:kind==='hidden'||kind==='transparent',depthVisible:kind==='visible',depthUnknown:kind==='throw'});
  assert(!f.output[0].includes('Private source getter diagnostic'));
 }
});

test('extra visibility inspection is capped at32 original rejected-depth branches with unknown on remaining branches',()=>{
 const f=fixture();let parent=f.pal;for(let i=0;i<23;i++){const child={parent,children:[]};parent.children.push(child);parent=child;}
 let reads=0;for(let i=0;i<33;i++){const leaf={parent,children:[]};Object.defineProperty(leaf,'visible',{get(){reads++;return false;}});parent.children.push(leaf);}
 f.audit();const r=parsePeopleAudit(f.output[0])[0];assert.equal(reads,32);assert.deepEqual(r.depthVisibility,{depthInvisible:true,depthVisible:false,depthUnknown:true});assert.equal(r.truncated,true);assert.equal(peopleIgnoreControl([r],frame,peer,false),null);
});

test('optional visibility diagnostics reject unknown text and missing/contradictory branch metadata while accepting original reports',()=>{
 const f=fixture();f.audit();const r=parsePeopleAudit(f.output[0])[0];assert.deepEqual(r.depthVisibility,{depthInvisible:false,depthVisible:false,depthUnknown:false});
 const legacy=structuredClone(r);delete legacy.depthVisibility;delete legacy.refusals;assert.deepEqual(parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify(legacy)),[legacy]);
 for(const depthVisibility of [{},{...r.depthVisibility,privateText:'not-retained'},{...r.depthVisibility,depthInvisible:1},{...r.depthVisibility,depthVisible:true}])assert.throws(()=>parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify({...r,depthVisibility})));
 const truncated={...r,truncated:true,depthVisibility:{...r.depthVisibility,depthUnknown:true}};assert.throws(()=>parsePeopleAudit(PEOPLE_AUDIT_PREFIX+JSON.stringify(truncated)));
});
