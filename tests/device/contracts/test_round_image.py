#!/usr/bin/env python3
import os,pathlib,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
class RoundImage(unittest.TestCase):
 def test_actual_component_against_qt_image(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='round-image-') as d:
   d=pathlib.Path(d);binary=d/'test'
   reference=d/'reference.qml';reference.write_text('import QtQuick 2.5\nImage { width:64; height:64 }\n')
   asset=d/'fixture.svg';asset.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16"><rect width="24" height="16" fill="red"/><rect width="12" height="8" fill="blue"/><rect x="12" y="8" width="12" height="8" fill="green"/></svg>')
   qml=ROOT/'interface/resources/qml/hifi/avatarapp/RoundImage.qml'
   baseline=os.environ.get('OVERTE_ROUND_IMAGE_BASELINE')
   if baseline:
    for name in ['RoundImage.qml','TransparencyMask.qml']:
     (d/name).write_bytes(subprocess.check_output(['git','show',baseline+':interface/resources/qml/hifi/avatarapp/'+name],cwd=ROOT))
    qml=d/'RoundImage.qml'
   if os.environ.get('OVERTE_ROUND_IMAGE_HIDE_CAPTURE_SOURCE'):
    original=qml.read_text();assert original.count('opacity: 0')==1
    mutant=d/'RoundImage.qml';mutant.write_text(original.replace('opacity: 0', 'visible: false'));qml=mutant
   subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('round-image-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),str(reference),str(asset)],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=15)
if __name__=='__main__':unittest.main()
