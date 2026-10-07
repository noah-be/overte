// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtQuick.Window 2.2
import QtWebEngine 1.10
import QtTest 1.2
import BrowserNativeInput 1.0
Window {
 id: win; width: 600; height: 600; visible: true
 property bool completed: false
 property bool passed: false
 property string evidence: ""
 onActiveChanged: helper.maybeStart()
 Item {
  id: helper; anchors.fill: parent
  NativeInput { id: measuredNativeInput }
  // Test-only scalar observation. Deliver exactly one unchanged native call.
  property var nativeInput: ({commitWebText:function(target,root,text){
   helper.nativeCommitObserved=true;
   var accepted=measuredNativeInput.commitWebText(target,root,text);
   helper.nativeCommitAccepted=accepted===true;
   helper.nativeGuardStage=measuredNativeInput?measuredNativeInput.webCommitStage():"object-destroyed";
   helper.nativeGuardReason=measuredNativeInput?measuredNativeInput.webCommitGuard():"object-destroyed";return accepted;
  },commitWebPasswordText:function(target,root,text){
   helper.nativeCommitObserved=true;
   var accepted=measuredNativeInput.commitWebPasswordText(target,root,text);
   helper.nativeCommitAccepted=accepted===true;
   helper.nativeGuardStage=measuredNativeInput?measuredNativeInput.webCommitStage():"object-destroyed";
   helper.nativeGuardReason=measuredNativeInput?measuredNativeInput.webCommitGuard():"object-destroyed";return accepted;
  }})
  TestEvent { id: events }
  WebEngineProfile { id: editorProfile; offTheRecord:true; persistentStoragePath:fixtureStorage; cachePath:fixtureStorage+"/cache"; httpCacheType:WebEngineProfile.MemoryHttpCache }
  WebEngineView { id: web; anchors.fill: parent; url: fixtureURL; profile:editorProfile
   onLoadingChanged: if(loadRequest.status===WebEngineLoadRequest.LoadSucceededStatus){if(helper.reloadProbe){helper.reloadProbe=false;helper.checkValue();}else{helper.documentReady=true;helper.maybeStart();}}
  }
  property bool started: false
  property bool documentReady: false
  property bool reloadProbe: false
  property var inputSurface: ({item:helper,revision:1,navigationSequence:1})
  property var pointerSurface: null
  property var pendingText: null
  property var textInputQueue: []
  property int textInputQueueUnits: 0
  property int index: -1
  property var results: []
  property var current: null
  property var inputPreparation: null
  property bool waiting: false
  property bool rejected: false
  property var targetChecks: []
  property string domRefusal: "unobserved"
  function observeTextTarget(reason,current){if(targetChecks.length<16)targetChecks.push(reason);return current;}
  property string observedStage: "case-start"
  property string observedError: "none"
  property bool nativeCommitObserved: false
  property bool nativeCommitAccepted: false
  property string nativeGuardStage: "not-called"
  property string nativeGuardReason: "not-called"
  property int beforeLength: -1
  property int beforeSelectionLength: -1
  property int afterLength: -1
  property int afterSelectionLength: -1
  property var cases: [
   {id:"plain",text:"Über 世界 👋",expected:"Über 世界 👋",kind:"unicode-text"},
   {id:"number",text:"1.1",expected:"1.1",kind:"native-number"},
   {id:"area",text:"Line 世界 👋",expected:"Line 世界 👋",kind:"textarea"},
   {id:"rich",text:"<b>literal 世界</b>",expected:"<b>literal 世界</b>",kind:"literal-contenteditable"},
   {id:"password",text:"Aé👋Z",expected:"Aé👋Z",kind:"password-unicode"},
   {id:"password",action:"undo",expected:"abc",kind:"password-native-undo"},
   {id:"password",action:"redo",expected:"Aé👋Z",kind:"password-native-redo"},
   {id:"password",text:"123456789",expected:"12345678",kind:"password-native-maxlength"},
   {id:"readonly",text:"changed",expected:"unchanged",refused:true,kind:"readonly"},
   {id:"disabled",text:"changed",expected:"unchanged",refused:true,kind:"disabled"},
   {id:"plain",text:"cancelled",expected:"Über 世界 👋",cancel:true,kind:"immediate-cancel"},
   {id:"plain",text:"cancelled",expected:"abc",navigate:true,kind:"navigation-cancel"},
   {id:"password",text:"cancelled",expected:"abc",cancel:true,kind:"password-immediate-cancel"},
   {id:"password",text:"cancelled",expected:"abc",navigate:true,kind:"password-navigation-cancel"}
  ]
  Timer { id:textCommitTimer; interval:5000; onTriggered:{helper.observedStage="commit-deadline";helper.failTextInput(helper.pendingText,"The native text commit did not finish within five seconds.");} }
  Timer { id:caseDeadline; interval:5000; onTriggered:{helper.observedStage="value-deadline";helper.completeCase(false);} }
  Timer { id:valueProbe; interval:20; onTriggered:helper.probeCase() }
  // requestActivate is asynchronous. Start only on the actual native window
  // activation and loaded-document state; never force an editor's focus.
  function maybeStart(){
   if(started||!documentReady||!win.active)return;
   started=true;nextCase();
  }
  function focusedItem(){return win.activeFocusItem;}
  function cancelPointer(){pointerSurface=null;}
  function errorCategory(reason){
   if(reason==="The native tablet could not commit text to its focused field.")return "focused-field-refused";
   if(reason==="The native text commit could not be started.")return "commit-start-refused";
   if(reason==="The native text commit did not finish within five seconds.")return "commit-deadline";
   return "unknown-fixed-error";
  }
  function sendToScript(message){if(message.kind==="error"){observedError=errorCategory(message.message);rejected=true;if(current&&current.refused)checkValue();else completeCase(false);}}
  function fromScript(message){if(message.fixtureComplete)checkValue();else if(message.event==="key")events.keyClick(Qt.Key_Tab,Qt.NoModifier,0);}
  __PRODUCTION_METHODS__
  function readExpression(id,expected){return '(function(){var e=document.getElementById('+JSON.stringify(id)+');if(!e)return {equal:false,length:-1,selectionLength:-1};var v=e.isContentEditable?e.innerText:e.value;return {equal:v==='+JSON.stringify(expected)+',length:Math.min(65536,v.length),selectionLength:typeof e.selectionStart==="number"&&typeof e.selectionEnd==="number"?Math.min(65536,Math.abs(e.selectionEnd-e.selectionStart)):-1};})()';}
  function checkValue(){
   if(!current||inputPreparation||waiting)return;waiting=true;observedStage="verify-value";
   var ordinal=index,entry=current;
   web.runJavaScript(readExpression(entry.id,entry.expected),function(observation){
    waiting=false;if(index!==ordinal||win.completed)return;
    afterLength=observation.length;afterSelectionLength=observation.selectionLength;
    if(observation.equal===true&&(!entry.refused||rejected))completeCase(true);else valueProbe.restart();
   });
  }
  function completeCase(ok){
   if(win.completed||!current)return;
   caseDeadline.stop();valueProbe.stop();inputPreparation=null;cancelTextInput();results.push({kind:current.kind,passed:ok===true,stage:observedStage,errorCategory:observedError,targetChecks:targetChecks.slice(),domRefusal:domRefusal,nativeCommitObserved:nativeCommitObserved,nativeCommitAccepted:nativeCommitAccepted,nativeGuardStage:nativeGuardStage,nativeGuardReason:nativeGuardReason,beforeLength:beforeLength,beforeSelectionLength:beforeSelectionLength,afterLength:afterLength,afterSelectionLength:afterSelectionLength});
   if(!ok){win.evidence=JSON.stringify({cases:results});win.completed=true;win.passed=false;return;}
   current=null;Qt.callLater(nextCase);
  }
  function preparationExpression(id,needsSelection,selectionAck){
   return '(function(){var e=document.getElementById('+JSON.stringify(id)+');if(!e||document.activeElement!==e)return false;if(!'+JSON.stringify(needsSelection)+')return true;var v=e.isContentEditable?e.innerText:e.value;if(typeof e.selectionStart==="number"&&typeof e.selectionEnd==="number")return e.selectionStart===0&&e.selectionEnd===v.length;if(e.isContentEditable){var selected=window.getSelection();return !!selected&&e.contains(selected.anchorNode)&&e.contains(selected.focusNode)&&selected.toString()===v;}return e.type==="number"&&typeof window.fixtureSelectionAck==="function"&&window.fixtureSelectionAck(e)>'+JSON.stringify(selectionAck)+';})()';
  }
  function probeCase(){if(inputPreparation)probePreparation();else checkValue();}
  function probePreparation(){
   if(!inputPreparation||waiting||win.completed)return;
   var preparation=inputPreparation;waiting=true;observedStage="await-input-state";
   web.runJavaScript(preparationExpression(preparation.entry.id,!preparation.entry.action,preparation.selectionAck),function(ready){
    if(win.completed||inputPreparation!==preparation||index!==preparation.ordinal)return;
    waiting=false;
    if(ready===true){inputPreparation=null;performPreparedInput(preparation.ordinal,preparation.entry);}else valueProbe.restart();
   });
  }
  function performPreparedInput(ordinal,entry){
   if(win.completed||index!==ordinal||current!==entry)return;
   if(entry.action){
    var mods=entry.action==="redo"?(Qt.ControlModifier|Qt.ShiftModifier):Qt.ControlModifier;
    observedStage="undo-redo";
    if(!events.keyClick(Qt.Key_Z,mods,0)){completeCase(false);return;}checkValue();return;
   }
   observedStage="start-web-text";
   if(!startWebText(web,focusedItem(),entry.text)){if(entry.refused){rejected=true;checkValue();}else completeCase(false);return;}
   if(win.completed)return;observedStage="await-text-completion";
   if(entry.navigate){cancelTextInput();inputSurface.navigationSequence++;reloadProbe=true;web.reload();return;}
   if(entry.cancel){cancelTextInput();checkValue();return;}
   textInputQueue.push({fixtureComplete:true});
  }
  function nextCase(){
   if(win.completed)return;
   if(++index>=cases.length){win.evidence=JSON.stringify({cases:results});win.passed=true;win.completed=true;return;}
   current=cases[index];targetChecks=[];domRefusal="unobserved";rejected=false;waiting=false;observedStage="geometry-read";observedError="none";nativeCommitObserved=false;nativeCommitAccepted=false;nativeGuardStage="not-called";nativeGuardReason="not-called";beforeLength=-1;beforeSelectionLength=-1;afterLength=-1;afterSelectionLength=-1;caseDeadline.restart();
   var ordinal=index,entry=current;
   // Geometry read is fixed to this authored local fixture. Editing uses only
   // native pointer/key events and the exact production text callback below.
   web.runJavaScript('(function(){var e=document.getElementById('+JSON.stringify(entry.id)+');if(!e)return null;var r=e.getBoundingClientRect();var v=e.isContentEditable?e.innerText:e.value;return {x:r.x+r.width/2,y:r.y+r.height/2,selectionAck:window.fixtureSelectionAck(e),length:Math.min(65536,v.length),selectionLength:typeof e.selectionStart==="number"&&typeof e.selectionEnd==="number"?Math.min(65536,Math.abs(e.selectionEnd-e.selectionStart)):-1};})()',function(point){
    if(index!==ordinal||win.completed||!point){completeCase(false);return;}
    observedStage="geometry-ready";beforeLength=point.length;beforeSelectionLength=point.selectionLength;
    var mapped=web.mapToItem(helper,point.x,point.y);
    if(entry.refused&&entry.id==="disabled"){
     observedStage="disabled-background-press";
     if(!events.mousePress(helper,580,580,Qt.LeftButton,Qt.NoModifier,0)){completeCase(false);return;}
     observedStage="disabled-background-release";
     if(!events.mouseRelease(helper,580,580,Qt.LeftButton,Qt.NoModifier,0)){completeCase(false);return;}
    }
    observedStage="pointer-press";
    if(!events.mousePress(helper,mapped.x,mapped.y,Qt.LeftButton,Qt.NoModifier,0)){completeCase(false);return;}
    observedStage="pointer-release";
    if(!events.mouseRelease(helper,mapped.x,mapped.y,Qt.LeftButton,Qt.NoModifier,0)){completeCase(false);return;}
    if(!entry.action){
     observedStage="select-all";
     if(!events.keyClick(Qt.Key_A,Qt.ControlModifier,0)){completeCase(false);return;}
    }
    // Qt event dispatch returns before Chromium processes pointer/key IPC.
    // Observe the actual authored editor state inside the same case deadline.
    if(entry.refused&&entry.id==="disabled"){performPreparedInput(ordinal,entry);return;}
    inputPreparation={ordinal:ordinal,entry:entry,selectionAck:point.selectionAck};probePreparation();
   });
  }
 }
}
