// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Authored synthetic input + read-only actual native mixed PCM; never raw audio evidence.
export const PEOPLE_AUDIO_FREQUENCIES=Object.freeze([440,659]);
/** Self-contained authored fixture installed before the actual BrowserSession opens. */
export function installPeopleSyntheticAudio({frequency}){
 if(![440,659].includes(frequency)||window.__peopleSyntheticAudio)throw Error('Invalid owned synthetic audio fixture');
 const ring=new Float32Array(48000);let count=0,cursor=0,phase=null,generation=0,outgoingBase=0;
 let context=null,oscillator=null,active=null,stopTrack=null,closed=false,outgoingFrames=0,pendingCloses=0,cleanupFailed=false;
 const original=window.WebSocket;
 window.WebSocket=class extends original{
  constructor(...args){super(...args);this.addEventListener('message',event=>{
   if(closed||!phase||!(event.data instanceof ArrayBuffer)||event.data.byteLength===0||event.data.byteLength>65536||event.data.byteLength%4!==0)return;
   const pcm=new Int16Array(event.data);
   for(let i=0;i<pcm.length;i+=2){ring[cursor]=(pcm[i]+pcm[i+1])/65536;cursor=(cursor+1)%ring.length;if(count<ring.length)count++;}
  });}
  send(data){if(!closed&&data instanceof ArrayBuffer&&data.byteLength<=65536&&data.byteLength%2===0){const samples=new Int16Array(data);if(samples.some(value=>Math.abs(value)>32))outgoingFrames++;}return super.send(data);}
 };
 function release(){const stop=stopTrack;stopTrack=null;active=null;try{oscillator?.stop();}catch{}oscillator=null;const old=context;context=null;if(old){pendingCloses++;try{Promise.resolve(old.close()).then(()=>pendingCloses--,()=>{pendingCloses--;cleanupFailed=true;});}catch{pendingCloses--;cleanupFailed=true;}}stop?.();}
 navigator.mediaDevices.getUserMedia=async function(constraints){
  if(closed||!constraints?.audio||constraints.video||active)throw Error('Owned synthetic stream admission refused');
  context=new AudioContext({sampleRate:48000});const gain=context.createGain(),destination=context.createMediaStreamDestination();
  try{
   oscillator=context.createOscillator();oscillator.frequency.value=frequency;gain.gain.value=.15;
   const track=destination.stream.getAudioTracks()[0];if(!track)throw Error('Synthetic audio track unavailable');
   active=track;stopTrack=track.stop.bind(track);track.stop=release;
   oscillator.connect(gain);gain.connect(destination);oscillator.start();await context.resume();
   if(closed)throw Error('Owned synthetic stream lifetime ended');
   return destination.stream;
  }catch(error){release();throw error;}
 };
 function amplitude(hz){if(count!==ring.length)return null;let real=0,imaginary=0;
  for(let i=0;i<ring.length;i++){const sample=ring[(cursor+i)%ring.length],angle=2*Math.PI*hz*i/48000;real+=sample*Math.cos(angle);imaginary+=sample*Math.sin(angle);}
  return 2*Math.hypot(real,imaginary)/ring.length;
 }
 window.__peopleSyntheticAudio={
  begin(value){if(!['baseline','ignored','restored'].includes(value)||closed)throw Error('Invalid synthetic phase');phase=value;generation++;outgoingBase=outgoingFrames;count=0;cursor=0;ring.fill(0);return generation;},
  read(){return{phase,generation,samples:count,rate:48000,tone440:amplitude(440),tone659:amplitude(659),outgoingNonzeroFrames:outgoingFrames,phaseOutgoingNonzeroFrames:outgoingFrames-outgoingBase,activeTracks:active?.readyState==='live'?1:0,openContexts:(context?1:0)+pendingCloses,cleanupFailed};},
  close(){if(closed)return;closed=true;release();count=0;ring.fill(0);phase=null;}
 };
 window.addEventListener('pagehide',()=>window.__peopleSyntheticAudio.close(),{once:true});
}
export function peopleAudioWindow(row,{phase,generation,frequency,baseline=null,suppressed=false}){
 if(!row||row.phase!==phase||row.generation!==generation||row.samples!==48000||row.rate!==48000||row.activeTracks!==1||row.phaseOutgoingNonzeroFrames<10)return false;
 const value=frequency===440?row.tone440:frequency===659?row.tone659:null;
 if(typeof value!=='number'||!Number.isFinite(value)||value<0)return false;
 if(suppressed)return typeof baseline==='number'&&Number.isFinite(baseline)&&baseline>.001&&value<.0001&&value<baseline*.01;
 return value>.001;
}
/** Use only genuine controls: a modal native Tablet must not cover microphone. */
export async function setPeopleSyntheticMicrophone(page,enabled){
 await page.bringToFront();
 if(await page.evaluate(()=>window.__overte?.tabletVisible))await page.getByRole('button',{name:'Close tablet',exact:true}).click();
 await page.waitForFunction(()=>!window.__overte?.tabletVisible,undefined,{timeout:10000});
 const button=page.locator('#microphone'),old=await button.evaluate(element=>element.getAttribute('aria-pressed'));
 if(old!==String(enabled))await button.click();
 await page.waitForFunction(value=>document.querySelector('#microphone').getAttribute('aria-pressed')===String(value),enabled,{timeout:10000});
}
/** Native open returns Home: the caller must re-enter genuine People via its painted frame. */
export async function reopenPeopleSyntheticTablet(page,enterPeople){
 await page.bringToFront();
 const opened=!await page.evaluate(()=>window.__overte?.tabletVisible);
 if(opened){if(typeof enterPeople!=='function')throw Error('A genuine People navigation callback is required');await page.locator('#tablet').click();}
 await page.waitForFunction(()=>window.__overte?.tabletVisible&&window.__peopleAudit.frame?.tabletRect,undefined,{timeout:30000});
 if(opened)await enterPeople();
}
/** Fixed scalar projection, with no field names, errors, participant IDs or PCM. */
export function projectPeopleAudioCheckpoint(phase,event,visitorOrdinal,row=null,category='none'){
 if(!['enable','baseline','ignore','ignored','unignore','restored','cleanup'].includes(phase)||
    !['start','sample','accepted','failed','complete'].includes(event)||
    !Number.isInteger(visitorOrdinal)||visitorOrdinal<0||visitorOrdinal>2||
    !['none','timeout','operation-refused','probe-cleanup-failed'].includes(category))throw Error('Invalid owned audio checkpoint');
 const numeric=(key,max)=>typeof row?.[key]==='number'&&Number.isFinite(row[key])&&row[key]>=0&&row[key]<=max?row[key]:null;
 const boolean=key=>typeof row?.[key]==='boolean'?row[key]:null;
 return{phase,event,visitorOrdinal,category,generation:numeric('generation',2147483647),samples:numeric('samples',48000),
  rate:numeric('rate',192000),tone440:numeric('tone440',2),tone659:numeric('tone659',2),
  phaseOutgoingNonzeroFrames:numeric('phaseOutgoingNonzeroFrames',2147483647),activeTracks:numeric('activeTracks',1),
  openContexts:numeric('openContexts',2),connected:boolean('connected'),microphoneEnabled:boolean('microphoneEnabled'),cleanupFailed:boolean('cleanupFailed')};
}
/** Extra named cycle after all original muted geometry gates; never a substitute. */
export async function runPeopleSyntheticAudioSuppression({pages,waitFor,ignore,unignore,onCheckpoint=()=>{}}){
 if(pages.length!==2||typeof onCheckpoint!=='function')throw Error('Two owned synthetic peers and one checkpoint receiver required');
 const windows=[],cleanupFailures=[];let ignoreAttempted=false,primary=null,result=null,checkpointFailed=false,emitted=0,currentPhase='enable',currentVisitor=0;
 const category=error=>error?.name==='TimeoutError'||String(error?.message||'').endsWith(' deadline')?'timeout':'operation-refused';
 const checkpoint=(phase,event,index,row=null,errorCategory='none')=>{
  if(emitted>=128)return;
  emitted++;try{onCheckpoint(projectPeopleAudioCheckpoint(phase,event,index,row,errorCategory));}catch{checkpointFailed=true;}
 };
 const read=page=>page.evaluate(()=>({...window.__peopleSyntheticAudio.read(),connected:window.__overte?.connected===true,microphoneEnabled:document.querySelector('#microphone').getAttribute('aria-pressed')==='true'}));
 const phase=async(name,baseline=null)=>{
  currentPhase=name;currentVisitor=0;checkpoint(name,'start',0);
  const generations=await Promise.all(pages.map(page=>page.evaluate(value=>window.__peopleSyntheticAudio.begin(value),name)));
  const results=[];
  for(let index=0;index<2;index++){
   const frequency=PEOPLE_AUDIO_FREQUENCIES[1-index];currentVisitor=index+1;let latest=null,samples=0;
   try{
    const row=await waitFor(async()=>{const value=await read(pages[index]);latest=value;if(samples++<12)checkpoint(name,'sample',index+1,value);return value.connected&&value.microphoneEnabled&&peopleAudioWindow(value,{phase:name,generation:generations[index],frequency,baseline:baseline?.[index],suppressed:name==='ignored'})?value:null;},'Actual reciprocal native mixed PCM '+name,15000);
    results.push(row);checkpoint(name,'accepted',index+1,row);
   }catch(error){checkpoint(name,'failed',index+1,latest,category(error));throw error;}
  }
  windows.push({phase:name,rows:results});checkpoint(name,'complete',0);return results.map((row,index)=>index===0?row.tone659:row.tone440);
 };
 try{
  for(let index=0;index<pages.length;index++){
   currentVisitor=index+1;checkpoint('enable','start',index+1);
   const pressed=await pages[index].locator('#microphone').evaluate(element=>element.getAttribute('aria-pressed'));
   if(pressed!=='false')throw Error('Original muted People gates must precede synthetic cycle');
   await setPeopleSyntheticMicrophone(pages[index],true);checkpoint('enable','accepted',index+1,await read(pages[index]));
  }
  const baseline=await phase('baseline');currentPhase='ignore';currentVisitor=1;checkpoint('ignore','start',1);ignoreAttempted=true;await ignore();checkpoint('ignore','accepted',1);await phase('ignored',baseline);
  currentPhase='unignore';currentVisitor=1;checkpoint('unignore','start',1);await unignore();ignoreAttempted=false;checkpoint('unignore','accepted',1);await phase('restored');
  result={completed:true,scope:'Synthetic owned-peer input through actual native mixer; no hardware permission/speech/playback-device claim',frequenciesHz:[...PEOPLE_AUDIO_FREQUENCIES],windows};
 }catch(error){primary=error;checkpoint(currentPhase,'failed',currentVisitor,null,category(error));}
 // Keep the original primary exception; cleanup is a separate fixed failure row.
 checkpoint('cleanup','start',0);
 if(ignoreAttempted)try{await unignore();}catch(error){cleanupFailures.push({visitorOrdinal:1,operation:'restore-ignore',category:category(error)});checkpoint('cleanup','failed',1,null,category(error));}
 for(let index=0;index<pages.length;index++){
  try{await setPeopleSyntheticMicrophone(pages[index],false);}catch(error){cleanupFailures.push({visitorOrdinal:index+1,operation:'microphone-mute',category:category(error)});checkpoint('cleanup','failed',index+1,null,category(error));}
  // Release owned fixture resources even if a genuine control operation failed.
  try{
   await pages[index].evaluate(()=>window.__peopleSyntheticAudio.close());let latest=null,samples=0;
   try{await waitFor(async()=>{const row=await read(pages[index]);latest=row;if(samples++<12)checkpoint('cleanup','sample',index+1,row);if(row.cleanupFailed)throw Error('Owned synthetic audio context cleanup failed');return row.activeTracks===0&&row.openContexts===0;},'Owned synthetic audio resources released',10000);}
   catch(error){checkpoint('cleanup','failed',index+1,latest,'probe-cleanup-failed');throw error;}
  }catch(error){cleanupFailures.push({visitorOrdinal:index+1,operation:'fixture-release',category:'probe-cleanup-failed'});}
 }
 checkpoint('cleanup',cleanupFailures.length?'failed':'complete',0,null,cleanupFailures.length?'probe-cleanup-failed':'none');
 if(primary)throw primary;
 if(cleanupFailures.length)throw Error('Owned synthetic microphone cleanup failed');
 if(checkpointFailed)throw Error('Owned synthetic audio checkpoint failed');
 return{...result,cleanup:{completed:true,failures:[]}};
}
