// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// An actual task boundary lets worker messages/cancellation run between tiles;
// Promise.resolve alone would remain in one unbounded microtask checkpoint.
interface Options {signal?:AbortSignal;channelFactory?:()=>MessageChannel}
const aborted=()=>new DOMException('Owned worker processing was cancelled','AbortError');
export class WorkerTaskYield {
  private channel?:MessageChannel;private closed=false;private sequence=0;
  private pending?:{id:number;resolve():void;reject(error:unknown):void};
  private readonly abort=()=>this.close();
  constructor(private readonly options:Options={}){
    if(options.signal?.aborted)this.closed=true;
    else options.signal?.addEventListener('abort',this.abort,{once:true});
  }
  yield():Promise<void>{
    if(this.closed)return Promise.reject(aborted());
    if(this.pending)return Promise.reject(Error('Only one owned worker continuation can be pending'));
    if(!this.channel){
      try{this.channel=this.options.channelFactory?.()??new MessageChannel();}
      catch(error){this.close(error);return Promise.reject(error);}
      this.channel.port1.onmessage=event=>{
        if(this.closed||!this.pending||event.data!==this.pending.id)return;
        const pending=this.pending;this.pending=undefined;pending.resolve();
      };
      this.channel.port1.onmessageerror=()=>this.close(Error('Owned worker continuation could not be delivered'));
    }
    return new Promise<void>((resolve,reject)=>{
      const id=++this.sequence;this.pending={id,resolve,reject};
      try{this.channel!.port2.postMessage(id);}catch(error){this.close(error);}
    });
  }
  close(error:unknown=aborted()):void{
    if(this.closed)return;this.closed=true;this.options.signal?.removeEventListener('abort',this.abort);
    const pending=this.pending;this.pending=undefined;
    if(this.channel){this.channel.port1.onmessage=null;this.channel.port1.onmessageerror=null;this.channel.port1.close();this.channel.port2.close();this.channel=undefined;}
    pending?.reject(error);
  }
}
