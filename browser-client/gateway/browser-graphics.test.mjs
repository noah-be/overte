// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import {readFile,mkdtemp,mkdir,rm,writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {buildBrowserGraphicsOverrides,loadBrowserGraphicsPackage,GRAPHICS_SOURCE_SHA256} from './browser-graphics-overrides.mjs';
function signal(){const handlers=new Set();return {connect:fn=>handlers.add(fn),disconnect:fn=>handlers.delete(fn),emit:(...args)=>{for(const fn of handlers)fn(...args);},get count(){return handlers.size;}};}
const channel='overte.browser.graphics.'+'1'.repeat(32);
const defaults={version:1,fieldOfView:70,resolutionPercent:100,localLights:true,cameraClipping:true};
async function fixture(){let now=0;const source=await readFile(new URL('./native-browser-graphics.js',import.meta.url),'utf8'),sent=[],ui=[],received=signal(),subscriptions=[];
    const context=vm.createContext({Messages:{subscribe:value=>subscriptions.push(value),unsubscribe:value=>subscriptions.push('-'+value),messageReceived:received,sendLocalMessage:(name,text)=>ui.push(JSON.parse(text))}});vm.runInContext(source,context);
    const helper=context.createBrowserGraphics({channel,send:value=>sent.push(value),now:()=>now});return {helper,sent,ui,received,subscriptions,advance:ms=>{now+=ms;helper.poll();},elapse:ms=>{now+=ms;},emit:value=>received.emit(channel,JSON.stringify(value),'own',true)};
}
test('native actual Settings adapter requires an effective browser ACK before accepting Qt changes and never writes worker Render defaults',async()=>{
    const {helper,sent,ui,emit}=await fixture();emit({kind:'ready'});assert.equal(sent.length,0);helper.setAuthority(3,true);emit({kind:'ready'});assert.equal(sent.length,1);assert.equal(sent[0].operation,'request');assert.equal(ui.at(-1).ready,false);
    emit({kind:'change',field:'fieldOfView',value:90});assert.equal(sent.length,1);
    helper.receive({action:'graphicsResult',revision:2,schemaVersion:1,requestId:1,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,false);
    helper.receive({action:'graphicsResult',revision:3,schemaVersion:1,requestId:1,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,true);
    emit({kind:'change',field:'resolutionPercent',value:50});assert.equal(sent.length,2);assert.equal(sent[1].field,'resolutionPercent');assert.equal(sent[1].value,50);
    helper.receive({action:'graphicsResult',revision:3,schemaVersion:1,requestId:2,accepted:false,settings:defaults,message:'Actual viewport unavailable'});assert.equal(ui.at(-1).settings.resolutionPercent,100);assert.equal(ui.at(-1).message,'Actual viewport unavailable');helper.close();
});
test('native revocation, replay, unsupported values and expired ACKs do not change approved control state',async()=>{
    const {helper,sent,ui,emit,advance,received,subscriptions}=await fixture();helper.setAuthority(1,true);emit({kind:'ready'});advance(8000);assert.match(ui.at(-1).message,/8 seconds/);helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:1,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,false);
    emit({kind:'ready'});helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:2,accepted:true,settings:defaults});
    for(const value of [{kind:'change',field:'bloom',value:true},{kind:'change',field:'fieldOfView',value:NaN},{kind:'change',field:'resolutionPercent',value:25},{kind:'change',field:'localLights',value:'false'}])emit(value);assert.equal(sent.length,2);
    emit({kind:'change',field:'localLights',value:false});helper.setAuthority(2,false);helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:3,accepted:true,settings:{...defaults,localLights:false}});assert.equal(ui.at(-1).ready,false);helper.setAuthority(-1,true);emit({kind:'ready'});assert.equal(sent.length,3);
    helper.close();helper.close();assert.equal(received.count,0);assert.deepEqual(subscriptions,[channel,'-'+channel]);
});
async function sources(){const fixture=JSON.parse(await readFile(new URL('../tests/fixtures/native-graphics-2026.04.1/sources.json',import.meta.url),'utf8')),out=fixture.files;assert.deepEqual(Object.keys(out).sort(),Object.keys(GRAPHICS_SOURCE_SHA256).sort());for(const[name,hash]of Object.entries(GRAPHICS_SOURCE_SHA256))assert.equal(createHash('sha256').update(out[name]).digest('hex'),hash,'Immutable native source bytes: '+name);return out;}
test('exact installed Settings source retains real slider/switch widgets and other app routes without native Render writes',async()=>{
    const originals=await sources(),generated=buildBrowserGraphicsOverrides(originals,channel);
    assert.match(generated['qml/pages/GraphicsSettings.qml'],/Resolution scale \(%\)/);assert.match(generated['qml/pages/GraphicsSettings.qml'],/minValue: 10;/);assert.match(generated['qml/pages/GraphicsSettings.qml'],/maxValue: 200;/);
    assert.doesNotMatch(generated['qml/pages/GraphicsSettings.qml'],/Render\.|Performance\.|LODManager\./);assert.equal((generated['qml/pages/GraphicsSettings.qml'].match(/SettingSlider \{/g)||[]).length,2);assert.equal((generated['qml/pages/GraphicsSettings.qml'].match(/SettingBoolean \{/g)||[]).length,2);
    assert.match(generated['Settings.qml'],/TabletGeneralPreferences.qml/);assert.match(generated['Settings.qml'],/hifi\/audio\/Audio.qml/);assert.match(generated['Settings.qml'],/EntityScriptQMLAllowlist.qml/);
    const tampered={...originals,'settings.js':originals['settings.js']+'\n'};assert.throws(()=>buildBrowserGraphicsOverrides(tampered,channel),/Unsupported installed/);assert.throws(()=>buildBrowserGraphicsOverrides(originals,'public-or-other-worker'),/private graphics channel/);
});
test('actual generated installed Settings script sends only private local Qt control events and delivers effective ACK to actual tablet QML',async()=>{
    const generated=buildBrowserGraphicsOverrides(await sources(),channel),fromQml=signal(),screenChanged=signal(),ending=signal(),received=signal(),packets=[],local=[];
    const tablet={fromQml,screenChanged,addButton:()=>({clicked:signal(),editProperties:()=>{}}),removeButton:()=>{},sendToQml:value=>packets.push(value),loadQMLSource:()=>{},gotoHomeScreen:()=>{}};
    const context=vm.createContext({Script:{resolvePath:value=>'file:///installed/'+value,scriptEnding:ending},Tablet:{getTablet:()=>tablet},Menu:{menuItemEvent:signal(),addMenuItem:()=>{},removeMenuItem:()=>{}},Desktop:{show:()=>{}},Messages:{subscribe:()=>{},unsubscribe:()=>{},messageReceived:received,sendLocalMessage:(name,text)=>local.push({name,value:JSON.parse(text)})},console:{log:()=>{}}});vm.runInContext(generated['settings.js'],context);
    fromQml.emit({type:'browserGraphicsChange',field:'resolutionPercent',value:50});assert.deepEqual(local,[{name:channel,value:{kind:'change',field:'resolutionPercent',value:50}}]);
    received.emit(channel,JSON.stringify({kind:'effective',sequence:2,ready:true,settings:defaults}),'own',true);assert.equal(packets.at(-1).type,'browserGraphicsState');assert.equal(packets.at(-1).settings.resolutionPercent,100);
    const count=packets.length;received.emit(channel,JSON.stringify({kind:'effective',sequence:1,ready:true,settings:{...defaults,resolutionPercent:50}}),'own',true);assert.equal(packets.length,count,'Stale pre-revocation UI state cannot replace newer effective controls');received.emit('other-worker',JSON.stringify({kind:'effective',settings:defaults}),'other',true);assert.equal(packets.length,count);ending.emit();assert.equal(received.count,0);
});
test('private overrides pin source bytes at startup and create distinct owner channels without modifying installed sources',async()=>{
    const directory=await mkdtemp(path.join(tmpdir(),'overte-graphics-fixture-'));try{
        const scripts=path.join(directory,'installed'),settings=path.join(scripts,'system/settings');await mkdir(path.join(settings,'qml/pages'),{recursive:true});await writeFile(path.join(scripts,'defaultScripts.js'),'// actual default location');const original=await sources();for(const [name,text] of Object.entries(original))await writeFile(path.join(settings,name),text);
        const prepared=await loadBrowserGraphicsPackage(pathToFileURL(path.join(scripts,'defaultScripts.js')));await writeFile(path.join(settings,'settings.js'),'changed after startup');
        const a=path.join(directory,'a'),b=path.join(directory,'b');await mkdir(a);await mkdir(b);const first=await prepared.prepare(a),second=await prepared.prepare(b);assert.notEqual(first.channel,second.channel);assert.equal(first.readOnlyOverrides.length,6);assert.equal(second.readOnlyOverrides.length,6);assert.equal(await readFile(path.join(settings,'settings.js'),'utf8'),'changed after startup');
        assert.match(await readFile(first.readOnlyOverrides[0].source,'utf8'),/browserGraphicsChannel/);assert.equal(first.readOnlyOverrides[0].target,path.join(settings,'settings.js'));await assert.rejects(()=>prepared.prepare(a),/EEXIST/);
    }finally{await rm(directory,{recursive:true,force:true});}
});

test('approval of an already visible page requests fresh effective state and deadline rejects late ACK before the timer polls',async()=>{
    const {helper,sent,ui,emit,elapse}=await fixture();emit({kind:'ready'});helper.setAuthority(1,true);assert.equal(sent.length,1);
    helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:1,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,true);
    helper.setAuthority(2,false);helper.setAuthority(3,true);assert.equal(sent.length,2);assert.equal(sent[1].operation,'request');
    helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:1,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,false);
    elapse(8000);helper.receive({action:'graphicsResult',revision:3,schemaVersion:1,requestId:2,accepted:true,settings:defaults});assert.equal(ui.at(-1).ready,false);assert.match(ui.at(-1).message,/8 seconds/);helper.close();
});

