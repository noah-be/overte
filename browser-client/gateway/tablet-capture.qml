// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Window 2.2
import QtTest 1.2
import BrowserNativeInput 1.0

Item {
    id: helper
    width: 1; height: 1
    signal sendToScript(var message)
    TestEvent { id: events }
    NativeInput { id: nativeInput }
    property var captureTarget: null
    property var activeCapture: null
    property string captureSurface: "tablet"
    function topRoot() { var item=helper; while(item.parent) item=item.parent; return item; }
    function find(item,name,depth) {
        if (!item || depth>24) return null;
        if (item.objectName===name) return item;
        for(var i=0;i<item.children.length;i++) {var found=find(item.children[i],name,depth+1);if(found)return found;}
        return null;
    }
    function hasDialog(item,tablet,depth) {
        if (!item || depth>24 || item===helper || item===tablet) return false;
        // Window.shown is a native Desktop QtQuick property. Invisible helper windows
        // and the system toolbar never count as associated dialogs.
        if (item.shown===true && item.visible && item.width>50 && item.height>40 && item.objectName!=="com.highfidelity.interface.toolbar.system") return true;
        for(var i=0;i<item.children.length;i++) if(hasDialog(item.children[i],tablet,depth+1))return true;
        return false;
    }
    function target() {
        var top=topRoot(),tablet=find(top,"tabletRoot",0),desktop=find(top,"desktop",0);
        if(!tablet) throw new Error("The native tablet is not ready.");
        tablet.shown=true;tablet.opacity=1;
        if(desktop && hasDialog(desktop,tablet,0)){captureSurface="dialogs";return desktop;}
        captureSurface="tablet";return tablet;
    }
    function focusedEditors(item,depth,out,target,x,y,budget) {
        if(!item || depth>24 || out.length>1 || !item.visible || ++budget.nodes>4096)return;
        if(item.focus && typeof item.insert==="function" && typeof item.forceActiveFocus==="function") {
            // The field's immediate container includes native edit decorations
            // such as the People pencil. A whole Window is never a field scope.
            var container=item.parent;
            if(container && container.shown===undefined && container.visible) {
                var point=target.mapToItem(container,x,y);
                if(point.x>=0 && point.y>=0 && point.x<container.width && point.y<container.height)out.push(item);
            }
        }
        for(var i=0;i<item.children.length;i++)focusedEditors(item.children[i],depth+1,out,target,x,y,budget);
    }
    function activateClickedEditor(item,x,y) {
        // Qt Window input layers can cover the visual childAt() result while the
        // actual event sets a descendant editor's local focus. Activate only an
        // unambiguous visible native field at this exact pointer position.
        var editors=[];focusedEditors(item,0,editors,item,x,y,{nodes:0});
        if(editors.length===1)editors[0].forceActiveFocus();
    }
    function modifiers(flags) {return (flags&1?Qt.ShiftModifier:0)|(flags&2?Qt.ControlModifier:0)|(flags&4?Qt.AltModifier:0)|(flags&8?Qt.MetaModifier:0);}
    function button(value) {return value===1?Qt.MiddleButton:value===2?Qt.RightButton:Qt.LeftButton;}
    function buttons(value) {return (value&1?Qt.LeftButton:0)|(value&2?Qt.RightButton:0)|(value&4?Qt.MiddleButton:0);}
    function focusedItem() {
        // OffscreenSurface installs this exact QQuickWindow as a context property.
        // Tablet and Desktop controls can have different attached Window scopes.
        var window=typeof offscreenWindow!=="undefined" ? offscreenWindow : topRoot().Window.window;
        return window ? window.activeFocusItem : null;
    }
    function text(value) {
        // A genuine input-method event preserves native plaintext, selection,
        // undo, readOnly, validators and masks without a shared system clipboard.
        var focused=focusedItem();
        if(focused && (focused.readOnly===true || focused.enabled===false))return false;
        if(focused && typeof focused.insert==="function" && typeof focused.cursorPosition==="number") {
            return nativeInput.commitText(focused,value);
        }
        var web=focused;
        while(web){
            if(typeof web.runJavaScript==="function"){
                // JSON quoting keeps committed visitor text out of executable source.
                web.runJavaScript('document.execCommand("insertText", false, '+JSON.stringify(value)+');');return true;
            }
            web=web.parent;
        }
        for(var i=0;i<value.length;i++) {
            // QtQuickTest's character overload asserts one UTF-16 code unit and
            // converts to Latin-1. It must never receive arbitrary Unicode text.
            if(value.charCodeAt(i)<32||value.charCodeAt(i)>126)return false;
            if(!events.keyClickChar(value.charAt(i),Qt.NoModifier,0))return false;
        }
        return true;
    }
    function clipboard(message) {
        var focused=focusedItem();
        function reply(value) {sendToScript({kind:"clipboard",revision:message.revision,requestId:message.sequence,text:String(value||"")});}
        // Qt password fields must never export their selected text.
        if(focused&&typeof focused.selectedText==="string") {
            if(focused.echoMode!==undefined&&focused.echoMode!==0){reply("");return;}
            var value=focused.selectedText;
            if(message.operation==="cut"&&value&&focused.readOnly!==true&&focused.enabled!==false)nativeInput.cutSelection(focused);
            reply(value);return;
        }
        var web=focused;
        while(web){
            if(typeof web.runJavaScript==="function") {
                var cut=message.operation==="cut";
                web.runJavaScript('(function(){var e=document.activeElement;if(e&&e.type==="password")return "";var text=(e&&typeof e.selectionStart==="number")?e.value.slice(e.selectionStart,e.selectionEnd):String(window.getSelection());'+(cut?'document.execCommand("cut");':'')+'return text;}())',reply);return;
            }
            web=web.parent;
        }
        reply("");
    }
    function keyCode(value) {
        var codes={Backspace:Qt.Key_Backspace,Tab:Qt.Key_Tab,Enter:Qt.Key_Return,Delete:Qt.Key_Delete,Insert:Qt.Key_Insert,Home:Qt.Key_Home,End:Qt.Key_End,PageUp:Qt.Key_PageUp,PageDown:Qt.Key_PageDown,ArrowLeft:Qt.Key_Left,ArrowRight:Qt.Key_Right,ArrowUp:Qt.Key_Up,ArrowDown:Qt.Key_Down,Escape:Qt.Key_Escape,F1:Qt.Key_F1,F2:Qt.Key_F2,F3:Qt.Key_F3,F4:Qt.Key_F4,F5:Qt.Key_F5,F6:Qt.Key_F6,F7:Qt.Key_F7,F8:Qt.Key_F8,F9:Qt.Key_F9,F10:Qt.Key_F10,F11:Qt.Key_F11,F12:Qt.Key_F12};
        return codes[value];
    }
    function fromScript(message) {
        try {
            if(message.kind==="cancelCapture") {activeCapture=null;return;}
            if(message.kind==="hide") {activeCapture=null;var root=find(topRoot(),"tabletRoot",0);if(root)root.shown=false;captureTarget=null;return;}
            if(message.kind==="focusTablet") {var tabletWindow=find(topRoot(),"tabletRoot",0);if(tabletWindow){tabletWindow.shown=true;if(typeof tabletWindow.raise==="function")tabletWindow.raise();}return;}
            if(message.kind==="capture") {
                var item=target();captureTarget=item;activeCapture=message;
                var width=Math.round(item.width),height=Math.round(item.height),surface=captureSurface;
                var tablet=find(topRoot(),"tabletRoot",0),origin=tablet.mapToItem(item,0,0);
                var tabletRect={x:origin.x,y:origin.y,width:tablet.width,height:tablet.height};
                if(width<1 || height<1 || width>2048 || height>2048) throw new Error("The native tablet display is too large.");
                if(!item.grabToImage(function(result){
                    var cancelled=activeCapture!==message;
                    if(!cancelled)activeCapture=null;
                    sendToScript({kind:"frame",sequence:message.sequence,revision:message.revision,width:width,height:height,surface:surface,tabletRect:tabletRect,cancelled:cancelled,saved:!cancelled&&result.saveToFile(message.path)});
                })) throw new Error("The native tablet display cannot be captured.");
            } else if(message.kind==="input") {
                var targetItem=captureTarget||target(),x=message.x*targetItem.width,y=message.y*targetItem.height,mods=modifiers(message.modifiers||0),accepted=true;
                if(message.event==="press")accepted=events.mousePress(targetItem,x,y,button(message.button),mods,0);
                else if(message.event==="release"){accepted=events.mouseRelease(targetItem,x,y,button(message.button),mods,0);if(accepted)activateClickedEditor(targetItem,x,y);}
                else if(message.event==="move")accepted=events.mouseMove(targetItem,x,y,0,buttons(message.buttons));
                else if(message.event==="wheel")accepted=events.mouseWheel(targetItem,x,y,Qt.NoButton,mods,message.deltaX,message.deltaY,0);
                else if(message.event==="text")accepted=text(message.text);
                else if(message.event==="clipboard")clipboard(message);
                else if(message.event==="key"){
                    var code=keyCode(message.key);
                    if(code!==undefined)accepted=events.keyClick(code,mods,0);
                    else if(message.key.length===1&&message.key.charCodeAt(0)>=32&&message.key.charCodeAt(0)<=126)accepted=events.keyClickChar(message.key,mods,0);
                    else accepted=text(message.key);
                }
                if(!accepted)throw new Error("The native tablet could not accept that input.");
            }
        }catch(error){sendToScript({kind:"error",revision:message.revision,operation:message.kind,message:String(error)});}
    }
}
