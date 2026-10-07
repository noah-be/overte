// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import assert from 'node:assert/strict';
export const POPUP_AUDIT_PREFIX='BROWSER_TABLET_POPUP_AUDIT ';
/** Fixed passive geometry only; use exclusively in an owned copied test helper. */
export function instrumentTabletPopupAudit(source){
 assert(typeof source==='string'&&source.length<=128*1024&&!source.includes(POPUP_AUDIT_PREFIX));
 const marker='    function fromScript(message) {',capture=source.includes('                var item=target();activeCapture=message;')?'                var item=target();activeCapture=message;':'                var item=target();captureTarget=item;activeCapture=message;';
 assert.equal(source.split(marker).length,2);assert.equal(source.split(capture).length,2);
 if(!source.includes('import QtQuick.Controls 2.15 as Controls\n')){const entry='import QtQuick.Window 2.2\n';assert.equal(source.split(entry).length,2);source=source.replace(entry,entry+'import QtQuick.Controls 2.15 as Controls\n');}
 const helper=`    property string popupAuditKey: ""
    property int popupAuditCount: 0
    function popupAudit(item,message) {
        if(popupAuditCount>=64)return;
        var top=topRoot(),tablet=find(top,"tabletRoot",0),desktop=find(top,"desktop",0),overlay=Controls.Overlay.overlay;
        function number(value){return typeof value==="number"&&isFinite(value)&&Math.abs(value)<=65536?value:null;}
        function geometry(node){if(!node)return null;var point=node.mapToItem(top,0,0),tag=/^[A-Za-z0-9_]+/.exec(String(node));return {classTag:tag?tag[0].slice(0,64):"unknown",visible:node.visible===true,opacity:number(node.opacity),x:number(point.x),y:number(point.y),width:number(node.width),height:number(node.height)};}
        var children=[],truncated=false;
        if(overlay&&overlay.children){for(var i=0;i<overlay.children.length&&i<256;i++){var child=overlay.children[i];if(child.visible===true&&child.width>0&&child.height>0){if(children.length<12)children.push(geometry(child));else truncated=true;}}if(overlay.children.length>256)truncated=true;}
        var controls=[],budget={nodes:0,truncated:false};
        function combo(node,depth){
            if(!node||depth>24||++budget.nodes>4096){budget.truncated=true;return;}
            if(node.visible===false)return;
            var tag=/^[A-Za-z0-9_]+/.exec(String(node));
            if(tag&&/^((ComboBox|QQuickComboBox)(_|$))/.test(tag[0])&&typeof node.currentIndex==="number"&&typeof node.highlightedIndex==="number"&&node.popup){
                if(controls.length<4){var p=node.popup,c=p.contentItem;
                    controls.push({rect:geometry(node),currentIndex:number(node.currentIndex),highlightedIndex:number(node.highlightedIndex),activeFocus:node.activeFocus===true,pressed:node.pressed===true,down:node.down===true,enabled:node.enabled!==false,
                    popup:{visible:p.visible===true,opened:p.opened===true,x:number(p.x),y:number(p.y),width:number(p.width),height:number(p.height)},content:geometry(c),delegateCount:node.delegateModel&&number(node.delegateModel.count)});
                }else budget.truncated=true;
            }
            if(node.children){if(node.children.length>256)budget.truncated=true;for(var j=0;j<node.children.length&&j<256;j++)combo(node.children[j],depth+1);}
        }
        combo(top,0);
        var data={controls:controls,controlsTruncated:budget.truncated,scope:item===top?"offscreen-content":item===desktop?"desktop":"tablet",top:geometry(top),tablet:geometry(tablet),overlay:geometry(overlay),overlayInTop:!!overlay&&overlay.parent===top,children:children,truncated:truncated},key=JSON.stringify(data);
        if(key===popupAuditKey)return;popupAuditKey=key;popupAuditCount++;
        data.sequence=message.sequence;data.revision=message.revision;
        console.log("${POPUP_AUDIT_PREFIX}"+JSON.stringify(data));
    }
`;
 return source.replace(marker,helper+marker).replace(capture,capture+'\n                popupAudit(item,message);');
}
