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
/** Extra named cycle after all original muted geometry gates; never a substitute. */
export async function runPeopleSyntheticAudioSuppression({pages,waitFor,ignore,unignore}){
 if(pages.length!==2)throw Error('Two owned synthetic peers required');
 const windows=[];let ignoreAttempted=false;
 const setMicrophone=async(page,enabled)=>{await page.bringToFront();const button=page.locator('#microphone');const old=await button.getAttribute('aria-pressed');if(old!==String(enabled))await button.click();await page.waitForFunction(value=>document.querySelector('#microphone').getAttribute('aria-pressed')===String(value),enabled,{timeout:10000});};
 const read=page=>page.evaluate(()=>({...window.__peopleSyntheticAudio.read(),connected:window.__overte?.connected===true,microphoneEnabled:document.querySelector('#microphone').getAttribute('aria-pressed')==='true'}));
 const phase=async(name,baseline=null)=>{
  const generations=await Promise.all(pages.map(page=>page.evaluate(value=>window.__peopleSyntheticAudio.begin(value),name)));
  const results=[];
  for(let index=0;index<2;index++){
   const frequency=PEOPLE_AUDIO_FREQUENCIES[1-index];
   const row=await waitFor(async()=>{const value=await read(pages[index]);return value.connected&&value.microphoneEnabled&&peopleAudioWindow(value,{phase:name,generation:generations[index],frequency,baseline:baseline?.[index],suppressed:name==='ignored'})?value:null;},'Actual reciprocal native mixed PCM '+name,15000);
   results.push(row);
  }
  windows.push({phase:name,rows:results});return results.map((row,index)=>index===0?row.tone659:row.tone440);
 };
 try{
  for(const page of pages){const pressed=await page.locator('#microphone').getAttribute('aria-pressed');if(pressed!=='false')throw Error('Original muted People gates must precede synthetic cycle');await setMicrophone(page,true);}
  const baseline=await phase('baseline');await pages[0].bringToFront();ignoreAttempted=true;await ignore();await phase('ignored',baseline);
  await unignore();ignoreAttempted=false;await phase('restored');
  return{completed:true,scope:'Synthetic owned-peer input through actual native mixer; no hardware permission/speech/playback-device claim',frequenciesHz:[...PEOPLE_AUDIO_FREQUENCIES],windows};
 }finally{
  if(ignoreAttempted)try{await pages[0].bringToFront();await unignore();}catch{}
  let clean=true;
  for(let index=0;index<pages.length;index++)try{await setMicrophone(pages[index],false);await pages[index].evaluate(()=>window.__peopleSyntheticAudio.close());await waitFor(async()=>{const row=await read(pages[index]);if(row.cleanupFailed)throw Error('Owned synthetic audio context cleanup failed');return row.activeTracks===0&&row.openContexts===0;},'Owned synthetic audio resources released',10000);}catch{clean=false;}
  if(!clean)throw Error('Owned synthetic microphone cleanup failed');
 }
}
