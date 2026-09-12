"""Actual Shared AudioClient mute method, Qt owner queue and adapter bridge."""
from pathlib import Path
import os,sys,subprocess,tempfile,shlex,unittest
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).parents[1]/'lifecycle'))
from test_login_dialog_domain_receiver import block
class MuteCaller(unittest.TestCase):
 def test_actual_mute(self):
  source=(ROOT/'libraries/audio-client/src/AudioClient.cpp').read_text()
  method=block(source,'void AudioClient::setMuted(')
  if os.environ.get('OVERTE_MUTE_SKIP_BRIDGE'):method=method.replace('overteIOSSetAudioMuted(muted);','')
  if os.environ.get('OVERTE_MUTE_SKIP_QUEUE'):method=method.replace('QThread::currentThread() != thread()','false')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
  actual=(ROOT/'ios/audio/IOSAudioAdapter.cpp').exists()
  with tempfile.TemporaryDirectory(prefix='actual-audio-mute-') as directory:
   d=Path(directory);(d/'mute.inc').write_text(method)
   if actual:
    begin=source.index('    overteIOSSetAudioMuted(_isMuted);')
    startup=source[begin:source.index('#endif',begin)]
    if os.environ.get('OVERTE_MUTE_SKIP_INITIAL'):startup=startup.replace('overteIOSSetAudioMuted(_isMuted);','')
    (d/'startup.inc').write_text('void initialAudio(bool _isMuted) {\n'+startup+'\n}')
   else:(d/'startup.inc').write_text('void initialAudio(bool muted) { overteIOSSetAudioMuted(muted); overteIOSActivateAudioSession(); }')
   extra=['-DACTUAL_IOS_ADAPTER=1',str(ROOT/'ios/audio/IOSAudioAdapter.cpp')] if actual else []
   subprocess.run(['c++','-std=c++17','-fPIC','-pthread','-I'+str(ROOT),'-I'+str(d),*extra,str(Path(__file__).with_name('mute-caller-test.cpp')),'-x','c++',str(ROOT/'libraries/audio-client/src/IOSAudioPermission.mm'),'-o',str(d/'test'),*flags],check=True,timeout=30)
   runner=os.environ.get('OVERTE_HOST_TEST_NETWORK_RUNNER')
   isolation=[runner] if runner else ['unshare','--user','--map-root-user','--net']
   subprocess.run([*isolation,str(d/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
