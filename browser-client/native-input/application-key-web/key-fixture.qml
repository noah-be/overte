// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtWebEngine 1.10
import QtTest 1.2
import BrowserNativeInput 1.0
Item {
 id: documentRoot; width:600; height:600
 property bool completed:false
 property bool passed:false
 property string evidence:""
 property int index:-1
 property var results:[]
 property var before:null
 property var current:null
 property var lastState:null
 property bool waiting:false
 property bool ready:false
 property bool sent:false
 property bool accepted:false
 property int quiet:0
 property string phase:"load"
 property var cases:[
  {kind:"web-normal",id:"plain",editable:true},
  {kind:"web-password",id:"password",editable:true},
  {kind:"web-readonly",id:"readonly",editable:false},
  {kind:"web-disabled",id:"disabled",editable:false,body:true,global:true},
  {kind:"web-noneditable",id:"body",editable:false,body:true,global:true},
  {kind:"qml-normal",qml:true}, {kind:"qml-password",qml:true,password:true},
  {kind:"qml-unconsumed",qml:true,global:true}
 ]
 Item {
  id: surface; objectName:"actualKeyWebParent"; width:480; height:600
  NativeInput { id: plugin; objectName:"actualApplicationKeyPlugin" }

  WebEngineProfile { id:profile;offTheRecord:true;persistentStoragePath:fixtureStorage;cachePath:fixtureStorage+"/cache";httpCacheType:WebEngineProfile.MemoryHttpCache }
  WebEngineView { id:web;anchors.fill:parent;profile:profile;url:fixtureURL
   onLoadingChanged:if(loadRequest.status===WebEngineLoadRequest.LoadSucceededStatus){documentRoot.ready=true;if(documentRoot.index<0)documentRoot.nextCase();else documentRoot.prepareCurrent();}
  }
  TextInput { id:qmlNormal;objectName:"normalEditor";x:10;y:20;width:360;height:42;text:"seed";visible:false;selectByMouse:true }
  TextInput { id:qmlPassword;objectName:"passwordEditor";x:10;y:20;width:360;height:42;text:"seed";echoMode:TextInput.Password;visible:false;selectByMouse:true }
  TextInput { id:qmlBody;objectName:"unconsumedEditor";x:10;y:20;width:360;height:42;text:"seed";readOnly:true;visible:false;selectByMouse:true
  }
 }
 TextInput { id:foreignEditor;x:500;y:20;width:90;height:42;text:"foreign";selectByMouse:true }
 TestEvent { id:events }
 Timer {id:deadline;interval:5000;onTriggered:documentRoot.finishCase(false,"case-deadline")}
 Timer {id:probe;interval:20;onTriggered:documentRoot.poll()}
 function stats(){return fixtureHost.statistics()}
 function delta(a,b,key){return a[key]-b[key]}
 function nextCase(){
  if(++index>=cases.length){fixtureHost.finishRefusals(plugin,surface,foreignEditor);evidence=JSON.stringify({cases:results});completed=true;passed=results.every(function(r){return r.passed;});return;}
  current=cases[index];lastState=null;waiting=false;sent=false;accepted=false;quiet=0;before=stats();phase="prepare";deadline.restart();
  web.visible=!current.qml;qmlNormal.visible=!!current.qml&&!current.password&&!current.global;qmlPassword.visible=!!current.password;qmlBody.visible=!!current.qml&&!!current.global;
  if(current.qml){prepareCurrent();return;}
  ready=false;web.reload();
 }
 function prepareCurrent(){
  if(!current||completed)return;
  if(current.qml){var item=current.global?qmlBody:current.password?qmlPassword:qmlNormal;var p=item.mapToItem(documentRoot,item.width-4,item.height/2);
   if(!events.mousePress(documentRoot,p.x,p.y,Qt.LeftButton,Qt.NoModifier,0)||!events.mouseRelease(documentRoot,p.x,p.y,Qt.LeftButton,Qt.NoModifier,0)){finishCase(false,"native-pointer-refused");return;}phase="await-focus";probe.restart();return;}
  if(!ready)return;
  var ordinal=index;waiting=true;
  web.runJavaScript('(function(){var e=document.getElementById('+JSON.stringify(current.id)+');if(!e)return null;var r=e.getBoundingClientRect();return {x:r.right-8,y:r.top+r.height/2};})()',function(p){
   waiting=false;if(index!==ordinal||completed)return;
   if(!p){finishCase(false,"authored-control-missing");return;}
   var mapped=web.mapToItem(documentRoot,p.x,p.y);
   if(!events.mousePress(documentRoot,mapped.x,mapped.y,Qt.LeftButton,Qt.NoModifier,0)||!events.mouseRelease(documentRoot,mapped.x,mapped.y,Qt.LeftButton,Qt.NoModifier,0)){finishCase(false,"native-pointer-refused");return;}
   phase="await-focus";probe.restart();
  });
 }
 function sendOnce(){if(sent)return;sent=true;before=stats();phase="actual-native-key";accepted=plugin.clickApplicationKey(surface,"x",0)===true;phase="await-key-state";probe.restart();}
 function poll(){
  if(completed||waiting||!current)return;
  if(current.qml){var item=current.global?qmlBody:current.password?qmlPassword:qmlNormal;
   if(!sent){if(item.activeFocus){sendOnce();}else probe.restart();return;}
   var text=item.text;var ok=current.global?text==="seed":text.length===5&&text.split("x").length-1===1;
   verify({length:text.length,xCount:text.split("x").length-1,input:-1,down:-1,up:-1,untrusted:-1,unchanged:text==="seed",changed:ok},ok);return;}
  waiting=true;var ordinal=index;
  web.runJavaScript('window.fixtureKeyboardRead('+JSON.stringify(current.id)+')',function(state){
   waiting=false;if(index!==ordinal||completed)return;
   if(!state){finishCase(false,"authored-read-refused");return;}
   if(!sent){if((current.body?state.bodyActive:state.active)&&fixtureHost.focusBelongsTo(surface)){sendOnce();}else probe.restart();return;}
   var ok=current.editable?state.changed&&state.length===5&&state.xCount===1&&state.input===1:state.unchanged||current.id==="body";
   verify(state,ok);
  });
 }
 function verify(state,valueOK){
  lastState=state;
  var now=stats(),pairs=current.global?1:0;
  var routeOK=accepted&&delta(now,before,"filterPresses")===1&&delta(now,before,"filterReleases")===1&&delta(now,before,"applicationPresses")===pairs&&delta(now,before,"applicationReleases")===pairs&&now.consumedKeys===0;
  var eventOK=current.qml||(state.down===1&&state.up===1&&state.untrusted===0&&state.input===(current.editable?1:0));
  if(valueOK&&routeOK&&eventOK){if(++quiet>=5){finishCase(true,"complete",state,now);return;}}else quiet=0;
  probe.restart();
 }
 function finishCase(ok,category,state,now){
  if(!current||completed)return;deadline.stop();probe.stop();now=now||stats();state=state||lastState||{};
  results.push({kind:current.kind,passed:ok===true,phase:phase,category:category,accepted:accepted,filterPresses:delta(now,before,"filterPresses"),filterReleases:delta(now,before,"filterReleases"),applicationPresses:delta(now,before,"applicationPresses"),applicationReleases:delta(now,before,"applicationReleases"),consumedKeys:now.consumedKeys,routeObservation:{windowReturnedPresses:delta(now,before,"windowReturnedPresses"),windowReturnedReleases:delta(now,before,"windowReturnedReleases"),windowAcceptedPresses:delta(now,before,"windowAcceptedPresses"),windowAcceptedReleases:delta(now,before,"windowAcceptedReleases"),filteredPresses:delta(now,before,"filteredPresses"),filteredReleases:delta(now,before,"filteredReleases"),consumedReleaseCount:delta(now,before,"consumedReleaseCount"),parentKeyPresses:delta(now,before,"parentKeyPresses"),parentKeyReleases:delta(now,before,"parentKeyReleases"),canvasForwardedPresses:delta(now,before,"canvasForwardedPresses"),canvasForwardedReleases:delta(now,before,"canvasForwardedReleases"),canvasApplicationAcceptedPresses:delta(now,before,"canvasApplicationAcceptedPresses"),canvasApplicationAcceptedReleases:delta(now,before,"canvasApplicationAcceptedReleases")},domDown:state.down===undefined?-1:state.down,domUp:state.up===undefined?-1:state.up,trustedInput:state.input===undefined?-1:state.input,untrustedEvents:state.untrusted===undefined?-1:state.untrusted,length:state.length===undefined?-1:state.length,xCount:state.xCount===undefined?-1:state.xCount});
  current=null;Qt.callLater(nextCase);
 }
}
