import type {PushToTalkCommand,PushToTalkState} from '../shared/push-to-talk.mjs';
export class PushToTalkSession {
    constructor(config:{connected:()=>boolean;approved:()=>boolean;revision:()=>number;muted:()=>boolean;
        sendNative:(value:PushToTalkCommand)=>void;sendBrowser:(value:PushToTalkState)=>void});
    reset():void;
    cancel():void;
    receive(message:unknown):void;
    receiveNative(message:unknown):void;
    allowsAudio():boolean;
}
