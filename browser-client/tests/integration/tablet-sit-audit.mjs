// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
export const EMOTE_PREFIX='BROWSER_EMOTE_ACTION ';
export const VIEW_PREFIX='BROWSER_EMOTE_VIEW ';
export const CORRECTED_EMOTE_SHA256='cc8bd029c59aeb7165050ebfc6bfb9004234d549fedf8feb4b5e308a5fd6c16f';
export const SIT_JOINTS=Object.freeze(['Hips','LeftUpLeg','RightUpLeg','LeftLeg','RightLeg','LeftFoot','RightFoot']);
export const EMOTE_QUERY=String.raw`(function(){
 if(!/\/system\/html\/EmoteApp\.html$/.test(location.pathname)||document.title!=='Emote App')return null;
 var elements=document.querySelectorAll('input.emote-button'),controls=[];
 if(elements.length!==10)return null;
 for(var i=0;i<elements.length;i++){
  var e=elements[i],r=e.getBoundingClientRect(),s=getComputedStyle(e);
  controls.push({name:String(e.value),rect:{x:r.x,y:r.y,width:r.width,height:r.height},visible:s.display!=='none'&&s.visibility!=='hidden'&&r.width>0&&r.height>0,enabled:!e.disabled});
 }
 return {route:'emote',readyState:document.readyState,eventBridge:!!(window.EventBridge&&typeof EventBridge.emitWebEvent==='function'),viewport:{width:innerWidth,height:innerHeight},controls:controls};
}())`;
export const HOME_PREFIX='BROWSER_EMOTE_HOME ';
export const EMOTE_HOME_AUDIT_QML=String.raw`    property int emoteHomeAuditCount: 0
    property int emoteHomeAuditBytes: 0
    function emoteHomeAudit(item,message) {
        if(emoteHomeAuditCount>=256||emoteHomeAuditBytes>=524288)return;
        var nodes=0,truncated=false,seen=new Set(),buttons=[];
        function visible(node){for(var depth=0;node&&depth<32;depth++,node=node.parent){if(node.visible===false||node.opacity===0)return false;if(node===item)return true;}return false;}
        function visit(node,depth,parent){
            if(!node||depth>24||nodes>=4096||seen.has(node)){truncated=true;return;}
            seen.add(node);nodes++;
            try{
                if(parent&&node.parent!==parent){truncated=true;return;}
                if(node.text==='EMOTE'&&node.sortOrder===12&&typeof node.isActive==='boolean'&&typeof node.buttonIndex==='number'&&visible(node)){if(buttons.length<2)buttons.push(node);else truncated=true;}
                if(node.children){if(node.children.length>256)truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,node);}
            }catch(error){truncated=true;}
        }
        visit(item,0,null);if(buttons.length===0)return;
        var button=buttons.length===1?buttons[0]:null,rect=null,enabled=false;
        if(button)try{enabled=button.enabled!==false;var p=button.mapToItem(item,0,0),r={x:Number(p.x),y:Number(p.y),width:Number(button.width),height:Number(button.height)};if([r.x,r.y,r.width,r.height].every(function(n){return isFinite(n)&&Math.abs(n)<=65536;})&&r.width>0&&r.height>0)rect=r;}catch(error){truncated=true;}
        var body=JSON.stringify({version:1,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,nodes:nodes,truncated:truncated,buttonCount:buttons.length,control:button?{enabled:enabled,rect:rect}:null});
        if(body.length>4096||emoteHomeAuditBytes+body.length>524288)return;emoteHomeAuditCount++;emoteHomeAuditBytes+=body.length;console.log('BROWSER_EMOTE_HOME '+body);
    }
`;
export function parseEmoteHomeAudit(text){
 assert(typeof text==='string'&&Buffer.byteLength(text)<=4*1024*1024);const records=[];
 const keys=(value,expected)=>assert(value&&typeof value==='object'&&!Array.isArray(value)&&JSON.stringify(Object.keys(value).sort())===JSON.stringify([...expected].sort()));
 for(const line of text.split('\n')){const start=line.indexOf(HOME_PREFIX);if(start<0)continue;const body=line.slice(start+HOME_PREFIX.length);assert(Buffer.byteLength(body)<=4096);if(!body.startsWith('{'))continue;const r=JSON.parse(body);
  keys(r,['version','sequence','revision','navigationSequence','nodes','truncated','buttonCount','control']);assert(r.version===1&&['sequence','revision','navigationSequence'].every(key=>Number.isSafeInteger(r[key])&&r[key]>=1));assert(Number.isSafeInteger(r.nodes)&&r.nodes>=0&&r.nodes<=4096&&typeof r.truncated==='boolean'&&Number.isSafeInteger(r.buttonCount)&&r.buttonCount>=0&&r.buttonCount<=2);
  if(r.control){keys(r.control,['enabled','rect']);assert(typeof r.control.enabled==='boolean');if(r.control.rect){keys(r.control.rect,['x','y','width','height']);assert(Object.values(r.control.rect).every(finite)&&r.control.rect.width>0&&r.control.rect.height>0);}}
  records.push(r);if(records.length>32)records.shift();
 }return records;
}
export function emoteHomeControl(records,frame){
 if(!frame||![frame.width,frame.height].every(n=>Number.isSafeInteger(n)&&n>0&&n<=4096)||!frame.tabletRect)return null;
 const t=frame.tabletRect;if(![t.x,t.y,t.width,t.height].every(finite)||t.width<=0||t.height<=0||t.x<0||t.y<0||t.x+t.width>frame.width||t.y+t.height>frame.height)return null;
 const matches=records.filter(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.navigationSequence===frame.navigationSequence);if(matches.length!==1)return null;const r=matches[0];
 if(r.truncated||r.buttonCount!==1||r.control?.enabled!==true||!r.control.rect)return null;const b=r.control.rect;
 if(b.x<t.x||b.y<t.y||b.x+b.width>t.x+t.width||b.y+b.height>t.y+t.height)return null;
 return {sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,rect:{...b},x:b.x+b.width/2,y:b.y+b.height/2};
}
export function instrumentEmoteView(qml){
 const marker='    function fromScript(message) {',capture='                var item=target();activeCapture=message;';
 assert.equal(qml.split(marker).length,2);assert.equal(qml.split(capture).length,2);
 const fixed=`    property int emoteAuditCount: 0
    property int emoteAuditBytes: 0
    property bool emoteAuditPending: false
    function emoteAudit(item,message) {
        if(emoteAuditPending||emoteAuditCount>=256||emoteAuditBytes>=524288)return;
        var seen=new Set(),nodes=0,views=0;
        function visit(node,depth,parent) {
            if(!node||depth>24||nodes>=2048||seen.has(node)||node.visible===false)return;
            if(node!==item&&node.parent!==parent)return;
            seen.add(node);nodes++;
            if(typeof node.runJavaScript==='function'&&views<4&&/\\/system\\/html\\/EmoteApp\\.html$/.test(String(node.url||''))&&!emoteAuditPending) {
                views++;emoteAuditPending=true;
                var origin=node.mapToItem(item,0,0),url=String(node.url),width=Number(node.width),height=Number(node.height);
                node.runJavaScript(${JSON.stringify(EMOTE_QUERY)},function(result){
                    emoteAuditPending=false;
                    if(!result||result.route!=='emote'||!node.visible||String(node.url)!==url||node.parent!==parent)return;
                    var body=JSON.stringify({sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,web:{x:Number(origin.x),y:Number(origin.y),width:width,height:height},dom:result});
                    if(body.length>16384||emoteAuditCount>=256||emoteAuditBytes+body.length>524288)return;
                    emoteAuditCount++;emoteAuditBytes+=body.length;console.log('${VIEW_PREFIX}'+body);
                });
            }
            if(node.children)for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,node);
        }
        try { visit(item,0,null); } catch(error) { emoteAuditPending=false; }
    }
`;
 return qml.replace(marker,fixed+EMOTE_HOME_AUDIT_QML+marker).replace(capture,capture+'\n                emoteAudit(item,message);\n                emoteHomeAudit(item,message);');
}
export function instrumentEmoteEvents(source){
 assert.equal(createHash('sha256').update(source).digest('hex'),CORRECTED_EMOTE_SHA256,'Only the exact corrected authored native script can be passively instrumented');
 const call='                    MyAvatar.overrideAnimation(ANIMATIONS[emoteName].url, FPS, false, 0, frameCount);';
 assert.equal(source.split(call).length,3);
 source=source.replaceAll(call,call+`\n                    print('${EMOTE_PREFIX}'+JSON.stringify({kind:'override-returned',name:emoteName,frames:frameCount,fps:FPS}));`);
 const stop='    Controller.disableMapping(eventMappingName);';assert.equal(source.split(stop).length,2);
 return source.replace(stop,stop+`\n    print('${EMOTE_PREFIX}'+JSON.stringify({kind:'restore-control-returned'}));`);
}
export function parseEmoteAudit(text,prefix){
 assert(typeof text==='string'&&text.length<=4*1024*1024);assert([VIEW_PREFIX,EMOTE_PREFIX].includes(prefix));const records=[];
 for(const line of text.split('\n')){const start=line.indexOf(prefix);if(start<0)continue;const body=line.slice(start+prefix.length);assert(body.length<=16384);if(!body.startsWith('{'))continue;if(prefix===EMOTE_PREFIX&&!/^\[[^\]\r\n]{1,128}\] \[[^\]\r\n]{1,128}\] \[overte\.scriptengine\.script\] \[[^\]\r\n]{1,128}\] $/.test(line.slice(0,start)))continue;records.push(JSON.parse(body));if(records.length>32)records.shift();}
 return records;
}
const finite=value=>typeof value==='number'&&Number.isFinite(value)&&Math.abs(value)<=65536;
export function emoteControl(records,frame,name='Sit'){
 assert.equal(name,'Sit');if(!frame)return null;
 const matching=records.filter(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.navigationSequence===frame.navigationSequence);
 if(matching.length!==1)return null;const {web,dom}=matching[0];
 if(dom?.route!=='emote'||dom.readyState!=='complete'||dom.eventBridge!==true||dom.controls?.length!==10||!web||!dom.viewport)return null;
 if(![web.x,web.y,web.width,web.height,dom.viewport.width,dom.viewport.height,frame.width,frame.height].every(finite)||web.width<=0||web.height<=0||dom.viewport.width<=0||dom.viewport.height<=0)return null;
 const found=dom.controls.filter(c=>c.name===name&&c.visible===true&&c.enabled===true);if(found.length!==1)return null;
 const r=found[0].rect;if(!r||![r.x,r.y,r.width,r.height].every(finite)||r.width<8||r.height<8||r.x<0||r.y<0||r.x+r.width>dom.viewport.width||r.y+r.height>dom.viewport.height)return null;
 const rect={x:web.x+r.x*web.width/dom.viewport.width,y:web.y+r.y*web.height/dom.viewport.height,width:r.width*web.width/dom.viewport.width,height:r.height*web.height/dom.viewport.height};
 if(rect.x<0||rect.y<0||rect.x+rect.width>frame.width||rect.y+rect.height>frame.height)return null;
 return {sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence,rect,x:rect.x+rect.width/2,y:rect.y+rect.height/2};
}
export function assertPaintedEmoteControl({width,height,rgba}){
 assert(Number.isSafeInteger(width)&&Number.isSafeInteger(height)&&width>=8&&height>=8&&width<=512&&height<=512&&width*height<=65536);assert.equal(rgba.length,width*height*4);
 let low=255,high=0,opaque=0;for(let i=0;i<rgba.length;i+=4){assert(rgba.slice(i,i+4).every(v=>Number.isInteger(v)&&v>=0&&v<=255));low=Math.min(low,...rgba.slice(i,i+3));high=Math.max(high,...rgba.slice(i,i+3));if(rgba[i+3]===255)opaque++;}
 assert(opaque>width*height/2&&high-low>20,'A genuine painted native Emote button is required');
}
function quaternion(value){assert(value&&['x','y','z','w'].every(a=>Number.isFinite(value[a])));const norm=Math.hypot(value.x,value.y,value.z,value.w);assert(norm>.99&&norm<1.01);return value;}
export function angle(a,b){quaternion(a);quaternion(b);const norm=Math.hypot(a.x,a.y,a.z,a.w)*Math.hypot(b.x,b.y,b.z,b.w);return 2*Math.acos(Math.min(1,Math.abs(a.x*b.x+a.y*b.y+a.z*b.z+a.w*b.w)/norm));}
export function sitPose(avatar){assert(avatar&&Array.isArray(avatar.jointNames)&&avatar.jointNames.length<=1000);return Object.fromEntries(SIT_JOINTS.map(name=>{const indices=avatar.jointNames.flatMap((v,i)=>v===name?[i]:[]);assert.equal(indices.length,1);const i=indices[0],position=avatar.jointTranslations?.[i];assert(position&&['x','y','z'].every(a=>Number.isFinite(position[a])&&Math.abs(position[a])<1e6));return[name,{orientation:{...quaternion(avatar.jointRotations?.[i])},position:{...position}}];}));}
export function sitDifference(baseline,current){return {hipsDrop:baseline.Hips.position.y-current.Hips.position.y,maximumThighChange:Math.max(...['LeftUpLeg','RightUpLeg'].map(n=>angle(baseline[n].orientation,current[n].orientation)))};}
export function actualRigMatches(rig,pose){return !!rig?.joints&&SIT_JOINTS.every(name=>{const actual=rig.joints[name],expected=pose[name];return actual&&expected&&['x','y','z','w'].every(a=>Math.abs(actual.orientation[a]-expected.orientation[a])<1e-6)&&['x','y','z'].every(a=>Math.abs(actual.position[a]-expected.position[a])<1e-6);});}
