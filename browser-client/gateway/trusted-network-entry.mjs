// SPDX-License-Identifier: Apache-2.0
// Optional trusted entry adapter only; actual lifecycle stays in network-sandbox.
import {open,lstat,realpath} from 'node:fs/promises';
import {constants} from 'node:fs';
import path from 'node:path';
export const TRUSTED_NETWORK_EXECUTABLE='/usr/libexec/overte-browser-network/launcher';

export async function trustedNetworkEntry(configPath) {
    const executable=TRUSTED_NETWORK_EXECUTABLE;
    for(let current=executable;;current=path.dirname(current)) {
        const info=await lstat(current);
        if(await realpath(current)!==current || info.uid!==0 || info.mode&0o022
            || (current===executable ? !info.isFile() || !(info.mode&0o111) || !!(info.mode&0o6000) : !info.isDirectory())) {
            throw Error('The trusted network entrypoint is not an immutable root-owned installation.');
        }
        if(current==='/')break;
    }
    const config=await open(configPath,constants.O_RDONLY|constants.O_NOFOLLOW);
    try {
        const info=await config.stat();
        if(!info.isFile() || info.uid!==process.getuid() || info.mode&0o077 || info.size<1 || info.size>131072) {
            throw Error('The network entrypoint requires a bounded owned configuration descriptor.');
        }
        // The actual C loader snapshots/seals config and verifies immutable code,
        // enforcing profile, isolated namespaces, kernel routes and cap retirement.
        return {command:executable,args:[],options:{configurationFD:config.fd},close:()=>config.close()};
    } catch(error){await config.close();throw error;}
}
