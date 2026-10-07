// SPDX-License-Identifier: Apache-2.0
// Test-laboratory subprocess ownership; completion is attached before any I/O awaits.
import {spawn} from 'node:child_process';

export function ownedAudioProcess(command, arguments_, {env, timeoutMs=12000, graceMs=1000, signal}={}) {
    if (!Number.isInteger(timeoutMs) || timeoutMs<1 || timeoutMs>30000 || !Number.isInteger(graceMs) || graceMs<1 || graceMs>2000) {
        throw Error('Audio subprocess bounds are invalid');
    }
    let resolveCompletion;
    const completion=new Promise(resolve=>{resolveCompletion=resolve;});
    let child, settled=false, stopping, deadline, escalation, abortListener;
    function finish(value) {
        if(settled)return;
        settled=true; clearTimeout(deadline);clearTimeout(escalation);
        if(abortListener)signal?.removeEventListener('abort',abortListener);
        resolveCompletion(value);
    }
    function requestStop(kind) {
        if(settled)return completion;
        stopping ||= kind;
        if(child && child.exitCode===null && child.signalCode===null) {
            child.kill('SIGTERM');
            escalation ||= setTimeout(()=>{
                if(!settled && child.exitCode===null && child.signalCode===null)child.kill('SIGKILL');
            },graceMs);
        }
        return completion;
    }
    if(signal?.aborted)finish({kind:'aborted',exitCode:null,signal:null});
    else {
        child=spawn(command,arguments_,{env,stdio:'ignore'});
        // Resolve typed failure instead of an early rejected promise which can
        // become unhandled while the caller still measures an output sink.
        child.once('error',error=>finish({kind:'spawn-error',exitCode:null,signal:null,
            errorCode:typeof error.code==='string' ? error.code : 'UNKNOWN'}));
        child.once('close',(exitCode,signal)=>finish({kind:stopping || 'exited',exitCode,signal}));
        deadline=setTimeout(()=>{requestStop('deadline');},timeoutMs);
        if(signal) {
            abortListener=()=>{requestStop('aborted');};signal.addEventListener('abort',abortListener,{once:true});
            if(signal.aborted)abortListener();
        }
    }
    return Object.freeze({completion,stop:()=>requestStop('stopped'),get pid(){return child?.pid;}});
}
