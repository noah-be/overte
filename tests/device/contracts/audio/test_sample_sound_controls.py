"""Execute all three production QML button handlers with failed/ready injectors."""
from pathlib import Path
import subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(Path(__file__).parents[1]/'lifecycle'))
from test_login_dialog_domain_receiver import block
paths=('hifi/audio/PlaySampleSound.qml','hifi/simplifiedUI/settingsApp/audio/Audio.qml','hifi/simplifiedUI/settingsApp/vr/VR.qml')
fixture=r'''
const assert = require('node:assert/strict');
let sound=null, sample=null, isPlaying=false, calls=0, fail=false, ready=false, ended=false, callback=null;
const injector={playing:true,finished:{connect(fn){callback=fn;},disconnect(fn){assert.equal(fn,callback);callback=null;}},stop(){callback();}};
const AudioScriptingInterface={playSystemSound(){++calls;injector.playing=!ended;return (!ready||fail)?null:injector;}};
/* METHODS */
playSound();assert.equal(calls,0);assert.equal(isPlaying,false);
sound={};playSound();assert.equal(calls,1);assert.equal(isPlaying,false);
ready=true;fail=true;playSound();assert.equal(calls,2);assert.equal(isPlaying,false);assert.equal(sample,null);
reset();stopSound(); // idempotent empty state
fail=false;playSound();assert.equal(calls,3);assert.equal(isPlaying,true);
playSound();assert.equal(calls,3); // one active sample
stopSound();assert.equal(isPlaying,false);assert.equal(sample,null);assert.equal(callback,null);
playSound();assert.equal(calls,4);callback();assert.equal(isPlaying,false);assert.equal(sample,null);
ended=true;playSound();assert.equal(calls,5);assert.equal(isPlaying,false);assert.equal(sample,null);
'''
with tempfile.TemporaryDirectory(prefix='overte-sample-controls-') as scratch:
 p=Path(scratch)/'test.js'
 for relative in paths:
  source=(ROOT/'interface/resources/qml'/relative).read_text()
  methods='\n'.join(block(source,'function '+name+'(') for name in ('playSound','stopSound','reset'))
  p.write_text(fixture.replace('/* METHODS */',methods))
  subprocess.run(['node',str(p)],check=True,timeout=5)
print('PASS all three actual QML sample controls: pending sound, failed injector, play/stop/completion/retry')
