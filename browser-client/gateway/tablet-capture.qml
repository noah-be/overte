// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Window 2.2
import QtQuick.Controls 2.15 as Controls
import QtTest 1.2
import BrowserNativeInput 1.0

Item {
    id: helper
    width: 1; height: 1
    signal sendToScript(var message)
    TestEvent { id: events }
    NativeInput { id: nativeInput; onPrivateGuiReady: helper.completePrivateGrab(token,result) }
    property var captureTarget: null
    property var pointerSurface: null
    property var inputSurface: null
    property var savedSurface: null
    property var activeCapture: null
    property var privateGrab: null
    property string captureSurface: "tablet"
    property var pendingText: null
    property var textInputQueue: []
    property int textInputQueueUnits: 0
    Timer { id: textCommitTimer; interval: 5000; repeat: false
        onTriggered: helper.failTextInput(helper.pendingText,"The native text commit did not finish within five seconds.")
    }
    Component.onDestruction: cancelTextInput()
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
    function popupTarget(top) {
        // Controls2 reparents popup visuals under its window's Overlay, a sibling
        // of the native Desktop root. A tablet-only or desktop-only grab excludes it.
        var overlay=Controls.Overlay.overlay;
        if(!overlay || overlay.visible!==true || overlay.opacity===0)return null;
        if(!overlay.children || overlay.children.length>256)throw new Error("The native popup display is too complex.");
        var painted=false;
        for(var i=0;i<overlay.children.length;i++) {
            var child=overlay.children[i];
            if(child.visible===true && child.opacity!==0 && child.width>0 && child.height>0){painted=true;break;}
        }
        if(!painted)return null;
        // Attached Overlay belongs to this helper's private offscreen window.
        // Refuse unexpected parenting rather than grabbing another native window.
        var item=overlay,depth=0;
        while(item && item!==top && depth++<24)item=item.parent;
        if(item!==top)throw new Error("The native popup is outside its private GUI surface.");
        return top;
    }
    function target() {
        var top=topRoot(),tablet=find(top,"tabletRoot",0),desktop=find(top,"desktop",0);
        if(!tablet) throw new Error("The native tablet is not ready.");
        tablet.shown=true;tablet.opacity=1;
        var popup=popupTarget(top);if(popup){captureSurface="dialogs";return popup;}
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
    function cancelTextInput() {
        var pending=pendingText;pendingText=null;textInputQueue=[];textInputQueueUnits=0;
        if(textCommitTimer)textCommitTimer.stop();
        if(pending){pending.cancelled=true;pending.web=null;pending.focus=null;pending.surface=null;}
    }
    function currentTextTarget(pending) {
        var input=pointerSurface||inputSurface;
        if(!pending || pending.cancelled || !pending.web || !pending.focus || !input ||
           input.item!==pending.surface || input.revision!==pending.revision || input.navigationSequence!==pending.navigationSequence || String(pending.web.url)!==pending.url || focusedItem()!==pending.focus)return false;
        var item=pending.web,depth=0;
        while(item && item!==pending.surface && depth++<24)item=item.parent;
        return item===pending.surface;
    }
    function failTextInput(pending,reason) {
        if(!pending || pendingText!==pending || pending.cancelled)return;
        var revision=pending.revision;cancelTextInput();cancelPointer();
        sendToScript({kind:"error",revision:revision,operation:"input",message:reason});
    }
    function queueTextInput(message) {
        var pending=pendingText;
        if(!pending || pending.revision!==message.revision || pending.navigationSequence!==message.navigationSequence)return;
        if(!currentTextTarget(pending)){failTextInput(pending,"The native text target changed before commit.");return;}
        var units=JSON.stringify(message).length;
        // Bound both command metadata and retained text, even during a stalled
        // WebEngine callback. Navigation/reset/hide are never queued here.
        if(textInputQueue.length>=64 || textInputQueueUnits+units>262144){failTextInput(pending,"Too many native inputs are waiting for a text commit.");return;}
        textInputQueue.push(message);textInputQueueUnits+=units;
    }
    function finishTextInput(pending,accepted) {
        if(pending.cancelled || pendingText!==pending)return;
        if(!accepted || !currentTextTarget(pending)){failTextInput(pending,"The native tablet could not commit text to its focused field.");return;}
        var queued=textInputQueue;cancelTextInput();
        for(var i=0;i<queued.length;i++)fromScript(queued[i]);
    }
    function startWebText(web,focused,value) {
        var input=pointerSurface||inputSurface;
        if(!input || pendingText)return false;
        var url=String(web.url);if(!url || url==="undefined" || url==="null")return false;
        var pending={web:web,focus:focused,surface:input.item,url:url,revision:input.revision,navigationSequence:input.navigationSequence,cancelled:false};
        if(!currentTextTarget(pending))return false;
        pendingText=pending;textCommitTimer.restart();
        // Only a native editable activeElement receives a normal insertion.
        // No direct value/property assignment, synthetic change event or field ID.
        var source='(function(){if(String(location.href)!=='+JSON.stringify(url)+')return false;var e=document.activeElement;if(!e||e.readOnly||e.disabled||!(e.isContentEditable||e.nodeName==="INPUT"||e.nodeName==="TEXTAREA"))return false;return document.execCommand("insertText",false,'+JSON.stringify(value)+');})()';
        try{web.runJavaScript(source,function(accepted){if(!pending.cancelled)helper.finishTextInput(pending,accepted===true);});}
        catch(error){failTextInput(pending,"The native text commit could not be started.");return false;}
        return true;
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
                return startWebText(web,focused,value);
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
        function reply(value) {sendToScript({kind:"clipboard",revision:message.revision,navigationSequence:message.navigationSequence,requestId:message.sequence,text:String(value||"")});}
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
    function cancelPointer() {
        var held=pointerSurface;pointerSurface=null;
        // Release outside the owned GUI item: cancellation must not activate a
        // previously pressed control. No visitor-supplied target is involved.
        if(held)events.mouseRelease(held.item,-1,-1,button(held.button),Qt.NoModifier,0);
    }
    function completePrivateGrab(token,result) {
        var pending=privateGrab;
        if(!pending || pending.token!==token)return;
        // Cancellation invalidates the original capture, not the GPU ownership.
        privateGrab=null;pending.callback(result);
    }
    function grabOwned(item,token,callback) {
        if(item!==topRoot())return item.grabToImage(callback);
        if(privateGrab)return false;
        privateGrab={token:token,callback:callback};
        if(!nativeInput.grabPrivateGui(item,token)){privateGrab=null;return false;}
        return true;
    }
    function fromScript(message) {
        try {
            if(message.kind==="readyProbe") {
                // Only this loaded capture Item can acknowledge readiness. There
                // is no visitor command, script source or arbitrary evaluation.
                if(typeof message.revision==="number"&&message.revision%1===0&&message.revision>=1&&message.revision<=9007199254740991&&typeof message.probe==="number"&&message.probe%1===0&&message.probe>=1&&message.probe<=9007199254740991)
                    sendToScript({kind:"helperReady",revision:message.revision,probe:message.probe});
                return;
            }
            if(message.kind==="cancelCapture") {activeCapture=null;savedSurface=null;return;}
            if(message.kind==="resetInput") {cancelTextInput();cancelPointer();inputSurface=null;savedSurface=null;captureTarget=null;return;}
            if(message.kind==="displayFrame") {
                if(savedSurface && message.revision===savedSurface.revision && message.sequence===savedSurface.sequence && message.navigationSequence===savedSurface.navigationSequence){inputSurface=savedSurface;savedSurface=null;captureTarget=inputSurface.item;}
                return;
            }
            if(message.kind==="hide") {cancelTextInput();activeCapture=null;var root=find(topRoot(),"tabletRoot",0);if(root)root.shown=false;cancelPointer();captureTarget=null;inputSurface=null;savedSurface=null;return;}
            if(message.kind==="focusTablet") {var tabletWindow=find(topRoot(),"tabletRoot",0);if(tabletWindow){tabletWindow.shown=true;if(typeof tabletWindow.raise==="function")tabletWindow.raise();}return;}
            if(message.kind==="capture") {
                var item=target();activeCapture=message;
                var width=Math.round(item.width),height=Math.round(item.height),surface=captureSurface;
                var tablet=find(topRoot(),"tabletRoot",0),origin=tablet.mapToItem(item,0,0);
                var tabletRect={x:origin.x,y:origin.y,width:tablet.width,height:tablet.height};
                if(width<1 || height<1 || width>2048 || height>2048) throw new Error("The native tablet display is too large.");
                if(!grabOwned(item,message.sequence,function(result){
                    var cancelled=activeCapture!==message;
                    if(!cancelled)activeCapture=null;
                    var saved=!cancelled&&result!==null&&result.saveToFile(message.path);
                    if(saved)savedSurface={item:item,width:width,height:height,revision:message.revision,sequence:message.sequence,navigationSequence:message.navigationSequence};
                    sendToScript({kind:"frame",sequence:message.sequence,navigationSequence:message.navigationSequence,revision:message.revision,width:width,height:height,surface:surface,tabletRect:tabletRect,cancelled:cancelled,saved:saved});
                })) throw new Error("The native tablet display cannot be captured.");
            } else if(message.kind==="input") {
                if(pendingText){queueTextInput(message);return;}
                // Input belongs to pixels actually drawn and acknowledged by the
                // visitor, never the target selected for an outstanding GPU grab.
                var input=pointerSurface||inputSurface;
                if(!input || input.revision!==message.revision || input.navigationSequence!==message.navigationSequence)return;
                if(["press","release","cancel","move","wheel"].indexOf(message.event)!==-1 && message.frameSequence!==input.sequence)return;
                var targetItem=input.item,x=message.x*input.width,y=message.y*input.height,mods=modifiers(message.modifiers||0),accepted=true;
                if(message.event==="press"){
                    if(pointerSurface)return;
                    accepted=events.mousePress(targetItem,x,y,button(message.button),mods,0);
                    if(accepted)pointerSurface={item:input.item,width:input.width,height:input.height,revision:input.revision,sequence:input.sequence,navigationSequence:input.navigationSequence,button:message.button};
                }
                else if(message.event==="cancel"){if(pointerSurface&&message.button===pointerSurface.button)cancelPointer();return;}
                else if(message.event==="release"){if(!pointerSurface||message.button!==pointerSurface.button)return;pointerSurface=null;accepted=events.mouseRelease(targetItem,x,y,button(message.button),mods,0);if(accepted)activateClickedEditor(targetItem,x,y);}
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
