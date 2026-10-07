// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {pushToTalkCommand,pushToTalkState} from '../shared/push-to-talk.mjs';
export class PushToTalkSession {
    constructor(config){this.config=config;this.reset();}
    reset(){this.sequence=0;this.requested=false;this.state=undefined;}
    cancel(){this.requested=false;}
    current(){return this.config.connected()&&this.config.approved();}
    receive(message){
        const value=pushToTalkCommand(message);
        if(!this.current()||value.permissionRevision!==this.config.revision()||value.sequence!==this.sequence+1)return;
        if(value.held&&(value.sequence===Number.MAX_SAFE_INTEGER||this.config.muted()||this.state?.permissionRevision!==value.permissionRevision||!this.state.enabled))return;
        this.sequence=value.sequence;this.requested=value.held;
        this.config.sendNative(value);
    }
    receiveNative(message){
        const value=pushToTalkState(message);
        if(!this.current()||value.permissionRevision!==this.config.revision()||value.sequence!==this.sequence)return;
        this.state=value;this.config.sendBrowser(value);
    }
    allowsAudio(){
        const s=this.state;
        return !!(this.current()&&!this.config.muted()&&s&&s.permissionRevision===this.config.revision()&&!s.muted
            &&(!s.enabled||(this.requested&&s.held&&s.sequence===this.sequence)));
    }
}
