// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';import assert from 'node:assert/strict';import vm from 'node:vm';import {readFile}from'node:fs/promises';import{createHash}from'node:crypto';
import{buildBrowserGraphicsOverrides,GRAPHICS_SOURCE_SHA256}from'./browser-graphics-overrides.mjs';
const source=await readFile(new URL('./browser-graphics-overrides.mjs',import.meta.url),'utf8');
const fixtures=JSON.parse(await readFile(new URL('../tests/fixtures/native-graphics-2026.04.1/sources.json',import.meta.url),'utf8')).files;
for(const[k,h]of Object.entries(GRAPHICS_SOURCE_SHA256))assert.equal(createHash('sha256').update(fixtures[k]).digest('hex'),h);
const insertion=`    const combo=once(sources['qml/SettingComboBox.qml'],'popup: Popup {','popup: Popup {\\n                    y: root.settingText === \\\"Resolution preset\\\" ? control.height : 0;');\n`;
assert.equal(source.split(insertion).length,2);
const opacityInsertion='    const opaqueCombo=once(combo,\'color: Qt.rgba(0,0,0,0.9)\',\'color: Qt.rgba(0,0,0,root.settingText === "Resolution preset" ? 1 : 0.9)\');\n';
assert.equal(source.split(opacityInsertion).length,2);
const placementSource=source.replace(opacityInsertion,'').replace("'qml/SettingComboBox.qml':opaqueCombo","'qml/SettingComboBox.qml':combo");
assert.equal(createHash('sha256').update(placementSource).digest('hex'),'28f5afdf722d561f8badc639dda23e44d2e986b4a025c78e57fed47ae85bb1ea');
const baseline=placementSource.replace(insertion,'').replace("'qml/SettingComboBox.qml':combo","'qml/SettingComboBox.qml':sources['qml/SettingComboBox.qml']");
assert.equal(createHash('sha256').update(baseline).digest('hex'),'ccb50787e8bc0431b6c13c67de1ebdbddf9abdc5f7123a64b6b061be89712329');
const context=vm.createContext({createHash,GRAPHICS_SOURCE_SHA256});vm.runInContext(baseline.slice(baseline.indexOf('function once('),baseline.indexOf('/** Call at gateway startup')).replace('export function buildBrowserGraphicsOverrides','function buildBrowserGraphicsOverrides'),context);
const channel='overte.browser.graphics.'+'1'.repeat(32),generated=buildBrowserGraphicsOverrides(fixtures,channel),old=JSON.parse(JSON.stringify(context.buildBrowserGraphicsOverrides(fixtures,channel)));
const originalBackground='color: Qt.rgba(0,0,0,0.9)',opaqueBackground='color: Qt.rgba(0,0,0,root.settingText === \"Resolution preset\" ? 1 : 0.9)';
const yBinding='                    y: root.settingText === "Resolution preset" ? control.height : 0;\n';
test('only approved browser Resolution preset popup placement changes; every authentic handler and five other overrides remain exact',()=>{assert.equal(generated['qml/SettingComboBox.qml'].split(yBinding).length,2);assert.equal(generated['qml/SettingComboBox.qml'].replace(opaqueBackground,originalBackground).replace(yBinding,''),fixtures['qml/SettingComboBox.qml']);for(const name of Object.keys(old)){if(name==='qml/SettingComboBox.qml')continue;assert.equal(generated[name],old[name]);}assert.doesNotMatch(generated['qml/SettingComboBox.qml'],/highlightedIndex\s*=(?!=)|forceActiveFocus|Qt\.callLater|Timer\s*\{/);});
test('actual generated y expression follows own ComboBox height and leaves all other native presets unchanged',()=>{const match=generated['qml/SettingComboBox.qml'].match(/y: (root\.settingText === "Resolution preset" \? control\.height : 0);/);assert(match);for(const height of [20,35,50]){assert.equal(vm.runInNewContext(match[1],{root:{settingText:'Resolution preset'},control:{height}}),height);for(const text of ['Graphics preset','Other',''])assert.equal(vm.runInNewContext(match[1],{root:{settingText:text},control:{height}}),0);}});
test('original overlapped click point enters row zero; below-control popup excludes that point without forcing highlight/current values',()=>{const combo={top:100,height:35},clickY=combo.top+combo.height/2,rowHeight=42;const firstRowContains=y=>clickY>=combo.top+y&&clickY<combo.top+y+rowHeight;assert.equal(firstRowContains(0),true);const expression=generated['qml/SettingComboBox.qml'].match(/y: (root\.settingText === "Resolution preset" \? control\.height : 0);/)[1];const y=vm.runInNewContext(expression,{root:{settingText:'Resolution preset'},control:{height:combo.height}});assert.equal(firstRowContains(y),false);assert.equal(y,35);});
test('unknown installed source/channel still refuses before producing overrides',()=>{assert.throws(()=>buildBrowserGraphicsOverrides({...fixtures,'qml/SettingComboBox.qml':fixtures['qml/SettingComboBox.qml']+'\n'},channel),/Unsupported installed/);assert.throws(()=>buildBrowserGraphicsOverrides(fixtures,'foreign'),/Invalid private/);});

test('only Resolution preset popup background becomes opaque; every other native combo retains 0.9 alpha',()=>{
 const combo=generated['qml/SettingComboBox.qml'];assert.equal(combo.split(opaqueBackground).length,2);
 // The source property has no semicolon, matching the original pinned widget.
 const actual=combo.match(/color: (Qt\.rgba\(0,0,0,root\.settingText === "Resolution preset" \? 1 : 0\.9\))/);assert(actual);
 for(const text of ['Resolution preset','Graphics preset','Other','']){
  const rgba=vm.runInNewContext(actual[1],{root:{settingText:text},Qt:{rgba:(r,g,b,a)=>[r,g,b,a]}});
  assert.deepEqual([...rgba],[0,0,0,text==='Resolution preset'?1:.9]);
 }
});
test('opaque popup excludes underlying white description and blue slider contribution without changing dark/row oracle',()=>{
 const compose=(alpha,under)=>under.map(v=>v*(1-alpha));
 for(const under of [[255,255,255],[0,128,255]]){
  assert(compose(.9,under).some(v=>v>=15),'original native translucent background can exceed the unchanged dark threshold');
  assert.deepEqual(compose(1,under),[0,0,0]);
 }
});
