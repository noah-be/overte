export interface PushToTalkCommand {type:'pushToTalk';version:1;permissionRevision:number;sequence:number;held:boolean}
export interface PushToTalkState {type:'pushToTalkState';version:1;permissionRevision:number;sequence:number;enabled:boolean;held:boolean;muted:boolean}
export function pushToTalkCommand(value:unknown):PushToTalkCommand;
export function pushToTalkState(value:unknown):PushToTalkState;
