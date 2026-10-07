// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {readCreateWorkerLog} from './tablet-create-readiness.mjs';
export const GRAPHICS_STATE_PREFIX='BROWSER_GRAPHICS_STATE_AUDIT ';
export const GRAPHICS_CAPTURE_PREFIX='BROWSER_GRAPHICS_CAPTURE_AUDIT ';
export const GRAPHICS_REFUSAL='BROWSER_GRAPHICS_AUDIT_REFUSED';
function once(source,marker,replacement){assert.equal(source.split(marker).length,2,'Reviewed diagnostic source anchor must be unique');return source.replace(marker,replacement);}
function logger(scope,fields){return `    property int graphicsAuditCount: 0
    function graphicsAudit(reason) {
        if(graphicsAuditCount>=256)return;
        graphicsAuditCount++;
        function number(value){return typeof value==="number"&&isFinite(value)&&Math.abs(value)<=65536?value:null;}
        try {console.log("${GRAPHICS_STATE_PREFIX}"+JSON.stringify({scope:"${scope}",ordinal:graphicsAuditCount,reason:reason,${fields}}));}catch(diagnosticError){try{console.log("${GRAPHICS_REFUSAL}");}catch(diagnosticLogError){}}
    }
`;}
/** Only instrument exact generated browser Graphics controls in a copied gateway. */
export function instrumentGraphicsGenerated(input){
 assert(input&&typeof input==='object');const out={...input};
 for(const name of ['Settings.qml','qml/pages/GraphicsSettings.qml','qml/SettingComboBox.qml'])assert(typeof out[name]==='string'&&out[name].length<128*1024&&!out[name].includes(GRAPHICS_STATE_PREFIX));
 let s=out['Settings.qml'];
 s=once(s,'    id: browserSettingsApp;','    id: browserSettingsApp;\n'+logger('settings','ready:browserGraphicsReady,resolutionPercent:number(browserGraphicsState.resolutionPercent),fieldOfView:number(browserGraphicsState.fieldOfView),graphicsPage:currentPage==="Graphics"'));
 s=once(s,'browserGraphicsReady=false;browserGraphicsState=message.settings;browserGraphicsMessage=message.message||"";browserGraphicsReady=message.ready;break;','graphicsAudit("effective-before");browserGraphicsReady=false;browserGraphicsState=message.settings;browserGraphicsMessage=message.message||"";browserGraphicsReady=message.ready;graphicsAudit("effective-after");break;');out['Settings.qml']=s;
 s=out['qml/pages/GraphicsSettings.qml'];
 s=once(s,'    id: graphicsPage;','    id: graphicsPage;\n'+logger('graphics-page','ready:browserReady,resolutionPercent:number(browserState.resolutionPercent),fieldOfView:number(browserState.fieldOfView),visible:visible===true,expectedIndex:[100,80,60].indexOf(browserState.resolutionPercent)<0?3:[100,80,60].indexOf(browserState.resolutionPercent)'));
 s=once(s,'    onVisibleChanged: {if(visible)browserPageReady();}','    onVisibleChanged: {graphicsAudit("visible");if(visible)browserPageReady();}\n    onBrowserReadyChanged: graphicsAudit("ready");\n    Component.onCompleted: graphicsAudit("completed");');
 s=once(s,'    onBrowserStateChanged: {if(localLightsControl)localLightsControl.update();if(clippingControl)clippingControl.update();if(resolutionProfileControl)resolutionProfileControl.setOptionIndex(resolutionProfileIndex());}','    onBrowserStateChanged: {graphicsAudit("state-before");if(localLightsControl)localLightsControl.update();if(clippingControl)clippingControl.update();if(resolutionProfileControl)resolutionProfileControl.setOptionIndex(resolutionProfileIndex());graphicsAudit("state-after");}');out['qml/pages/GraphicsSettings.qml']=s;
 s=out['qml/SettingComboBox.qml'];
 // The actual licensed native widget remains intact. Only fixed scalar logs
 // around existing assignments are added; no setters, timers or event dispatch.
 s=once(s,'\tid: root;','\tid: root;\n'+logger('combo','optionIndex:number(optionIndex),currentIndex:number(control.currentIndex),highlightedIndex:number(control.highlightedIndex),visible:visible===true,enabled:enabled===true,popupVisible:control.popup.visible===true'));
 s=once(s,'\t\t\t\tonCurrentIndexChanged: {','\t\t\t\tonCurrentIndexChanged: {\n                    if(settingText==="Resolution preset")graphicsAudit("index-before");');
 s=once(s,'\t\t\t\t\t_optionText = options[currentIndex];','\t\t\t\t\t_optionText = options[currentIndex];\n                    if(settingText==="Resolution preset")graphicsAudit("index-after");');
 s=once(s,'\tfunction setOptionIndex(index) {\n\t\tcontrol.currentIndex = index;\n\t}','\tfunction setOptionIndex(index) {\n        if(settingText==="Resolution preset")graphicsAudit("set-before");\n\t\tcontrol.currentIndex = index;\n        if(settingText==="Resolution preset")graphicsAudit("set-after");\n\t}');out['qml/SettingComboBox.qml']=s;
 return out;
}
export function instrumentGraphicsCapture(source){
 assert(typeof source==='string'&&source.length<128*1024&&!source.includes(GRAPHICS_CAPTURE_PREFIX));
 const marker='    function fromScript(message) {',capture='                var item=target();activeCapture=message;';
 const observer=`    property int graphicsCaptureAuditCount: 0
    function graphicsCaptureAudit(item,message) {
        if(graphicsCaptureAuditCount>=256)return;graphicsCaptureAuditCount++;
        var pages=[],controls=[],budget={nodes:0,truncated:false};
        function number(value){return typeof value==="number"&&isFinite(value)&&Math.abs(value)<=65536?value:null;}
        function visit(node,depth){
            if(!node||depth>24||++budget.nodes>4096){budget.truncated=true;return;}
            if(node.visible===false)return;
            if(typeof node.browserReady==="boolean"&&node.browserState&&typeof node.resolutionProfileIndex==="function"){
                if(pages.length<4)pages.push({ready:node.browserReady,resolutionPercent:number(node.browserState.resolutionPercent),fieldOfView:number(node.browserState.fieldOfView),visible:node.visible===true});else budget.truncated=true;
            }
            var tag=/^[A-Za-z0-9_]+/.exec(String(node));
            if(tag&&/^(ComboBox|QQuickComboBox)(_|$)/.test(tag[0])&&typeof node.currentIndex==="number"&&typeof node.highlightedIndex==="number"&&node.popup){
                if(controls.length<4)controls.push({currentIndex:number(node.currentIndex),highlightedIndex:number(node.highlightedIndex),enabled:node.enabled===true,activeFocus:node.activeFocus===true,popupVisible:node.popup.visible===true,popupOpened:node.popup.opened===true});else budget.truncated=true;
            }
            if(node.children){if(node.children.length>256)budget.truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1);}
        }
        visit(topRoot(),0);
        console.log("${GRAPHICS_CAPTURE_PREFIX}"+JSON.stringify({ordinal:graphicsCaptureAuditCount,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,pages:pages,controls:controls,truncated:budget.truncated}));
    }
`;
 return once(once(source,marker,observer+marker),capture,capture+'\n                try{graphicsCaptureAudit(item,message);}catch(diagnosticError){try{console.log("'+GRAPHICS_REFUSAL+'");}catch(diagnosticLogError){}}');
}
const scopes=new Set(['settings','graphics-page','combo']);
const reasons=new Set(['effective-before','effective-after','visible','ready','completed','state-before','state-after','index-before','index-after','set-before','set-after']);
function integer(v,min,max){return Number.isSafeInteger(v)&&v>=min&&v<=max;}
function scalar(v){return v===null||typeof v==='boolean'||(typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=65536);}
/** Project only fixed scalars; raw private worker text is never returned. */
export function parseGraphicsStateAudit(text){
 assert(typeof text==='string'&&Buffer.byteLength(text)<=4*1024*1024);const records=[];let censored=false,refused=0;
 for(const line of text.split('\n')){
  if(line.includes(GRAPHICS_REFUSAL)){refused=Math.min(1024,refused+1);if(refused===1024)censored=true;continue;}
  const stateAt=line.indexOf(GRAPHICS_STATE_PREFIX),captureAt=line.indexOf(GRAPHICS_CAPTURE_PREFIX);if(stateAt<0&&captureAt<0)continue;
  const capture=captureAt>=0,prefix=capture?GRAPHICS_CAPTURE_PREFIX:GRAPHICS_STATE_PREFIX,body=line.slice((capture?captureAt:stateAt)+prefix.length);assert(body.length<=4096);const value=JSON.parse(body);assert(value&&integer(value.ordinal,1,256));
  if(capture){assert(integer(value.sequence,1,Number.MAX_SAFE_INTEGER)&&integer(value.revision,1,Number.MAX_SAFE_INTEGER)&&integer(value.navigationSequence,0,Number.MAX_SAFE_INTEGER)&&typeof value.truncated==='boolean');assert(Array.isArray(value.pages)&&value.pages.length<=4&&Array.isArray(value.controls)&&value.controls.length<=4);
   const pages=value.pages.map(p=>{assert(p&&typeof p.ready==='boolean'&&typeof p.visible==='boolean'&&scalar(p.resolutionPercent)&&scalar(p.fieldOfView));return {ready:p.ready,visible:p.visible,resolutionPercent:p.resolutionPercent,fieldOfView:p.fieldOfView};});
   const controls=value.controls.map(c=>{assert(c&&scalar(c.currentIndex)&&scalar(c.highlightedIndex)&&['enabled','activeFocus','popupVisible','popupOpened'].every(k=>typeof c[k]==='boolean'));return {currentIndex:c.currentIndex,highlightedIndex:c.highlightedIndex,enabled:c.enabled,activeFocus:c.activeFocus,popupVisible:c.popupVisible,popupOpened:c.popupOpened};});
   records.push({kind:'capture',ordinal:value.ordinal,sequence:value.sequence,revision:value.revision,navigationSequence:value.navigationSequence,pages,controls,truncated:value.truncated});
  }else{assert(scopes.has(value.scope)&&reasons.has(value.reason));const record={kind:'state',scope:value.scope,ordinal:value.ordinal,reason:value.reason};const keys=value.scope==='settings'?['ready','resolutionPercent','fieldOfView','graphicsPage']:value.scope==='graphics-page'?['ready','resolutionPercent','fieldOfView','visible','expectedIndex']:['optionIndex','currentIndex','highlightedIndex','visible','enabled','popupVisible'];for(const k of keys){assert(scalar(value[k]));if(['ready','graphicsPage','visible','enabled','popupVisible'].includes(k))assert(typeof value[k]==='boolean');else assert(value[k]===null||typeof value[k]==='number');record[k]=value[k];}records.push(record);}
  if(value.ordinal===256)censored=true;if(records.length>1024){records.shift();censored=true;}
 }
 return {records,censored,refused};
}
export async function readGraphicsStateAudit(profile){return parseGraphicsStateAudit(await readCreateWorkerLog(profile));}
