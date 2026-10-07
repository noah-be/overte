#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Actual bounded whole-job namespace smoke; never a complete CI success."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from gates import isolated_identity


def main():
    isolated_identity()
    config=json.loads(Path(sys.argv[1]).read_text())
    independent={name:os.stat('/proc/self/ns/'+name).st_ino!=inode
                 for name,inode in config['hostNamespaces'].items()}
    if not all(independent.values()):
        raise RuntimeError('CI-job-namespace-is-not-independent-of-agent')
    for display in (94,95):
        if Path(f'/tmp/.X{display}-lock').exists() or Path(f'/tmp/.X11-unix/X{display}').exists():
            raise RuntimeError('private-job-tmp-exposes-existing-X-display')
    sockets=[]
    try:
        for port in (8090,45100,45110):
            listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
            listener.bind(('127.0.0.1',port));listener.listen(1);sockets.append(listener)
        for port in (45102,45200,45201,45202,45203,45204,45205):
            listener=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            listener.bind(('127.0.0.2',port));sockets.append(listener)
        subprocess.run(['unshare','--user','--map-current-user','--ipc','--pid','--fork',
            '--mount-proc','--net','--','true'],check=True,capture_output=True,timeout=10)
        subprocess.run(['bwrap','--unshare-user','--unshare-pid','--unshare-net','--unshare-ipc',
            '--die-with-parent','--ro-bind','/','/','--proc','/proc','--dev','/dev','--','true'],
            check=True,capture_output=True,timeout=10)
    finally:
        for listener in sockets:listener.close()
    report={'namespaceSmokePassed':True,'completeCI':'not-run','sourceSHA':config['sourceSHA'],
        'sourceCheckoutClean':config['sourceCheckoutClean'],
        'qualificationHelperSHA256':config['sourceFiles'],'independentNamespaces':independent,
        'fixedTCPPortsInsideOwnedNamespace':3,'fixedUDPPortsInsideOwnedNamespace':7,
        'privateXSocketAndLockFiles':'clean','nonrootAndZeroInheritedCapabilities':True,
        'verifiedZeroCapabilitySets':['inheritable','permitted','effective','bounding','ambient'],
        'nestedNormalUnshareAndBubblewrap':'passed','hostServiceChanges':'none',
        'ordinaryNativeGUIAndAudioGates':'not-run'}
    output=Path(config['repo'])/'build/jenkins-browser-ci/namespace-smoke.json'
    output.write_text(json.dumps(report,indent=2)+'\n')
    return 0


if __name__=='__main__':raise SystemExit(main())
