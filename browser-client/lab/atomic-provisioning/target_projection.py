# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Private exact-destination matching; output contains fixed syscall/errno enums."""
import json,re
from observer import ERRNOS,MAX_CAPTURE,MAX_LINE
LINE=re.compile(r'^(?:\[pid\s+\d+\]\s+|\d+\s+)?(?P<time>\d{9,12}\.\d{1,9})\s+(?P<call>linkat|rename|renameat|renameat2|fsync|fdatasync)\((?P<args>.*)\)\s+=\s+(?P<result>-?\d{1,20})(?:\s+(?P<errno>[A-Z][A-Z0-9]+)\s+\([^\r\n]*\))?\s*$')

def arguments(value):
    result=[];start=0;quoted=False;escaped=False
    for i,c in enumerate(value):
        if quoted:
            if escaped:escaped=False
            elif c=='\\':escaped=True
            elif c=='"':quoted=False
        elif c=='"':quoted=True
        elif c==',':result.append(value[start:i].strip());start=i+1
    if quoted or escaped:return None
    result.append(value[start:].strip())
    return result if len(result)<=8 else None

def summarize(data,target,start,end,*,capture_truncated=False):
    if not isinstance(data,bytes)or len(data)>MAX_CAPTURE or not isinstance(target,str)or not target.startswith('/')or len(target)>4096 or not 0<start<=end:
        raise ValueError('target-projection-input-refused')
    out={'scope':'exact-private-settings-destination-within-single-provisioning-window','calls':{},'unmatchedDestination':0,'syncDescriptorUnattributed':0,'unparsedLines':0,'oversizedLines':0,'windowExcluded':0,'captureTruncated':bool(capture_truncated),'settingsCommitCause':'not-established'}
    for raw in data.splitlines():
        if len(raw)>MAX_LINE:out['oversizedLines']+=1;continue
        line=LINE.fullmatch(raw.decode('ascii',errors='replace'))
        if not line:out['unparsedLines']+=1;continue
        if not start<=float(line['time'])<=end:out['windowExcluded']+=1;continue
        if line['call']in('fsync','fdatasync'):out['syncDescriptorUnattributed']+=1;continue
        args=arguments(line['args']);index=1 if line['call']=='rename'else 3
        if not args or len(args)<=index:out['unparsedLines']+=1;continue
        try:destination=json.loads(args[index])
        except (ValueError,TypeError):out['unmatchedDestination']+=1;continue
        # No cwd, dirfd, proc fd, symlink or substring inference. Only the full
        # original absolute configured destination is eligible for attribution.
        if type(destination)is not str or destination!=target:out['unmatchedDestination']+=1;continue
        row=out['calls'].setdefault(line['call'],{'success':0,'failure':0,'unclassifiedResult':0,'errno':{}})
        value=int(line['result'])
        if value==0 and not line['errno']:row['success']+=1
        elif value==-1 and line['errno']:
            row['failure']+=1;errno=line['errno']if line['errno']in ERRNOS else'unrecognized-errno';row['errno'][errno]=row['errno'].get(errno,0)+1
        else:row['unclassifiedResult']+=1
    return out
