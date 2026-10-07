// SPDX-License-Identifier: Apache-2.0
// Observe existing gateway responses only; never fetch/retry an asset.
import {createHash} from 'node:crypto';
const formats=new Set(['png','dds','tga','jpg','jpeg']);
export function classifyAssetError(message){
 if(typeof message!=='string'||message.length>8192)return 'unknown';
 if(/^Asset server returned HTTP \d{3}\.$/.test(message))return 'upstream-http';
 if(message==='The asset origin is not enabled by the gateway administrator.')return 'origin-refused';
 if(['Asset exceeds the 32 MiB limit.','Invalid or oversized asset.'].includes(message))return 'asset-size';
 if(['Too many asset readers.','Too many queued asset requests.'].includes(message))return 'asset-capacity';
 if(['The asset session changed.','Asset service is not connected.'].includes(message))return 'session-changed';
 if(message==='Asset reader cancelled or timed out.'||message==='The native asset request timed out.'||message==='The operation was aborted due to timeout')return 'timeout-or-cancelled';
 if(['Too many asset redirects.','The asset redirect has no destination.'].includes(message))return 'redirect-refused';
 if(message==='fetch failed')return 'upstream-network';
 return 'unknown';
}
export class OriginalImageErrorCollector{
 constructor(origin,{deadlineMs=1000}={}){this.origin=new URL(origin).origin;this.deadlineMs=deadlineMs;this.queue=[];this.active=0;this.accepted=0;this.closed=false;this.records=[];this.dropped=0;this.waiters=[];}
 observe(response){
  if(this.closed||response.status()!==502)return;
  let address,original,format;
  try{address=new URL(response.url());if(address.origin!==this.origin||!/^\/api\/assets\/[a-zA-Z0-9_-]{1,128}$/.test(address.pathname)||address.searchParams.size!==1)return;
   original=address.searchParams.get('url');if(typeof original!=='string'||original.length>4096)return;
   format=new URL(original).pathname.match(/\.([a-zA-Z0-9]+)$/)?.[1].toLowerCase();if(!formats.has(format))return;
  }catch{return;}
  if(this.accepted>=128||this.queue.length>=32){this.dropped++;return;}
  this.accepted++;this.queue.push({response,format:format==='jpeg'?'jpg':format,urlSHA256:createHash('sha256').update(original).digest('hex')});this.pump();
 }
 pump(){while(!this.closed&&this.active<4&&this.queue.length){const job=this.queue.shift();this.active++;void this.read(job).finally(()=>{this.active--;this.pump();if(!this.active&&!this.queue.length){for(const done of this.waiters.splice(0))done();}});}}
 async read(job){
  let timer;
  const work=async()=>{
   const headers=await job.response.headers();if(this.closed)return 'body-unavailable';
   const length=headers['content-length'];
   if(!/^\d{1,5}$/.test(length??'')||Number(length)>8192||Number(length)<2)return 'body-unbounded';
   if(!/^application\/json(?:\s*;|$)/i.test(headers['content-type']??''))return 'body-not-json';
   // Both adapters expose the already received body; no network request is made.
   const bytes=Buffer.from(await (typeof job.response.body==='function'?job.response.body():job.response.buffer()));
   if(bytes.length!==Number(length)||bytes.length>8192)return 'body-invalid';
   try{return classifyAssetError(JSON.parse(bytes.toString('utf8'))?.error);}catch{return 'body-invalid';}
  };
  try{const category=await Promise.race([work(),new Promise(resolve=>{timer=setTimeout(()=>resolve('body-deadline'),this.deadlineMs);})]);if(!this.closed)this.records.push({urlSHA256:job.urlSHA256,format:job.format,category});}
  catch{if(!this.closed)this.records.push({urlSHA256:job.urlSHA256,format:job.format,category:'body-unavailable'});}
  finally{clearTimeout(timer);job.response=null;}
 }
 async finish(){
  if(!this.closed&&(this.active||this.queue.length)){let timer;await Promise.race([new Promise(resolve=>this.waiters.push(resolve)),new Promise(resolve=>{timer=setTimeout(resolve,this.deadlineMs);})]);clearTimeout(timer);}
  this.closed=true;this.dropped+=this.queue.length;this.queue=[];this.waiters=[];
  const aggregates={};for(const {format,category}of this.records){const key=format+':'+category;aggregates[key]=(aggregates[key]??0)+1;}
  return {schema:1,scope:'existing-owned-gateway-original-image-502-responses',extensionIsNotDecodedFormat:true,accepted:this.accepted,completed:this.records.length,dropped:this.dropped,unsettled:this.active,aggregates,entries:this.records.map(v=>({...v}))};
 }
}
