// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Test-owned only. Never used by the gateway, native API or wire protocol.
import {constants} from 'node:fs';
import {mkdtemp,open,realpath,rm,lstat} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {preparationDiagnostics,safePreparationDiagnostic} from './preparation-diagnostics.mjs';
const LIMIT=16384;
const errnos=new Map([['Operation not permitted',1],['Permission denied',13],['No such file or directory',2],['Invalid argument',22],['Cannot allocate memory',12],['No buffer space available',105],['Input/output error',5]]);
// Exact literal operations from bubblewrap v0.9.0; paths/arguments never escape.
const operations=new Map([['capset failed','bubblewrap-capset'],['capget failed','bubblewrap-capget'],['setting up uid map','bubblewrap-uid-map'],['setting up gid map','bubblewrap-gid-map'],['error writing to setgroups','bubblewrap-setgroups'],['prctl(PR_SET_NO_NEW_PRIVS) failed','bubblewrap-nnp'],['Creating new namespace failed','bubblewrap-namespace']]);
// Exact fixed categories from the immutable owner admission module.
const admissionRefusals=new Set(['bridge-port','broad-runtime','caller-policy','config-schema','duplicate-bind-target','duplicate-key','environment-argument','filesystem-target','headless-probe-display','headless-probe-environment','invalid-record','invalid-string','isolation-prefix','managed-address','managed-scope','missing-bind-argument','missing-filesystem-argument','missing-required-boundary','missing-worker-delimiter','namespace-attestation-mismatch','noncanonical-path','owner-capability-retirement','owner-parent','owner-profile','parent-mismatch','policy-schema','private-environment','public-runtime-root','record-size-changed','route-attestation','runtime-environment-path','runtime-policy','session-directory-ownership','session-file-type','session-scope','unapproved-bind','unexpected-managed-record','unknown-worker-option','unsealed-or-unbounded-record','webengine-path','worker-arguments','worker-command','worker-executable','working-directory','writable-host-bind']);
export function projectNetworkTestStderr(bytes,observedBytes,streamsClosed=false) {
    if(!Buffer.isBuffer(bytes)||bytes.length>LIMIT||!Number.isSafeInteger(observedBytes)||observedBytes<bytes.length||typeof streamsClosed!=='boolean')throw Error('Network test stderr projection refused');
    const diagnostic=preparationDiagnostics('OVERTE_NET_NATIVE_STARTED');diagnostic.observe(bytes);
    const candidates=[];
    const lines=bytes.toString('utf8').split('\n');if(observedBytes>bytes.length)lines.pop();
    for(const line of lines) {
        const match=/^bwrap: (.{1,64}): (.{1,64})$/.exec(line);
        if(match&&operations.has(match[1])&&errnos.has(match[2]))candidates.push({operation:operations.get(match[1]),errnoReported:errnos.get(match[2])});
    }
    const same=candidates.length>0&&candidates.every(v=>v.operation===candidates[0].operation&&v.errnoReported===candidates[0].errnoReported);
    // Only fixed exception names/numbers escape; traceback paths and messages stay private.
    const python=[],refusals=[];let pythonProbeLine=null,nativeBoundaryRefused=false,ownerMarkersInvalid=false;
    for(const line of lines){
        const exception=/^(PermissionError|FileNotFoundError|OSError): \[Errno (1|2|13|22)\] .+$/.exec(line);
        if(exception)python.push({kind:exception[1],errnoReported:Number(exception[2])});
        const frame=/^  File "<string>", line ([1-9][0-9]{0,2})(?:, in [A-Za-z_<>][A-Za-z0-9_<>]*)?$/.exec(line);
        if(frame&&Number(frame[1])<=256)pythonProbeLine=Number(frame[1]);
        if(line==='Native capability boundary refused.')nativeBoundaryRefused=true;
        const refusal=/^owner_admission\.Refusal: ([a-z-]{1,64})$/.exec(line);
        if(line.startsWith('owner_admission.Refusal:')){
            if(refusal&&admissionRefusals.has(refusal[1]))refusals.push(refusal[1]);
            else ownerMarkersInvalid=true;
        }
    }
    const consistent=python.length>0&&python.every(v=>v.kind===python[0].kind&&v.errnoReported===python[0].errnoReported);
    return Object.freeze({schemaVersion:1,scope:'test-owned-child-stderr-not-syscall-proof',observedBytes,retainedBytes:bytes.length,truncated:observedBytes>bytes.length,streamsClosed,
        operation:same?candidates[0].operation:'unclassified',errnoReported:same?candidates[0].errnoReported:null,
        pythonException:consistent?python[0]:null,pythonProbeLine,nativeBoundaryRefused,
        admissionRefusal:observedBytes===bytes.length&&!ownerMarkersInvalid&&refusals.length>0&&refusals.every(v=>v===refusals[0])?refusals[0]:null,
        preparation:safePreparationDiagnostic(diagnostic.snapshot(null,null))});
}
// A private receipt is returned ONLY to the test caller, never its public projection.
export async function persistPrivateNetworkTestStderr(bytes) {
    if(!Buffer.isBuffer(bytes)||bytes.length>LIMIT)throw Error('Network test stderr artifact refused');
    let directory;
    try{
        directory=await mkdtemp(path.join(tmpdir(),'overte-network-test-stderr-'));
        const st=await lstat(directory);
        if(await realpath(directory)!==directory||!st.isDirectory()||st.uid!==process.getuid()||(st.mode&0o777)!==0o700)throw Error('Network test stderr directory refused');
        const file=path.join(directory,'child.stderr.private');
        const handle=await open(file,constants.O_CREAT|constants.O_EXCL|constants.O_WRONLY|constants.O_NOFOLLOW,0o600);
        try{
            const current=await handle.stat();
            if(!current.isFile()||current.uid!==process.getuid()||(current.mode&0o777)!==0o600||current.nlink!==1)throw Error('Network test stderr file refused');
            await handle.writeFile(bytes);
        }finally{await handle.close();}
        return {directory,file};
    }catch(error){if(directory)await rm(directory,{recursive:true,force:true}).catch(()=>{});throw error;}
}
export function networkTestStderr() {
    let buffer=Buffer.alloc(LIMIT),retained=0,observed=0,stopped=false;
    const watches=[];
    function observe(chunk){if(stopped||!Buffer.isBuffer(chunk))return;observed=Math.min(Number.MAX_SAFE_INTEGER,observed+chunk.length);const take=Math.min(chunk.length,LIMIT-retained);if(take){chunk.copy(buffer,retained,0,take);retained+=take;}}
    function projection(){return projectNetworkTestStderr(buffer.subarray(0,retained),observed,watches.every(v=>v.closed));}
    function stop(){stopped=true;for(const v of watches){v.stream.off('data',v.data);v.stream.off('close',v.close);}watches.length=0;buffer.fill(0);buffer=Buffer.alloc(0);}
    return {
        watch(child){if(stopped||watches.length>=4||!child.stderr)throw Error('Network test stderr ownership refused');const v={stream:child.stderr,closed:child.stderr.closed===true,data:observe,close:()=>{v.closed=true;}};watches.push(v);v.stream.on('data',v.data);v.stream.once('close',v.close);return child;},
        projection,
        async finish(error){
            const safe=projection();
            if(error){
                let artifactSaved=false;
                try{await persistPrivateNetworkTestStderr(buffer.subarray(0,retained));artifactSaved=true;}catch{}
                // Failure observability cannot replace the original Error/gate.
                try{error.message+=' [network-test-stderr: '+JSON.stringify({...safe,artifactSaved})+']';}catch{}
            }
            stop();return safe;
        }
    };
}
