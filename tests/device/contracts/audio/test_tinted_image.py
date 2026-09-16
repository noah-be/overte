#!/usr/bin/env python3
import os,pathlib,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[4]
class Tint(unittest.TestCase):
 def test_real_svg_software_pixels(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='audio-tint-') as d:
   d=pathlib.Path(d);binary=d/'test';qml=ROOT/'interface/resources/qml/hifi/audio/TintedImage.qml'
   if os.environ.get('OVERTE_TINT_MUTATION')=='1':
    text=qml.read_text().replace('ctx.globalCompositeOperation = "source-in"','ctx.globalCompositeOperation = "source-over"');qml=d/'TintedImage.qml';qml.write_text(text)
   subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('tinted-image-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),str(ROOT/'interface/resources/icons/tablet-icons/mic-mute-i.svg')],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=15)
if __name__=='__main__':unittest.main()
