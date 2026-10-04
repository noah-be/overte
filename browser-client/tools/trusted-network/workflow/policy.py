#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Write private explicit stage policy; no profile/runtime activation."""
import argparse
import json
import os
from pathlib import Path
import sys


def policy(native_root=None,qt_root=None,input_root=None):
 if os.getuid()==0 or os.getgid()==0:raise ValueError('policy-must-identify-actual-nonroot-worker-owner')
 python=str(Path('/usr/bin/python3').resolve(strict=True))
 record={'version':1,'hostUID':os.getuid(),'hostGID':os.getgid(),'sessionParent':'/tmp',
  'nativeExecutables':[python],'nativeReadRoots':[str(Path(python).parent)]}
 if any(value is not None for value in (native_root,qt_root,input_root)):
  if any(value is None for value in (native_root,qt_root,input_root)):raise ValueError('all-three-exact-native-roots-required')
  roots=[Path(value).resolve(strict=True) for value in (native_root,qt_root,input_root)]
  if any(not root.is_dir() for root in roots):raise ValueError('exact-native-package-directories-required')
  executable=roots[0]/'AppRun'
  if executable.resolve(strict=True)!=executable or not executable.is_file():raise ValueError('canonical-native-entry-required')
  record['nativeExecutables'].append(str(executable));record['nativeReadRoots']+=[str(root) for root in roots]
 return record

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--native-root');parser.add_argument('--qt-root');parser.add_argument('--input-root')
 args=parser.parse_args()
 descriptor=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  value=policy(args.native_root,args.qt_root,args.input_root)
  with os.fdopen(descriptor,'w') as stream:json.dump(value,stream,sort_keys=True);stream.write('\n')
 except BaseException:
  try:os.close(descriptor)
  except OSError:pass
  raise
