// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Execute the authentic-policy QML verifier with authored metadata controls.
// This is an oracle contract, not native Qt or installed Interface execution.
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../native-input/application-key-web/authentic-policy/key-fixture.qml',import.meta.url),'utf8');
function method(name){const start=source.indexOf(' function '+name+'(');assert(start>=0);let p=source.indexOf('{',start)+1,depth=1,quote='',escape=false;for(;depth&&p<source.length;p++){const c=source[p];if(quote){if(escape)escape=false;else if(c==='\\')escape=true;else if(c===quote)quote='';}else if(c==='"'||c==="'")quote=c;else if(c==='{')depth++;else if(c==='}')depth--;}assert.equal(depth,0);return source.slice(start,p);}
const match=source.match(/property var cases:\[([\s\S]*?)\n \]/);assert(match);
const cases=vm.runInNewContext('['+match[1]+']');assert.equal(cases.length,8);
function fixture(entry){const rows=[],before={filterPresses:0,filterReleases:0,applicationPresses:0,applicationReleases:0,consumedKeys:0},now={filterPresses:1,filterReleases:1,applicationPresses:entry.global?1:0,applicationReleases:entry.global?1:0,consumedKeys:0};const context={current:entry,before,accepted:true,quiet:0,stats:()=>now,probe:{restart(){}},finishCase:(...row)=>rows.push(row)};vm.createContext(context);vm.runInContext(method('delta')+'\n'+method('verify'),context);return{context,rows,now};}
for(const entry of cases)test('authentic source oracle preserves original five quiet checks for '+entry.kind,()=>{const f=fixture(entry),state={down:1,up:1,untrusted:0,input:entry.editable?1:0};for(let i=0;i<4;i++)f.context.verify(state,true);assert.equal(f.rows.length,0);f.context.verify(state,true);assert.equal(f.rows.length,1);assert.equal(f.rows[0][0],true);});
for(const kind of ['web-disabled','web-noneditable','web-readonly'])test(kind+' cannot approve an accidental native global shortcut',()=>{const entry=cases.find(row=>row.kind===kind);assert(!entry.global);const f=fixture(entry);f.now.applicationPresses=1;f.now.applicationReleases=1;for(let i=0;i<8;i++)f.context.verify({down:1,up:1,untrusted:0,input:0},true);assert.equal(f.rows.length,0);});
test('unconsumed QML shortcut still requires exactly one Application pair',()=>{const f=fixture(cases.find(row=>row.kind==='qml-unconsumed'));for(const count of [0,2]){f.now.applicationPresses=count;f.now.applicationReleases=count;for(let i=0;i<8;i++)f.context.verify({},true);assert.equal(f.rows.length,0);}});
