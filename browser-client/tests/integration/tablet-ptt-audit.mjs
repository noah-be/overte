// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
export const PTT_AUDIT_PREFIX='BROWSER_TABLET_PTT_AUDIT ';
// Fixed capture-time reads only. The existing native input path performs clicks.
export const PTT_AUDIT_QML=String.raw`    property int pttAuditCount: 0
    property int pttAuditBytes: 0
    function pttAudit(item,message) {
        if(pttAuditCount>=512||pttAuditBytes>=524288)return;
        var nodes=0,truncated=false,seen=new Set(),audioRoots=[],buttons=[],switches=[];
        function visible(node){for(var depth=0;node&&depth<32;depth++,node=node.parent){if(node.visible===false||node.opacity===0)return false;if(node===item)return true;}return false;}
        function rect(node){try{var p=node.mapToItem(item,0,0),r={x:Number(p.x),y:Number(p.y),width:Number(node.width),height:Number(node.height)};if(![r.x,r.y,r.width,r.height].every(function(n){return isFinite(n)&&Math.abs(n)<=65536;})||r.width<=0||r.height<=0)return null;return r;}catch(error){return null;}}
        function visit(node,depth,audio,switchRoot,parent){
            if(!node||depth>24||nodes>=4096||seen.has(node)){truncated=true;return;}
            seen.add(node);nodes++;
            try{
            if(parent&&node.parent!==parent){truncated=true;return;}
            if(node.title==='Audio Settings'&&node.switchWidth===40&&node.switchHeight===16&&typeof node.pushToTalk==='boolean'&&typeof node.muted==='boolean'&&visible(node)){if(audioRoots.length<2)audioRoots.push(node);else truncated=true;audio=node;}
            if(node.text==='AUDIO'&&node.sortOrder===1&&typeof node.isActive==='boolean'&&typeof node.buttonIndex==='number'&&visible(node)){if(buttons.length<2)buttons.push(node);else truncated=true;}
            if(audio&&node.labelTextOn==='Push To Talk (T)'&&typeof node.checked==='boolean'&&visible(node))switchRoot=node;
            if(switchRoot&&node!==switchRoot&&node.background&&node.indicator&&typeof node.checked==='boolean'&&typeof node.down==='boolean'&&typeof node.visualPosition==='number'&&visible(node)){
                if(switches.length<2)switches.push({root:audio,wrapper:switchRoot,control:node});else truncated=true;
            }
            if(node.children){if(node.children.length>256)truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],depth+1,audio,switchRoot,node);}
            }catch(error){truncated=true;}
        }
        visit(item,0,null,null,null);
        var root=audioRoots.length===1?audioRoots[0]:null,button=buttons.length===1?buttons[0]:null,entry=switches.length===1?switches[0]:null;
        var desktop=null,held=null,muted=null,nativeBuildVersion=null;
        try{var build=About.buildVersion;if(typeof build==='string'&&/^[0-9A-Za-z.+ -]{1,64}$/.test(build))nativeBuildVersion=build;}catch(error){}
        try{desktop=AudioScriptingInterface.pushToTalkDesktop===true;held=AudioScriptingInterface.pushingToTalk===true;muted=AudioScriptingInterface.mutedDesktop===true;}catch(error){truncated=true;}
        var control=entry&&entry.root===root&&entry.wrapper.checked===entry.control.checked?{checked:entry.control.checked,enabled:entry.wrapper.enabled!==false&&entry.control.enabled!==false,rect:rect(entry.control.background)}:null;
        var body=JSON.stringify({version:1,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,scope:'native-desktop-ptt',nativeBuildVersion:nativeBuildVersion,nodes:nodes,truncated:truncated,audioRootCount:audioRoots.length,switchCount:switches.length,audioButtonCount:buttons.length,native:{enabled:desktop,held:held,muted:muted},audioButton:button?{enabled:button.enabled!==false,rect:rect(button)}:null,control:control});
        if(body.length>4096||pttAuditBytes+body.length>524288)return;pttAuditCount++;pttAuditBytes+=body.length;
        console.log("BROWSER_TABLET_PTT_AUDIT "+body);
    }
`;
export function instrumentPttAudit(qml){
 assert(typeof qml==='string'&&Buffer.byteLength(qml)<=128*1024&&!qml.includes(PTT_AUDIT_PREFIX));
 const marker='    function fromScript(message) {',capture='                var item=target();activeCapture=message;';
 assert.equal(qml.split(marker).length,2);assert.equal(qml.split(capture).length,2);
 return qml.replace(marker,PTT_AUDIT_QML+marker).replace(capture,capture+'\n                pttAudit(item,message);');
}
const keys=(value,allowed)=>{assert(value&&typeof value==='object'&&!Array.isArray(value));assert.deepEqual(Object.keys(value).sort(),[...allowed].sort());};
const integer=(value,min,max)=>Number.isSafeInteger(value)&&value>=min&&value<=max;
function rectangle(value){keys(value,['x','y','width','height']);assert(Object.values(value).every(n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<=65536));assert(value.width>0&&value.height>0);}
export function parsePttAudit(text){
 assert(typeof text==='string'&&Buffer.byteLength(text)<=4*1024*1024);const records=[];
 for(const line of text.split('\n')){const at=line.indexOf(PTT_AUDIT_PREFIX);if(at<0)continue;const body=line.slice(at+PTT_AUDIT_PREFIX.length);assert(Buffer.byteLength(body)<=4096);const r=JSON.parse(body);
  keys(r,['version','sequence','revision','navigationSequence','scope','nativeBuildVersion','nodes','truncated','audioRootCount','switchCount','audioButtonCount','native','audioButton','control']);
  assert(r.version===1&&r.scope==='native-desktop-ptt'&&integer(r.sequence,1,Number.MAX_SAFE_INTEGER)&&integer(r.revision,1,Number.MAX_SAFE_INTEGER)&&integer(r.navigationSequence,1,Number.MAX_SAFE_INTEGER));
  assert(r.nativeBuildVersion===null||typeof r.nativeBuildVersion==='string'&&/^[0-9A-Za-z.+ -]{1,64}$/.test(r.nativeBuildVersion));
  assert(integer(r.nodes,0,4096)&&typeof r.truncated==='boolean');for(const field of ['audioRootCount','switchCount','audioButtonCount'])assert(integer(r[field],0,2));
  keys(r.native,['enabled','held','muted']);assert(Object.values(r.native).every(v=>typeof v==='boolean'||v===null));
  if(r.audioButton){keys(r.audioButton,['enabled','rect']);assert(typeof r.audioButton.enabled==='boolean');if(r.audioButton.rect)rectangle(r.audioButton.rect);}
  if(r.control){keys(r.control,['checked','enabled','rect']);assert(typeof r.control.checked==='boolean'&&typeof r.control.enabled==='boolean');if(r.control.rect)rectangle(r.control.rect);}
  records.push(r);if(records.length>32)records.shift();
 }return records;
}
export function pttClickControl(records,frame,kind,expected){
 assert(['audio-app','desktop-ptt'].includes(kind));if(kind==='desktop-ptt')assert(typeof expected==='boolean');
 if(!frame||!integer(frame.width,1,4096)||!integer(frame.height,1,4096)||!frame.tabletRect)return null;
 const record=records.findLast(r=>r.sequence===frame.sequence&&r.revision===frame.revision&&r.navigationSequence===frame.navigationSequence);
 if(!record||record.truncated)return null;
 let control;
 if(kind==='audio-app'){if(record.audioButtonCount!==1||record.audioRootCount!==0)return null;control=record.audioButton;}
 else {if(record.audioRootCount!==1||record.switchCount!==1||record.native.enabled!==expected||record.native.held!==false||record.native.muted!==true)return null;control=record.control;if(control?.checked!==expected)return null;}
 if(!control?.enabled||!control.rect)return null;const box=control.rect;
 if(box.x<0||box.y<0||box.x+box.width>frame.width||box.y+box.height>frame.height)return null;
 return {x:box.x+box.width/2,y:box.y+box.height/2,rect:{...box},sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence};
}
export function assertPaintedPttControl(rgba,width,height){
 assert(integer(width,8,256)&&integer(height,8,256)&&width*height<=65536&&rgba.length===width*height*4);
 assert((Array.isArray(rgba)||rgba instanceof Uint8Array)&&rgba.every(value=>Number.isInteger(value)&&value>=0&&value<=255));
 let lo=255,hi=0,opaque=0;for(let i=0;i<rgba.length;i+=4){const value=(rgba[i]+rgba[i+1]+rgba[i+2])/3;lo=Math.min(lo,value);hi=Math.max(hi,value);if(rgba[i+3]===255)opaque++;}
 assert(hi-lo>20&&opaque>width*height/2,'Actual native control must have painted visible contrast');return true;
}
