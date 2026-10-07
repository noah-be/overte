// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {prepareSource,methods} from '../native-input/web-editor/prepare.mjs';
const [qml,cpp,template]=await Promise.all(['./tablet-capture.qml','../native-input/native-input.cpp','../native-input/web-editor/editor-fixture.template.qml'].map(path=>readFile(new URL(path,import.meta.url),'utf8')));
test('serialized authentic editor registers every current native text dependency',()=>{
 const fixture=prepareSource(qml,cpp,template);
 for(const method of methods){const actual=qml.match(new RegExp('    function '+method+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'))[0];assert(fixture.includes(actual));}
 assert(!fixture.includes('__PRODUCTION_METHODS__'));
 assert(fixture.includes('commitWebPasswordText:function('));
 assert(fixture.includes('measuredNativeInput.commitWebPasswordText('));
});
test('old scalar wrapper counterfactual refuses before compiling or delivery',()=>{
 const old=template.replaceAll('commitWebPasswordText','commitWebPasswordScalar');
 assert.throws(()=>prepareSource(qml,cpp,old),/Actual fixture registration commitWebPasswordText/);
});
test('missing C++ registration refuses before compiling or delivery',()=>{
 assert.throws(()=>prepareSource(qml,cpp.replace('Q_INVOKABLE bool commitWebPasswordText(','bool commitWebPasswordText('),template),/Actual C\+\+ registration/);
});
test('lost template marker and missing helper are rejected',()=>{
 assert.throws(()=>prepareSource(qml,cpp,template.replace('__PRODUCTION_METHODS__','')),/Expected values/);
 assert.throws(()=>prepareSource(qml.replace('function passwordTextValid(', 'function missingPasswordTextValid('),cpp,template),/Current native editor dependency/);
});
test('actual production C++ whole-event method compiled control contracts',()=>{
 execFileSync('python3',[fileURLToPath(new URL('../native-input/test-native-web-route.py',import.meta.url))],{timeout:20000,stdio:'pipe'});
});
test('real own-child diagnostic streams have strict retention and deadline bounds',()=>{
 execFileSync('python3',[fileURLToPath(new URL('../native-input/web-editor/test-runner.py',import.meta.url))],{timeout:5000,stdio:'pipe'});
});
test('real Linux renderer ownership reaps zombies and orphans with strict refusal bounds',()=>{
 execFileSync('python3',['-B',fileURLToPath(new URL('../native-input/web-editor/test-owned-reaping.py',import.meta.url))],{timeout:20000,maxBuffer:65536,stdio:'pipe'});
});
