// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Fixed private capture-time observer; no script execution or widget setters.
import assert from 'node:assert/strict';
import {captureState} from '../../shared/browser-capture.mjs';
export const PREFIX='BROWSER_TABLET_CAPTURE_AUDIT ';
export const KINDS=Object.freeze(['browser-tab','native-tab','echoCancellation','noiseSuppression','autoGainControl','inputGainPercent']);
export const QUERY=String.raw`    property int captureAuditCount: 0
    property int captureAuditBytes: 0
    function captureAudit(item,message) {
        if(captureAuditCount>=512||captureAuditBytes>=1048576)return;
        var nodes=0,truncated=false,seen=new Set(),roots=[],entries=[];
        function visible(node){for(var d=0;node&&d<32;d++,node=node.parent){if(node.visible===false||node.opacity===0)return false;if(node===item)return true;}return false;}
        function rect(node){try{var p=node.mapToItem(item,0,0),r={x:Number(p.x),y:Number(p.y),width:Number(node.width),height:Number(node.height)};if(![r.x,r.y,r.width,r.height].every(function(v){return isFinite(v)&&Math.abs(v)<=65536;})||r.width<=0||r.height<=0)return null;return r;}catch(e){return null;}}
        function visit(node,d,root,wrapper,parent){
            if(!node||d>24||nodes>=4096||seen.has(node)){truncated=true;return;}seen.add(node);nodes++;
            try{
                if(parent&&node.parent!==parent){truncated=true;return;}
                if(typeof node.browserReady==='boolean'&&typeof node.awaiting==='boolean'&&node.browserState&&node.browserState.version===1&&visible(node)){if(roots.length<2)roots.push(node);else truncated=true;root=node;}
                if(root&&visible(node)){
                    var kind=null;
                    if((node.text==='Browser microphone'||node.text==='Native connection')&&typeof node.checked==='boolean'&&typeof node.down==='boolean'&&typeof node.checkable==='boolean')kind=node.text==='Browser microphone'?'browser-tab':'native-tab';
                    var labels={'Echo Cancellation':'echoCancellation','Noise Suppression':'noiseSuppression','Automatic Gain Control':'autoGainControl'};
                    if(typeof labels[node.labelTextOn]==='string'&&typeof node.checked==='boolean')wrapper={node:node,kind:labels[node.labelTextOn]};
                    if(wrapper&&node!==wrapper.node&&node.background&&node.indicator&&typeof node.checked==='boolean'&&typeof node.visualPosition==='number'){
                        if(entries.length<12)entries.push({kind:wrapper.kind,enabled:wrapper.node.enabled!==false&&node.enabled!==false,checked:node.checked,rect:rect(node.background)});else truncated=true;wrapper=null;
                    }
                    if(node.from===0&&node.to===200&&node.stepSize===1&&typeof node.value==='number'&&node.background&&node.handle&&typeof node.pressed==='boolean'){
                        if(entries.length<12)entries.push({kind:'inputGainPercent',enabled:node.enabled!==false,checked:null,value:node.value,rect:rect(node.background),slider:{rect:rect(node),availableWidth:Number(node.availableWidth),leftPadding:Number(node.leftPadding),rightPadding:Number(node.rightPadding),handleWidth:Number(node.handle.width),mirrored:node.mirrored===true,horizontal:node.horizontal===true}});else truncated=true;
                    }
                    if(kind){if(entries.length<12)entries.push({kind:kind,enabled:node.enabled!==false,checked:node.checked,rect:rect(node)});else truncated=true;}
                }
                if(node.children){if(node.children.length>256)truncated=true;for(var i=0;i<node.children.length&&i<256;i++)visit(node.children[i],d+1,root,wrapper,node);}
            }catch(e){truncated=true;}
        }
        visit(item,0,null,null,null);var root=roots.length===1?roots[0]:null;if(roots.length===0)return;
        var body=JSON.stringify({version:1,sequence:message.sequence,revision:message.revision,navigationSequence:message.navigationSequence,scope:'visitor-capture-controls',nodes:nodes,truncated:truncated,rootCount:roots.length,uiEpoch:root?root.browserUiEpoch:0,ready:root?root.browserReady:false,awaiting:root?root.awaiting:false,state:root?root.browserState:null,controls:entries});
        if(body.length>4096||captureAuditBytes+body.length>1048576)return;captureAuditCount++;captureAuditBytes+=body.length;console.log('BROWSER_TABLET_CAPTURE_AUDIT '+body);
    }
`;
export function instrumentCaptureAudit(qml){assert(typeof qml==='string'&&Buffer.byteLength(qml)<=128*1024&&!qml.includes(PREFIX));const a='    function fromScript(message) {',b='                var item=target();activeCapture=message;';assert.equal(qml.split(a).length,2);assert.equal(qml.split(b).length,2);return qml.replace(a,QUERY+a).replace(b,b+'\n                captureAudit(item,message);');}
const integer=(v,min,max)=>Number.isSafeInteger(v)&&v>=min&&v<=max;
const exact=(v,ks)=>assert(v&&typeof v==='object'&&!Array.isArray(v)&&Object.keys(v).length===ks.length&&ks.every(k=>Object.hasOwn(v,k)));
function rect(r){exact(r,['x','y','width','height']);assert(Object.values(r).every(v=>typeof v==='number'&&Number.isFinite(v)&&Math.abs(v)<=65536));assert(r.width>0&&r.height>0);}
export function parseCaptureAudit(text){assert(typeof text==='string'&&Buffer.byteLength(text)<=4*1024*1024);const rows=[];for(const line of text.split('\n')){const i=line.indexOf(PREFIX);if(i<0)continue;const body=line.slice(i+PREFIX.length);assert(Buffer.byteLength(body)<=4096);const r=JSON.parse(body);exact(r,['version','sequence','revision','navigationSequence','scope','nodes','truncated','rootCount','uiEpoch','ready','awaiting','state','controls']);assert(r.version===1&&r.scope==='visitor-capture-controls');for(const k of ['sequence','revision','navigationSequence'])assert(integer(r[k],1,Number.MAX_SAFE_INTEGER));assert(integer(r.uiEpoch,0,2147483647));assert(integer(r.nodes,0,4096)&&integer(r.rootCount,0,2));assert([r.truncated,r.ready,r.awaiting].every(v=>typeof v==='boolean'));if(r.state!==null)r.state=captureState(r.state);assert(Array.isArray(r.controls)&&r.controls.length<=12);for(const c of r.controls){exact(c,c.kind==='inputGainPercent'?['kind','enabled','checked','value','rect','slider']:['kind','enabled','checked','rect']);assert(KINDS.includes(c.kind)&&typeof c.enabled==='boolean');assert(c.kind==='inputGainPercent'?c.checked===null&&typeof c.value==='number'&&Number.isFinite(c.value)&&c.value>=0&&c.value<=200:typeof c.checked==='boolean');if(c.rect!==null)rect(c.rect);if(c.kind==='inputGainPercent')validateSlider(c.slider);}rows.push(r);if(rows.length>32)rows.shift();}return rows;}
export function validateSlider(s){exact(s,['rect','availableWidth','leftPadding','rightPadding','handleWidth','mirrored','horizontal']);rect(s.rect);for(const k of ['availableWidth','leftPadding','rightPadding','handleWidth'])assert(typeof s[k]==='number'&&Number.isFinite(s[k])&&s[k]>=0&&s[k]<=65536);assert(typeof s.mirrored==='boolean'&&s.horizontal===true);assert(s.availableWidth>s.handleWidth&&s.availableWidth===Math.max(0,s.rect.width-s.leftPadding-s.rightPadding));}
export function gainPoint(s,value){validateSlider(s);assert(integer(value,0,200));const extent=s.availableWidth-s.handleWidth,offset=s.handleWidth/2;return s.mirrored?s.rect.x+s.rect.width-s.rightPadding-offset-extent*value/200:s.rect.x+s.leftPadding+offset+extent*value/200;}
export function captureControl(records,frame,kind,expected,value){assert(KINDS.includes(kind));if(kind==='inputGainPercent'){assert(integer(expected,0,200)&&integer(value,0,200));}else assert(typeof expected==='boolean');if(!frame?.tabletRect)return null;const r=records.findLast(v=>v.sequence===frame.sequence&&v.revision===frame.revision&&v.navigationSequence===frame.navigationSequence);if(!r||r.truncated||r.rootCount!==1||r.uiEpoch<1||!r.ready||r.awaiting)return null;const matches=r.controls.filter(c=>c.kind===kind);if(matches.length!==1)return null;const c=matches[0];if(!c.enabled||!c.rect)return null;if(kind==='inputGainPercent'){if(c.value!==expected||!r.state.active||r.state.settings.inputGainPercent!==expected)return null;}else if(c.checked!==expected)return null;const b=c.rect;let x=b.x+b.width/2,y=b.y+b.height/2,box={...b};if(kind==='inputGainPercent'){x=gainPoint(c.slider,value);box={x:x-8,y:y-8,width:16,height:16};}if(box.x<0||box.y<0||box.x+box.width>frame.width||box.y+box.height>frame.height)return null;return{x,y,rect:box,sequence:frame.sequence,revision:frame.revision,navigationSequence:frame.navigationSequence};}
export function encodeCaptureRecords(rows){assert(Array.isArray(rows)&&rows.length<=32);const s=rows.map(r=>PREFIX+JSON.stringify(r)).join('\n');parseCaptureAudit(s);return s;}
