"""Actual ImageOverlay/Overlay/ItemTint with real two-frame GIF content."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource,shutil
from PIL import Image,ImageDraw
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[3]
class AnimatedTint(unittest.TestCase):
 def test_actual_animated_overlay(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='animated-overlay-') as d:
   d=pathlib.Path(d);frames=[]
   for left in [True,False]:
    f=Image.new('RGBA',(32,32),(0,0,0,0));ImageDraw.Draw(f).rectangle((0 if left else 16,0,15 if left else 31,31),fill='red');frames.append(f)
   frames[0].save(d/'frames.gif',save_all=True,append_images=frames[1:],duration=80,loop=0,disposal=2)
   Image.new('RGBA',(32,32),'green').save(d/'other.png')
   binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('animated-overlay-tint-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   source=ROOT/'interface/resources/qml/hifi/overlays/ImageOverlay.qml'
   if os.environ.get('OVERTE_ANIMATED_TINT_FREEZE_FRAMES'):
    for name in ['Overlay.qml','ImageOverlay.qml','ItemTint.qml']:shutil.copy2(source.parent/name,d/name)
    p=d/'ItemTint.qml';text=p.read_text();needle='function onCurrentFrameChanged() { root.refresh(false) }';assert text.count(needle)==1;p.write_text(text.replace(needle,'function onCurrentFrameChanged() {}'));source=d/'ImageOverlay.qml'
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(source),str(d/'frames.gif'),str(d/'other.png')],check=True,timeout=15,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'))
if __name__=='__main__':unittest.main()
