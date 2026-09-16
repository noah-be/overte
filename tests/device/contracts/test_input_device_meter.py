"""Complete actual InputDeviceButton with real constants, SVGs and shared painters."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource,shutil,re
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[3]
class Meter(unittest.TestCase):
 def test_complete_input_device_button(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='input-device-meter-') as d:
   binary=pathlib.Path(d)/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('input-device-meter-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   source=ROOT/'interface/resources/qml/hifi/simplifiedUI/inputDeviceButton/InputDeviceButton.qml'
   if os.environ.get('OVERTE_INPUT_METER_SOLID_NEGATIVE') or os.environ.get('OVERTE_INPUT_METER_CANCEL_NEGATIVE'):
    hifi=pathlib.Path(d)/'hifi';(hifi/'audio').mkdir(parents=True);(hifi/'simplifiedUI').mkdir()
    shutil.copytree(source.parent,hifi/'simplifiedUI/inputDeviceButton');shutil.copytree(source.parent.parent/'simplifiedConstants',hifi/'simplifiedUI/simplifiedConstants')
    for name in ['TintedImage.qml','LevelImage.qml']:shutil.copy2(ROOT/'interface/resources/qml/hifi/audio'/name,hifi/'audio'/name)
    p=hifi/'audio/TintedImage.qml'
    if os.environ.get('OVERTE_INPUT_METER_SOLID_NEGATIVE'):p.write_text(p.read_text().replace('        paintTint(ctx)','        ctx.fillStyle = color; ctx.fillRect(0, 0, width, height)'))
    source=hifi/'simplifiedUI/inputDeviceButton/InputDeviceButton.qml'
    if os.environ.get('OVERTE_INPUT_METER_CANCEL_NEGATIVE'):source.write_text(re.sub(r'^        onCanceled:[^\n]*\n','',source.read_text(),flags=re.M|re.S))
   subprocess.run(['unshare' ,'--user','--map-root-user','--net',str(binary),str(source)],check=True,timeout=15,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'))
if __name__=='__main__':unittest.main()
