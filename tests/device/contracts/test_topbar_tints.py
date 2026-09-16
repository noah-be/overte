"""Actual TopBar image/tint pairs and status rectangle on real Qt software backend."""
import os,pathlib,re,shlex,subprocess,tempfile,unittest,resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[3]
def body(s,a):
 i=s.index('{',a)+1;depth=1
 while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
class Tints(unittest.TestCase):
 def test_actual_topbar_tints(self):
  p=ROOT/'interface/resources/qml/hifi/simplifiedUI/topBar/SimplifiedTopBar.qml';s=p.read_text();imp=next(l for l in s.splitlines() if l.endswith(' as SharedAudio'));flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='topbar-tints-') as d:
   d=pathlib.Path(d);binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('topbar-tints-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   for ident in ['outputDeviceButton','statusIcon','displayModeImage','helpButtonImage','settingsButtonImage','statusButton']:
    a=s.rfind('Rectangle {' if ident=='statusButton' else 'Image {',0,s.index('id: '+ident+'\n'));b=body(s,a);b=b.replace('{','{ objectName: "actualSource";',1)
    if ident!='statusButton':
     a=s.rfind('SharedAudio.TintedImage {',0,s.index('source: '+ident+'.source'));t=body(s,a)
     if os.environ.get('OVERTE_TOPBAR_TINT_NEGATIVE'):t=re.sub(r'color: [^\n]+','color: "transparent"',t)
     b+='\n'+t
    else:b+='\nComponent.onCompleted: statusButton.currentStatus = "available"'
    pre='''import QtQuick 2.5
Item { width:64; height:64; id:root; property bool hovered:false
QtObject { id:simplifiedUI; property var numericConstants: ({mutedValue:0}); property var colors: ({text:{white:"white"},controls:{outputVolumeButton:{text:{muted:"red",noisy:"blue"}}}}) }
'''
    for mid in ['outputDeviceButtonMouseArea','statusButtonMouseArea','displayModeMouseArea','helpButtonMouseArea','settingsButtonMouseArea']:pre+='QtObject { id:'+mid+'; property bool containsMouse:root.hovered }\n'
    if ident=='statusIcon':pre+='QtObject { id:statusButton; property string currentStatus:"available" }\n'
    qml=d/'case.qml';qml.write_text(imp+'\n'+pre+b+'\n}')
    with self.subTest(ident=ident):subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),str(p),ident],check=True,timeout=10,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'))
if __name__=='__main__':unittest.main()