function profilePage(generated,onChange){
    const source=generated['qml/pages/GraphicsSettings.qml'],methods=['publish','resolutionProfileIndex','selectResolutionProfile'];
    const context=vm.createContext({browserReady:false,browserState:{...defaults},browserSettingChanged:onChange,
        resolutionProfileControl:{currentIndex:0,setOptionIndex(index){this.currentIndex=index;}}});
    for(const name of methods){
        const start=source.indexOf('function '+name+'(');assert(start>=0,'Actual generated QML method is required: '+name);
        let depth=0,end=source.indexOf('{',start);
        for(;end<source.length;end++){if(source[end]==='{')depth++;else if(source[end]==='}'&&--depth===0){end++;break;}}
        assert.equal(depth,0);vm.runInContext(source.slice(start,end),context);
    }
    return context;
}

test('actual generated native combo has three explicit presets and truthful Custom; no new graphics wire fields or worker Render writes',async()=>{
    const originals=await sources(),generated=buildBrowserGraphicsOverrides(originals,channel),qml=generated['qml/pages/GraphicsSettings.qml'];
    assert.equal(generated['qml/SettingComboBox.qml'].replace('color: Qt.rgba(0,0,0,root.settingText === \"Resolution preset\" ? 1 : 0.9)','color: Qt.rgba(0,0,0,0.9)').replace('                    y: root.settingText === "Resolution preset" ? control.height : 0;\n',''),originals['qml/SettingComboBox.qml']);
    assert.equal((qml.match(/SettingComboBox \{/g)||[]).length,1);
    assert.match(qml,/options: \["Default \(100%\)", "Balanced \(80%\)", "Faster \(60%\)", "Custom"\]/);
    assert.match(qml,/graphicsPage\.selectResolutionProfile\(index\)/);
    assert.match(qml,/resolutionProfileControl\.setOptionIndex\(resolutionProfileIndex\(\)\)/);
    assert.match(qml,/select one explicitly to reduce pixel workload/);
    assert.doesNotMatch(qml,/Performance\.|Render\.|LODManager\.|switchToAGraphicsPreset/);
    assert.match(generated['Settings.qml'],/browserGraphicsReady=false;browserGraphicsState=message\.settings/);
    const changes=[],page=profilePage(generated,(field,value)=>changes.push({field,value}));
    assert.equal(page.resolutionProfileIndex(),0);assert.equal(changes.length,0);
    page.selectResolutionProfile(1);assert.equal(changes.length,0,'Not approved on construction');
    page.browserReady=true;
    for(const bad of [3,-1,4,1.5,NaN,'1',undefined]){page.resolutionProfileControl.currentIndex=bad;page.selectResolutionProfile(bad);assert.equal(page.resolutionProfileControl.currentIndex,0,'Non-actionable selection restores actual confirmed profile');}
    assert.equal(changes.length,0,'Custom/invalid selector entries must not choose a hidden value');
    for(const [index,percent] of [[1,80],[2,60]]){page.selectResolutionProfile(index);assert.deepEqual(changes.at(-1),{field:'resolutionPercent',value:percent});}
    page.browserState={...defaults,resolutionPercent:70};assert.equal(page.resolutionProfileIndex(),3);
    page.selectResolutionProfile(3);assert.equal(page.resolutionProfileControl.currentIndex,3);
    page.browserState={...defaults,resolutionPercent:60};assert.equal(page.resolutionProfileIndex(),2);
});

test('generated Qt profile methods through actual native controller keep pending/rejected/stale ACK and custom readback truthful without programmatic echo',async()=>{
    const generated=buildBrowserGraphicsOverrides(await sources(),channel),native=await fixture();
    const page=profilePage(generated,(field,value)=>native.emit({kind:'change',field,value}));
    function effective(){
        const state=native.ui.at(-1);page.browserReady=false;page.browserState={...state.settings};
        // The genuine combobox emits valueChanged on its programmatic index update.
        page.selectResolutionProfile(page.resolutionProfileIndex());page.browserReady=state.ready;
        return page.resolutionProfileIndex();
    }
    native.helper.setAuthority(7,true);native.emit({kind:'ready'});
    native.helper.receive({action:'graphicsResult',revision:7,schemaVersion:1,requestId:1,accepted:true,settings:defaults});
    assert.equal(effective(),0);assert.equal(native.sent.length,1);
    page.selectResolutionProfile(1);assert.equal(native.sent.length,2);assert.equal(native.sent[1].value,80);assert.equal(effective(),0);
    page.selectResolutionProfile(2);assert.equal(native.sent.length,2,'Pending controls are disabled');
    native.helper.receive({action:'graphicsResult',revision:6,schemaVersion:1,requestId:2,accepted:true,settings:{...defaults,resolutionPercent:80}});
    assert.equal(effective(),0);assert.equal(page.browserReady,false);
    native.helper.receive({action:'graphicsResult',revision:7,schemaVersion:1,requestId:2,accepted:false,settings:defaults,message:'Allocation refused'});
    assert.equal(effective(),0);assert.equal(page.browserReady,true);assert.equal(native.sent.length,2);assert.equal(native.ui.at(-1).message,'Allocation refused');
    page.selectResolutionProfile(2);
    native.helper.receive({action:'graphicsResult',revision:7,schemaVersion:1,requestId:3,accepted:true,settings:{...defaults,resolutionPercent:60}});
    assert.equal(effective(),2);assert.equal(native.sent.length,3);assert.equal(native.ui.at(-1).settings.localLights,true);
    page.publish('resolutionPercent',70);
    native.helper.receive({action:'graphicsResult',revision:7,schemaVersion:1,requestId:4,accepted:true,settings:{...defaults,resolutionPercent:70}});
    assert.equal(effective(),3);page.selectResolutionProfile(3);assert.equal(native.sent.length,4);
    native.helper.setAuthority(8,false);effective();page.selectResolutionProfile(1);assert.equal(native.sent.length,4);
    native.helper.close();page.browserReady=true;page.selectResolutionProfile(1);assert.equal(native.sent.length,4,'Lifetime cleanup disconnected actual Qt message reception');
});

test('missing or changed native combo source is rejected before any generated override; all six targets remain exact pinned package paths',async()=>{
    const originals=await sources();
    for(const bad of [{...originals,'qml/SettingComboBox.qml':undefined},{...originals,'qml/SettingComboBox.qml':originals['qml/SettingComboBox.qml']+'\n'}])
        assert.throws(()=>buildBrowserGraphicsOverrides(bad,channel),/Unsupported installed/);
    const generated=buildBrowserGraphicsOverrides(originals,channel);
    assert.deepEqual(Object.keys(generated).sort(),Object.keys(GRAPHICS_SOURCE_SHA256).sort());
    assert.equal(Object.keys(generated).length,6);
});

test('Custom and disabled selection restoration stays bounded when the native combo emits its real index-change callback again',async()=>{
    const generated=buildBrowserGraphicsOverrides(await sources(),channel),changes=[],page=profilePage(generated,(field,value)=>changes.push({field,value}));
    let notifications=0;
    page.resolutionProfileControl={currentIndex:3,setOptionIndex(index){if(this.currentIndex===index)return;assert(++notifications<=3,'Index restoration must not recurse');this.currentIndex=index;page.selectResolutionProfile(index);}};
    page.browserReady=true;page.selectResolutionProfile(3);assert.equal(page.resolutionProfileControl.currentIndex,0);assert.equal(changes.length,0);
    page.browserReady=false;page.resolutionProfileControl.currentIndex=2;page.selectResolutionProfile(2);assert.equal(page.resolutionProfileControl.currentIndex,0);assert.equal(changes.length,0);
    page.browserState={...defaults,resolutionPercent:70};page.resolutionProfileControl.currentIndex=1;page.selectResolutionProfile(1);assert.equal(page.resolutionProfileControl.currentIndex,3);assert.equal(changes.length,0);
});

test('profile change ACK after the unchanged8second deadline cannot select or persist an unconfirmed profile',async()=>{
    const generated=buildBrowserGraphicsOverrides(await sources(),channel),native=await fixture(),page=profilePage(generated,(field,value)=>native.emit({kind:'change',field,value}));
    native.helper.setAuthority(1,true);native.emit({kind:'ready'});native.helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:1,accepted:true,settings:defaults});
    page.browserState={...defaults};page.browserReady=true;page.selectResolutionProfile(1);native.elapse(8000);
    native.helper.receive({action:'graphicsResult',revision:1,schemaVersion:1,requestId:2,accepted:true,settings:{...defaults,resolutionPercent:80}});
    assert.equal(native.ui.at(-1).ready,true,'Expired change permits retry of the last confirmed state');assert.equal(native.ui.at(-1).settings.resolutionPercent,100);assert.match(native.ui.at(-1).message,/8 seconds/);
    assert.equal(native.sent.length,2);native.helper.close();
});
