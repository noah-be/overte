#!/usr/bin/env python3
import os,pathlib,shlex,subprocess,tempfile,unittest,shutil
ROOT=pathlib.Path(__file__).resolve().parents[4]
class Meter(unittest.TestCase):
 def test_real_software_pixels(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='audio-meter-') as d:
   binary=pathlib.Path(d)/'test'
   subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('level-meter-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   qml=ROOT/'interface/resources/qml/hifi/audio'
   if os.environ.get('OVERTE_METER_MUTATION')=='1':
    qml=pathlib.Path(d)/'qml';qml.mkdir()
    for name in ['InputPeak.qml','LevelMeter.qml']:
     shutil.copy2(ROOT/'interface/resources/qml/hifi/audio'/name,qml/name)
    meter=qml/'LevelMeter.qml';meter.write_text(meter.read_text().replace('ctx.fillStyle = gradient','ctx.fillStyle = "white"'))
   sources=[qml]
   if os.environ.get('OVERTE_METER_MUTATION')!='1':
    sources.append(ROOT/'interface/resources/qml/hifi/simplifiedUI/simplifiedControls')
   for source in sources:
    with self.subTest(source=source.name):
     subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(source),str(qml)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=15)
if __name__=='__main__':unittest.main()
