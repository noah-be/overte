// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {readFile,writeFile} from'node:fs/promises';import assert from'node:assert/strict';import{createHash}from'node:crypto';import{fileURLToPath}from'node:url';
export const methods=['cancelTextInput','currentTextTarget','failTextInput','finishTextInput','startWebText','passwordTextValid','continuePasswordText'];
export function prepareSource(qml,cpp,template){
 const production=methods.map(name=>{const result=qml.match(new RegExp('    function '+name+'\\([^\\n]*\\) \\{[\\s\\S]*?\\n    \\}'));assert(result,'Current native editor dependency '+name);return result[0];}).join('\n');
 const fixture=template.replace('__PRODUCTION_METHODS__',production);assert.equal(template.split('__PRODUCTION_METHODS__').length,2);
 const names=[...new Set([...production.matchAll(/nativeInput\.(commitWeb\w+)\(/g)].map(m=>m[1]))];
 for(const name of names){assert(template.includes(name+':function('),'Actual fixture registration '+name);assert(template.includes('measuredNativeInput.'+name+'('),'Actual fixture forwarding '+name);assert(cpp.includes('Q_INVOKABLE bool '+name+'('),'Actual C++ registration '+name);}
 return fixture;
}
if(process.argv[1]===fileURLToPath(import.meta.url)){
 assert.equal(process.argv.length,3,'Use one owned output filename');
 const [qml,cpp,template]=await Promise.all(['../../gateway/tablet-capture.qml','../native-input.cpp','./editor-fixture.template.qml'].map(p=>readFile(new URL(p,import.meta.url),'utf8')));
 const fixture=prepareSource(qml,cpp,template);await writeFile(process.argv[2],fixture,{flag:'wx',mode:0o600});
 console.log(JSON.stringify({fixtureSHA256:createHash('sha256').update(fixture).digest('hex'),productionMethods:methods}));
}
