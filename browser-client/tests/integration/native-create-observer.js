// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Independent native observation. The only entity write is finally-only deletion
// of the single native-owned latch established after the genuine GUI Shape click.
function createNativeCreateObserver(config,api){
 var baseline=null,armed=false,owned=null,lastSequence=0;
 function authority(){return /^(?:hifi|overte):\/\/127\.0\.0\.2:45102(?:\/|$)/.test(String(api.href()));}
 function snapshot(){
  if(!authority()||!api.loaded())return null;
  var ids=api.ids(),values=[];if(ids.length>128)throw Error('Unexpected isolated scene size');
  for(var i=0;i<ids.length;i++){var e=api.properties(ids[i]);if(e.entityHostType!=='domain'||e.clientOnly===true)continue;e.children=api.children(e.id);if(e.children.length>64)throw Error('Unexpected entity child count');values.push(e);}
  if(values.length>64)throw Error('Unexpected domain entity count');return values;
 }
 function stable(list){return list.map(function(e){return{id:e.id,name:e.name,type:e.type};}).sort(function(a,b){return a.id<b.id?-1:a.id>b.id?1:0;});}
 function unchanged(list){if(!baseline)return false;return baseline.every(function(b){return list.some(function(e){return e.id===b.id&&e.name===b.name&&e.type===b.type;});});}
 function tick(){var list=snapshot();if(!list)return;
  if(armed&&!owned){if(!unchanged(list))throw Error('Preserved baseline changed');var additions=list.filter(function(e){return !baseline.some(function(b){return b.id===e.id;});});
   if(additions.length>1)throw Error('Ambiguous native Create result');
   if(additions.length===1){var e=additions[0];if((e.type!=='Shape'&&e.type!=='Box')||e.shape!=='Cube'||e.locked||api.children(e.id).length)throw Error('Unexpected native Create result');owned={id:e.id,originalName:e.name};api.emit('owned',{id:e.id});}
  }
  api.emit('snapshot',{entities:list,canRez:api.canRez(),version:api.version()});
 }
 function receive(command){
  if(!command||typeof command.sequence!=='number'||!isFinite(command.sequence)||Math.floor(command.sequence)!==command.sequence||command.sequence>9007199254740991||command.sequence<=lastSequence)return;lastSequence=command.sequence;
  if(!authority())throw Error('Refused non-isolated domain');var list=snapshot();if(!list)throw Error('Actual native entity tree is not loaded');
  if(command.action==='arm'){
   if(armed||owned)throw Error('Only one genuine Create attempt is admitted');
   if(list.length!==7||!list.every(function(e){return typeof e.name==='string'&&e.name.indexOf('Browser Lab ')===0;}))throw Error('Expected seven baseline entities');
   baseline=stable(list);armed=true;api.emit('armed',{baseline:baseline});
  }else if(command.action==='cleanup'){
   if(armed&&!owned){tick();list=snapshot();}
   if(!baseline||!unchanged(list))throw Error('Cleanup refuses a changed baseline');
   if(owned){var entity=list.filter(function(e){return e.id===owned.id;})[0];if(entity){if((entity.type!=='Shape'&&entity.type!=='Box')||entity.shape!=='Cube'||(entity.name!==owned.originalName&&entity.name!==config.name)||api.children(owned.id).length)throw Error('Cleanup refuses changed ownership');api.remove(owned.id);}}
   api.emit('cleanup-sent',{ownedCount:owned?1:0});
  }else throw Error('Unsupported observer command');
 }
 return{tick:tick,receive:receive};
}
if(typeof NATIVE_CREATE_OBSERVER!=='undefined'){
 (function(){var config=NATIVE_CREATE_OBSERVER,properties=['id','name','type','shape','color','dimensions','position','entityHostType','clientOnly','locked','parentID'];
 function emit(kind,data){print('NATIVE_CREATE_OBSERVER '+JSON.stringify({kind:kind,at:new Date().toISOString(),data:data}));}
 var observer=createNativeCreateObserver(config,{href:function(){return location.href;},loaded:function(){return !!location.isConnected;},ids:function(){return Entities.findEntities({x:0,y:0,z:0},256);},properties:function(id){return Entities.getEntityProperties(id,properties);},children:function(id){return Entities.getChildrenIDs(id);},canRez:function(){return Entities.canRez();},version:function(){return About.buildVersion;},remove:function(id){Entities.deleteEntity(id);},emit:emit});
 Audio.muted=true;MyAvatar.setGravity(0);MyAvatar.velocity={x:0,y:0,z:0};var busy=false;
 function cycle(){Audio.muted=true;try{observer.tick();}catch(e){emit('refused',{message:String(e.message||e)});}if(busy)return;busy=true;
 var request=new XMLHttpRequest();request.open('GET',config.commandURL+'?t='+Date.now());request.timeout=2000;request.onreadystatechange=function(){if(request.readyState!==4)return;busy=false;if(request.status===200)try{observer.receive(JSON.parse(request.responseText));}catch(e){emit('refused',{message:String(e.message||e)});}};request.send();}
 var interval=Script.setInterval(cycle,500);Script.scriptEnding.connect(function(){Script.clearInterval(interval);Audio.muted=true;});
 }());
}
