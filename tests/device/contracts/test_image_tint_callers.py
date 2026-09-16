"""Full actual BubbleIcon and actual Card badge subtree; Qt software rendering."""
import pathlib,os,shlex,subprocess,tempfile,unittest,resource
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
ROOT=pathlib.Path(__file__).resolve().parents[3]
class TintCallers(unittest.TestCase):
 def test_actual_callers(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='image-tint-callers-') as d:
   d=pathlib.Path(d);cpp=pathlib.Path(__file__).with_name('image-tint-callers-test.cpp');subprocess.run(['/usr/lib64/qt6/libexec/moc',str(cpp),'-o',str(d/'image-tint-callers-test.moc')],check=True,timeout=10)
   binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC','-I',str(d),str(cpp),'-o',str(binary),*flags],check=True,timeout=30)
   qmlroot=ROOT/'interface/resources/qml';bubble=qmlroot/'BubbleIcon.qml'
   overlays=qmlroot/'hifi/overlays'
   if os.environ.get('OVERTE_TINT_SKIP_FOLLOWUP'):
    overlays=d/'overlays';overlays.mkdir();text=(qmlroot/'hifi/overlays/ItemTint.qml').read_text();assert text.count('followupPaint = true')==1;(overlays/'ItemTint.qml').write_text(text.replace('followupPaint = true','followupPaint = false'))
    text=bubble.read_text().replace('"hifi/overlays"','"'+overlays.as_uri()+'"').replace('"./hifi/audio"','"'+(qmlroot/'hifi/audio').as_uri()+'"').replace('"../icons/tablet-icons/bubble-i.svg"','"'+(ROOT/'interface/resources/icons/tablet-icons/bubble-i.svg').as_uri()+'"');bubble=d/'BubbleIcon.qml';bubble.write_text(text)
   card=(qmlroot/'hifi/Card.qml').read_text();start=card.index('    Image {\n        id: standaloneOptomizedBadge');end=card.index('    StateImage {',start);body=card[start:end]
   # Preserve the production source URL base while isolating the actual badge.
   body=body.replace('source: "../../icons/standalone-optimized.svg"','source: "'+(ROOT/'interface/resources/icons/standalone-optimized.svg').as_uri()+'"')
   cardqml=d/'card.qml';cardqml.write_text('import QtQuick 2.5\nimport "'+overlays.as_uri()+'" as SharedOverlays\n'+'''Item { id: root; width: 64; height: 40
property bool standaloneOptimized: true
property bool isConcurrency: true
QtObject { id: hifi; property var colors: ({blueHighlight:"#00ff00"}) }
Item { id: actionIcon; x: 55; y: 5 }
'''+body+'\n}')
   for mode,source in [('bubble',bubble),('card',cardqml)]:
    with self.subTest(mode=mode):subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(source),mode],check=True,timeout=5,env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'))
if __name__=='__main__':unittest.main()
