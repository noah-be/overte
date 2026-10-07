// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {pushToTalkState,type PushToTalkCommand,type PushToTalkState} from '../shared/push-to-talk.mjs';
export class BrowserPushToTalk {
    private revision=0;
    private approved=false;
    private sequence=0;
    private requested=false;
    private state?:PushToTalkState;
    private closed=false;
    constructor(private config:{current:(revision:number)=>boolean;armed:()=>boolean;send:(value:PushToTalkCommand)=>void;
        gate:(allowed:boolean)=>void;changed:()=>void}) {this.config.gate(false);}
    get enabled():boolean {return this.state?.enabled===true;}
    get nativeMuted():boolean|undefined {return this.state?.muted;}
    get talking():boolean {return !!(this.current()&&this.config.armed()&&this.requested&&this.state?.enabled&&this.state.held&&!this.state.muted&&this.state.sequence===this.sequence);}
    private current():boolean {return !this.closed&&this.approved&&this.revision>0&&this.config.current(this.revision);}
    private update():void {
        const s=this.state;
        this.config.gate(!!(this.current()&&this.config.armed()&&s&&!s.muted
            &&(!s.enabled||(this.requested&&s.held&&s.sequence===this.sequence))));
    }
    setAuthority(revision:number, approved:boolean):void {
        if(this.closed)return;
        if(this.revision!==revision||!approved||!this.approved){this.release();this.state=undefined;this.sequence=0;}
        this.revision=revision;this.approved=approved;this.update();
    }
    receive(message:unknown):void {
        const value=pushToTalkState(message);
        if(!this.current()||value.permissionRevision!==this.revision||value.sequence!==this.sequence)return;
        this.state=value;if(!value.enabled)this.requested=false;this.update();this.config.changed();
    }
    refreshMicrophone():void {if(!this.config.armed())this.release();this.update();}
    press():boolean {
        if(!this.current()||!this.enabled)return false;
        if(!this.requested&&this.config.armed()){
            if(this.sequence>=Number.MAX_SAFE_INTEGER-1)throw Error('Push-to-Talk command limit reached. Reconnect to continue.');
            this.requested=true;this.config.send({type:'pushToTalk',version:1,permissionRevision:this.revision,sequence:++this.sequence,held:true});
        }
        this.update();return true;
    }
    release():void {
        const wasRequested=this.requested;this.requested=false;this.update();
        if(wasRequested&&this.current()&&this.sequence<Number.MAX_SAFE_INTEGER)
            this.config.send({type:'pushToTalk',version:1,permissionRevision:this.revision,sequence:++this.sequence,held:false});
    }
    close():void {this.release();this.closed=true;this.approved=false;this.state=undefined;this.config.gate(false);}
}
