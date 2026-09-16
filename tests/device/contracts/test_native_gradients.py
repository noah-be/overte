#!/usr/bin/env python3
"""Actual three production gradient items, real Qt software pixels; layout context seam."""
import os,pathlib,shlex,subprocess,tempfile,unittest
ROOT=pathlib.Path(__file__).resolve().parents[3]
class Gradients(unittest.TestCase):
 def test_actual_gradient_items(self):
  flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
  with tempfile.TemporaryDirectory(prefix='native-gradients-') as d:
   d=pathlib.Path(d);binary=d/'test';subprocess.run(['c++','-std=c++17','-fPIC',str(pathlib.Path(__file__).with_name('native-gradients-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
   for name in ['controlsUit/ContentSection.qml','controlsUit/TabletContentSection.qml','windows/ScrollingWindow.qml']:
    s=(ROOT/'interface/resources/qml'/name).read_text();g=s.index('gradient: Gradient {');a=s.rfind('Rectangle {',0,g);i=s.index('{',a)+1;depth=1
    while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
    body=s[a:i].replace('Rectangle {','Rectangle { objectName: "gradientItem"',1)
    if os.environ.get('OVERTE_GRADIENT_MUTATION')=='1':body=body.replace('position: 1.0','position: 0.0')
    qml=d/'test.qml';qml.write_text('''import QtQuick 2.5
Item { id: window; width: 640; height: 32
property bool hideBackground: false
property bool gradientsSupported: true
property bool isCollapsible: true
property int modality: Qt.NonModal
QtObject { id: desktop; property bool gradientsSupported: true }
QtObject { id: hifi; property var colors: ({darkGray:"black",baseGray:"white",darkGray0:"transparent"}); property var dimensions: ({contentMargin:{x:0}}) }
Item { id: frame; width: 640 }
Item { id: heading; height: 4 }
Item { id: contentBackground; width: 640; height: 4 }
'''+body+'\n}')
    with self.subTest(name=name):subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),'hidden' if 'TabletContent' in name else 'visible'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=10)
if __name__=='__main__':unittest.main()
