"""Actual complete NameCard VU subtree and Shared LevelMeter, Qt software pixels."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[4]
class NameCardMeter(unittest.TestCase):
 def test_actual_meter(self):
  s=(ROOT/'interface/resources/qml/hifi/NameCard.qml').read_text();start=s.index('    // VU Meter');end=s.index('    // Per-Avatar Gain Slider',start);body=s[start:end].replace('id: nameCardVUMeter','id: nameCardVUMeter; objectName: "meter"')
  if os.environ.get('OVERTE_NAME_CARD_HIGH_STOP'):
   assert body.count('highPosition: 0.91')==1;body=body.replace('highPosition: 0.91','highPosition: 1.0')
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='name-card-meter-') as d:
   d=pathlib.Path(d);qml=d/'test.qml';qml.write_text('import QtQuick 2.5\nimport "'+(ROOT/'interface/resources/qml/hifi/audio').as_uri()+'" as AudioMeters\n'+'''Item { id: thisNameCard; width: 640; height: 32
property bool isMyCard: false
property bool selected: true
property bool isPresent: true
property real audioLevel: 0.5
property real gain: 20
QtObject {id: pal; property string activeTab: "nearbyTab"}
QtObject {id: hifi; property var colors: ({darkGray:"#575757"})}
Item {id: avatarImage}
Item {id: userNameText}
Item {id: gainSlider; width: 640; visible: false; property real value: thisNameCard.gain; property real minimumValue: -60; property real maximumValue: 20}
'''+body+'\n}')
   binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('name-card-meter-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml)],check=True,timeout=5,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'))
if __name__=='__main__':unittest.main()
