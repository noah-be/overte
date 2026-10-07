// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {constants} from 'node:fs';
import {mkdir,open,opendir,lstat,rename,unlink} from 'node:fs/promises';
import {join} from 'node:path';
import {randomUUID} from 'node:crypto';
import {Readable} from 'node:stream';

export const MAX_VISITOR_FILE_BYTES=64*1024*1024;
export const MAX_VISITOR_WORKSPACE_BYTES=256*1024*1024;
export const MAX_VISITOR_FILES=256;
export const MAX_VISITOR_FILE_OPERATIONS=16;
export function visitorFilename(value){
    if(typeof value!=='string'||value.length<1||value.length>180||Buffer.byteLength(value)>240||value.startsWith('.')||/[\\/\p{C}]/u.test(value))throw new Error('Choose a plain file name without folders or control characters');
    return value;
}
export function visitorDownloadHeaders(name,size){
    name=visitorFilename(name);
    if(!Number.isSafeInteger(size)||size<0||size>MAX_VISITOR_FILE_BYTES)throw new Error('Invalid visitor download size');
    return {'content-type':'application/octet-stream','content-length':String(size),'content-disposition':`attachment; filename="${name.replace(/[^A-Za-z0-9._ -]/g,'_')}"; filename*=UTF-8''${encodeURIComponent(name).replace(/['()*]/g,c=>'%'+c.charCodeAt(0).toString(16).toUpperCase())}`,
        'x-content-type-options':'nosniff','content-security-policy':"sandbox; default-src 'none'",'cache-control':'no-store'};
}

/** Linux descriptor-bound workspace shared only with one sandboxed native worker. */
export async function createVisitorFiles(sessionDirectory){
    const directory=join(sessionDirectory,'files');await mkdir(directory,{mode:0o700});
    const descriptor=await open(directory,constants.O_RDONLY|constants.O_DIRECTORY|constants.O_NOFOLLOW);
    return new VisitorFiles(directory,descriptor);
}
class VisitorFiles {
    constructor(directory,descriptor){this.directory=directory;this.descriptor=descriptor;this.closed=false;this.operations=new Set();this.readers=new Set();this.inputs=new Set();this.uploading=false;this.closing=null;}
    path(name){if(this.closed)throw Error('Visitor files session has ended');return `/proc/self/fd/${this.descriptor.fd}/${visitorFilename(name)}`;}
    run(action){if(this.closed)return Promise.reject(Error('Visitor files session has ended'));if(this.operations.size+this.readers.size>=MAX_VISITOR_FILE_OPERATIONS)return Promise.reject(Error('Too many visitor file transfers are already active'));const operation=action();this.operations.add(operation);operation.finally(()=>this.operations.delete(operation)).catch(()=>{});return operation;}
    list(){return this.run(async()=>{
        const root=`/proc/self/fd/${this.descriptor.fd}`,entries=await opendir(root);
        const files=[];let count=0;
        for await(const entry of entries){
            if(++count>MAX_VISITOR_FILES*2)throw Error('The visitor workspace contains too many files');
            if(entry.name.startsWith('.'))continue;
            try{visitorFilename(entry.name);}catch{continue;}
            const info=await lstat(`${root}/${entry.name}`).catch(()=>null);
            if(!info?.isFile()||info.isSymbolicLink())continue;
            if(info.size>MAX_VISITOR_FILE_BYTES)throw Error('A native-created file exceeds the visitor workspace limit');
            files.push({name:entry.name,size:info.size});
        }
        if(files.length>MAX_VISITOR_FILES)throw Error('The visitor workspace contains too many files');
        return files.sort((a,b)=>a.name.localeCompare(b.name));
    });}
    upload(name,input){return this.run(async()=>{
        name=visitorFilename(name);if(this.uploading)throw Error('Another visitor upload is still in progress');
        this.uploading=true;this.inputs.add(input);const temporary=`.upload-${randomUUID()}`;
        const root=`/proc/self/fd/${this.descriptor.fd}`,temporaryPath=`${root}/${temporary}`;let file,size=0;
        try{
            const files=await this.list();const total=files.filter(item=>item.name!==name).reduce((sum,item)=>sum+item.size,0);
            if(!files.some(item=>item.name===name)&&files.length>=MAX_VISITOR_FILES)throw Error('The visitor workspace contains too many files');
            file=await open(temporaryPath,constants.O_WRONLY|constants.O_CREAT|constants.O_EXCL|constants.O_NOFOLLOW|constants.O_NONBLOCK,0o600);
            for await(const chunk of input){
                if(this.closed)throw Error('Visitor files session has ended');
                const bytes=Buffer.isBuffer(chunk)?chunk:Buffer.from(chunk);size+=bytes.length;
                if(size>MAX_VISITOR_FILE_BYTES||total+size>MAX_VISITOR_WORKSPACE_BYTES)throw Error('Visitor upload exceeds the workspace limit');
                let written=0;while(written<bytes.length){const part=await file.write(bytes,written,bytes.length-written);written+=part.bytesWritten;}
            }
            if(this.closed)throw Error('Visitor files session has ended');
            await file.sync();await file.close();file=null;
            // rename replaces a native-created final symlink instead of following it.
            await rename(temporaryPath,`${root}/${name}`);return {name,size};
        }finally{await file?.close().catch(()=>{});await unlink(temporaryPath).catch(()=>{});this.inputs.delete(input);this.uploading=false;}
    });}
    download(name){return this.run(async()=>{
        const file=await open(this.path(name),constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);let owned=true;
        try{
            const info=await file.stat();if(!info.isFile()||info.size>MAX_VISITOR_FILE_BYTES)throw Error('Only bounded regular visitor files can be downloaded');
            if(this.closed)throw Error('Visitor files session has ended');
            if(!info.size){await file.close();owned=false;return {name,size:0,stream:Readable.from([]),headers:visitorDownloadHeaders(name,0)};}
            // Bound the stream to stat()'s size even if native code later appends.
            const stream=file.createReadStream({start:0,end:info.size-1,autoClose:true});owned=false;this.readers.add(stream);
            stream.once('close',()=>this.readers.delete(stream));stream.on('error',()=>{});
            return {name,size:info.size,stream,headers:visitorDownloadHeaders(name,info.size)};
        }finally{if(owned)await file.close();}
    });}
    delete(name){return this.run(async()=>{await unlink(this.path(name));});}
    close(){
        if(this.closing)return this.closing;this.closed=true;
        for(const input of this.inputs)input.destroy?.(Error('Visitor files session has ended'));
        const readers=[...this.readers].map(reader=>new Promise(resolve=>{if(reader.closed){resolve();return;}reader.once('close',resolve);reader.destroy();}));
        this.closing=(async()=>{await Promise.allSettled([...this.operations,...readers]);await this.descriptor.close();})();return this.closing;
    }
}
