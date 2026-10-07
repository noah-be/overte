# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Bind reviewed source/header/artifacts/module bytes; no GUI, compile, or launch."""
import hashlib,json,os,stat
from pathlib import Path

def digest_regular(path, limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=limit:raise ValueError('native-key-attestation-input-refused')
        data=bytearray()
        while len(data)<=limit:
            chunk=os.read(fd,min(65536,limit+1-len(data)))
            if not chunk:break
            data.extend(chunk)
        after=os.fstat(fd)
        if len(data)!=before.st_size or len(data)>limit or (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):raise ValueError('native-key-attestation-input-changed')
        return hashlib.sha256(data).hexdigest(),bytes(data)
    finally:os.close(fd)

def attest_input(build, source):
    build=Path(build);source=Path(source)
    cpp,_=digest_regular(source,128*1024)
    header,_=digest_regular(source.with_name('application-key-route.h'),32*1024)
    metadata,raw=digest_regular(build/'artifacts.json',128*1024)
    artifacts=json.loads(raw)
    if type(artifacts) is not dict:raise ValueError('native-key-attestation-metadata-refused')
    required={'sourceSha256':cpp,'applicationKeyRouteSha256':header,'qtSDKVersion':'5.15.3','qtRuntimeVersion':'5.15.3'}
    if any(type(artifacts.get(key)) is not str or artifacts[key]!=value for key,value in required.items()):raise ValueError('native-key-attestation-source-refused')
    plugin,_=digest_regular(build/'qml/BrowserNativeInput/libbrowsernativeinput.so',32*1024*1024)
    if type(artifacts.get('pluginSha256')) is not str or artifacts['pluginSha256']!=plugin:raise ValueError('native-key-attestation-module-refused')
    return {'sourceSHA256':cpp,'applicationKeyRouteSHA256':header,'pluginLibrarySHA256':plugin,'pluginArtifactsSHA256':metadata}
