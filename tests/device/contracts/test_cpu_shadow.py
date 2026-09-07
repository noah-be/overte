#!/usr/bin/env python3
"""Actual retained avatar shadow wrappers and Qt software image pixels."""
import os
import re
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]

class CpuShadow(unittest.TestCase):
    def test_spread_boundaries(self):
        script = r"""
const fs=require('fs'), vm=require('vm'), assert=require('assert');
let code=fs.readFileSync(process.argv[1],'utf8').replace('.pragma library','');
vm.runInThisContext(code);
function alpha(spread, opacity=1) {
    let image={width:3,height:1,data:new Uint8ClampedArray([9,8,7,0,9,8,7,64,9,8,7,255])};
    let writes=0;
    paintShadow({putImageData(...args){assert.equal(args.length,7);writes++;}},image,0,0,0,{r:0,g:0,b:0,a:opacity},spread);
    assert.equal(writes,1);
    return [image.data[3],image.data[7],image.data[11]];
}
assert.deepEqual(alpha(0),[0,64,255]);
assert.deepEqual(alpha(0.5),[0,128,255]);
assert.deepEqual(alpha(1),[0,255,255]);
assert.deepEqual(alpha(2),alpha(1));
for (const value of [-1,NaN,Infinity,-Infinity,undefined]) assert.deepEqual(alpha(value),alpha(0));
assert.deepEqual(alpha(1,0.5),[0,128,128]);
assert.deepEqual(alpha(1,0),[0,0,0]);
console.log('PASS actual CPU spread boundaries, transparent support and color opacity');
"""
        subprocess.run(['unshare','--user','--map-root-user','--net','node','--jitless','-e',script,
            str(ROOT/'interface/resources/qml/controls/CpuShadowPixels.js')],check=True,timeout=10)

    def test_actual_avatar_wrappers(self):
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
        with tempfile.TemporaryDirectory(prefix='cpu-shadow-callers-') as directory:
            temp=Path(directory)
            files=['controls/CpuDropShadow.qml','controls/CpuShadowPixels.js','controls/CpuShadowSourceObserver.qml','controls/qmldir',
                'hifi/avatarapp/ShadowRectangle.qml','hifi/avatarapp/ShadowGlyph.qml','hifi/avatarapp/ShadowImage.qml','hifi/avatarapp/RoundImage.qml',
                'stylesUit/qmldir','stylesUit/HiFiGlyphs.qml']
            for relative in files:
                destination=temp/'qml'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(ROOT/'interface/resources/qml'/relative,destination)
            if os.environ.get('OVERTE_SHADOW_SHORT_PUTIMAGE')=='1':
                path=temp/'qml/controls/CpuShadowPixels.js'
                path.write_text(path.read_text().replace('context.putImageData(image, 0, 0, 0, 0, width, height)', 'context.putImageData(image, 0, 0)'))
            if os.environ.get('OVERTE_SHADOW_IGNORE_CHILD_PAINT')=='1':
                path=temp/'qml/controls/CpuShadowSourceObserver.qml'
                path.write_text(path.read_text().replace('function onPainted() { observer.changed(false) }', 'function onPainted() {}'))
            if os.environ.get('OVERTE_SHADOW_INVALIDATE_LIVE')=='1':
                path=temp/'qml/controls/CpuShadowSourceObserver.qml'
                path.write_text(path.read_text().replace('function onPainted() { observer.changed(false) }', 'function onPainted() { observer.changed(true) }'))
            qml=temp/'scene.qml'
            qml.write_text('''import QtQuick 2.5
import "qml/hifi/avatarapp" as Avatar
import "qml/controls" as Cpu
Item { id: scene; width: 300; height: 220
    property bool motionRunning: false
    property color gradientColor: "blue"
    Gradient { id: fillGradient; GradientStop { position:0; color:scene.gradientColor } GradientStop { position:1; color:scene.gradientColor } }
    function activateGradient() { rectangle.gradient = fillGradient }
    Avatar.ShadowRectangle { id: rectangle; objectName: "rectangle"; x:20; y:20; width:48; height:48; color:"red"; radius:8 }
    Avatar.ShadowGlyph { objectName: "glyph"; x:110; y:20; width:48; height:48; text:"M"; color:"red"; font.family:"DejaVu Sans"; font.pixelSize:36 }
    Cpu.CpuDropShadow { objectName:"liveShadow"; x:20; y:140; width:32; height:32; source:motion; radius:4; verticalOffset:4 }
    Canvas { id: motion; objectName:"motion"; x:20; y:140; width:32; height:32; property int phase:0; property int paintedPhase:0; renderTarget:Canvas.Image
        onPaint: { var c=getContext("2d"); c.reset(); c.fillStyle=Qt.rgba((phase%200)/200,0,1,1); c.fillRect(0,0,width,height); paintedPhase=phase }
        Timer { interval:8; repeat:true; running:scene.motionRunning; onTriggered:{ motion.phase++; motion.requestPaint() } }
    }

    Avatar.ShadowImage { objectName: "image"; x:210; y:20; width:48; height:48; source: fixtureRed }
}
''')
            binary=temp/'test'
            subprocess.run(['c++','-std=c++17','-fPIC',str(Path(__file__).with_name('cpu-shadow-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
            subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),str(temp/'qml')],
                env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=20)
    def test_other_retained_effect_items(self):
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Quick','Qt6Test'],text=True))
        callers=['windows/DefaultFrameDecoration.qml','controlsUit/FilterBar.qml','hifi/tablet/TabletButton.qml','hifi/avatarapp/SquareLabel.qml','hifi/avatarPackager/AvatarProjectCard.qml','hifi/Card.qml']
        with tempfile.TemporaryDirectory(prefix='cpu-shadow-retained-') as directory:
            temp=Path(directory);(temp/'controls').mkdir()
            for filename in ['CpuDropShadow.qml','CpuShadowPixels.js','CpuShadowSourceObserver.qml','qmldir']:
                shutil.copy2(ROOT/'interface/resources/qml/controls'/filename,temp/'controls'/filename)
            if os.environ.get('OVERTE_SHADOW_IGNORE_SPREAD')=='1':
                path=temp/'controls/CpuShadowPixels.js'
                path.write_text(path.read_text().replace('var strength = isFinite(spread) ? Math.max(0, Math.min(1, spread)) : 0;', 'var strength = 0;'))
            binary=temp/'test'
            subprocess.run(['c++','-std=c++17','-fPIC',str(Path(__file__).with_name('cpu-shadow-retained-test.cpp')),'-o',str(binary),*flags],check=True,timeout=30)
            cases=[]
            for caller in callers:
                source=(ROOT/'interface/resources/qml'/caller).read_text()
                starts=[m.start() for m in re.finditer(r'    CpuControls.CpuDropShadow \{',source)]
                cases.extend((caller,start) for start in starts)
            for caller,start in cases:
                source=(ROOT/'interface/resources/qml'/caller).read_text()
                end=source.index('\n    }',start)+len('\n    }')
                item=source[start:end].replace('CpuControls.CpuDropShadow {','CpuControls.CpuDropShadow { objectName:"effectUnderTest"',1)
                target=re.search(r'\bsource: (\w+)',item).group(1)
                qml=temp/'caller.qml'
                qml.write_text('''import QtQuick 2.5
import "controls" as CpuControls
Item { width:128; height:128
    property bool isStacked:true
    property bool showPlace:true
    property real dropHorizontalOffset:0
    property real dropVerticalOffset:4
    property real dropRadius:4
    property real dropSpread:0.5
    QtObject { id: desktop; property bool gradientsSupported:true }
    QtObject { id: hifi; property var colors: ({baseGrayShadow60:"#99000000",baseGrayShadow:"#99000000",black:"black"}) }
    Item { id:window; objectName:"window"; x:24; y:24; width:64; height:64; focus:true
''' + item + '\nRectangle { id:'+target+'; anchors.fill:parent; color:"red" }\n}\n}')
                with self.subTest(caller=caller, source=target):
                    subprocess.run(['unshare','--user','--map-root-user','--net',str(binary),str(qml),'tablet' if 'TabletButton' in caller else 'visible'],env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software'),check=True,timeout=10)

if __name__=='__main__':unittest.main(verbosity=2)
