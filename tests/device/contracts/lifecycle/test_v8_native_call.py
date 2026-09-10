#!/usr/bin/env python3
"""Complete production native call: actual V8 callback and QObject moc dispatch."""
import os,pathlib,shlex,subprocess,tempfile,unittest
from v8_abort_fixture import write_abort_fixture
ROOT=pathlib.Path(__file__).resolve().parents[4]
class NativeCall(unittest.TestCase):
 def test_native_dispatch(self):
  prefix=pathlib.Path(os.environ['V8_TEST_ROOT']).resolve(strict=True)
  path='libraries/script-engine/src/v8/ScriptObjectV8Proxy.cpp'
  source=(ROOT/path).read_text()
  if os.environ.get('OVERTE_NATIVE_CALL_MUTATION')=='1':
   source='\n'.join(x for x in source.splitlines() if 'if (!canContinue())' not in x and 'if (_engine->isEvaluationAborted()) { return; }' not in x)
  method='void ScriptMethodV8Proxy::call('+source.split('void ScriptMethodV8Proxy::call(',1)[1].split('\nScriptSignalV8Proxy::ScriptSignalV8Proxy',1)[0]
  # Apple retains its production Qt compatibility helpers.
  for signature in ('static QVariant variantFromMetaTypeId(', 'static bool invokeWithGenericArguments('):
   if signature in source:
    method=signature+source.split(signature,1)[1].split('\n}',1)[0]+'\n}\n'+method
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
  moc=pathlib.Path(subprocess.check_output(['pkg-config','--variable=libexecdir','Qt6Core'],text=True).strip())/'moc'
  with tempfile.TemporaryDirectory(prefix='sh005-native-call-') as temp:
   temp=pathlib.Path(temp);(temp/'call.inc').write_text(method);write_abort_fixture(ROOT,temp)
   header=pathlib.Path(__file__).with_name('v8-native-call-meta.h')
   subprocess.run([str(moc),str(header),'-o',str(temp/'meta.inc')],check=True,timeout=10)
   binary=temp/'test';library=prefix/'usr/lib64'
   subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I',str(temp),'-isystem',str(prefix/'usr/include/node'),str(pathlib.Path(__file__).with_name('v8-native-call-test.cpp')),'-L',str(library),'-Wl,-rpath,'+str(library),'-lnode','-o',str(binary),*flags],check=True,timeout=40)
   for mode in ('normal','void','scriptvalue','stopped','conversion-stop','conversion-delete','native-stop'):
    with self.subTest(mode=mode):
     r=subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),mode],text=True,capture_output=True,timeout=5)
     self.assertEqual(r.returncode,0,r.stderr)
if __name__=='__main__':unittest.main()
