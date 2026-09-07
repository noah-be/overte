"""Real shared ComboBox, keyboard and popup; style/metrics are explicit seams."""
from pathlib import Path
import os,subprocess,tempfile,unittest,re,json
ROOT=Path(__file__).resolve().parents[3]
class QuerySelection(unittest.TestCase):
    def test_actual_combo(self):
        source=(ROOT/'interface/resources/qml/controlsUit/ComboBox.qml').read_text()
        if os.environ.get('OVERTE_QUERY_SWALLOW_SPACE'):
            source=source.replace('Keys.onSpacePressed: {\n            if (comboBox.editable) { event.accepted = false; } else { selectCurrentItem(); }\n        }','Keys.onSpacePressed: selectCurrentItem();')
        with tempfile.TemporaryDirectory(prefix='query-selection-') as directory:
            d=Path(directory);controls=d/'controls';styles=d/'stylesUit';controls.mkdir();styles.mkdir()
            (controls/'ComboBox.qml').write_text(source)
            (controls/'TouchUiMetrics.qml').write_text('import QtQuick 2.7\nQtObject {property bool hoverSupported:true; property real textScale:1; property real adaptiveMinimumControlHeight:40}')
            (controls/'Label.qml').write_text('import QtQuick 2.7\nText {property int colorScheme:0}')
            (controls/'ScrollBar.qml').write_text('import QtQuick.Controls 2.2\nScrollBar {}')
            colors={name:'#888888' for name in re.findall(r'hifi.colors.(\w+)',source)}
            (styles/'HifiConstants.qml').write_text('import QtQuick 2.7\nQtObject {property var colors: ('+json.dumps(colors)+');property var colorSchemes: ({light:0});property var fontSizes: ({textFieldInput:14});property var dimensions: ({textPadding:8,spinnerSize:24});property var glyphs: ({caratDn:"v"})}')
            (styles/'FiraSansSemiBold.qml').write_bytes((ROOT/'interface/resources/qml/stylesUit/FiraSansSemiBold.qml').read_bytes())
            (styles/'HiFiGlyphs.qml').write_text('import QtQuick 2.7\nText {property real size:24; font.pixelSize:size}')
            for name in ['QueryDialog','TabletQueryDialog']:
                dialog=(ROOT/('interface/resources/qml/dialogs/'+name+'.qml')).read_text()
                current=next(line.strip() for line in dialog.splitlines() if 'property var current:' in line)
                text=next(line.strip() for line in dialog.splitlines() if 'text: root.items ?' in line)
                index=next(line.strip() for line in dialog.splitlines() if 'currentIndex: typeof root.current' in line)
                if os.environ.get('OVERTE_QUERY_IGNORE_INDEX'):
                    index='currentIndex: 0'
                result=next(line.strip().split('root.result = ',1)[1] for line in dialog.splitlines() if 'root.result = items ?' in line)
                completion=dialog.split('Component.onCompleted: {',1)[1].rsplit('}',2)[0].replace('HMD.active','false')
                (d/(name+'Bindings.qml')).write_text('import QtQuick 2.7\nimport QtQuick.Controls 2.3\nimport "controls" as Shared\nItem {id:root;property var items;property bool editable:true;property bool keyboardEnabled:false;function updateIcon(){} QtObject{id:d;function resize(){}} Component.onCompleted:{'+completion+'} '+current+';property alias input:textResult;property alias selection:comboBox;TextField{id:textResult;visible:!root.items;'+text+'} Shared.ComboBox{id:comboBox;visible:!!root.items;model:root.items?root.items:[];editable:root.editable;'+index+'} function selectedValue(){return '+result+'}}')
            (d/'tst_combo.qml').write_text('''import QtQuick 2.7
import QtTest 1.2
import "controls" as Shared
TestCase {
 name: "SharedQuerySelection"; when: windowShown; width:400; height:300
 Shared.ComboBox {id:combo; width:240; model:["first","second"];currentIndex:1}
 Component{id:desktopBinding;QueryDialogBindings{}}
 Component{id:tabletBinding;TabletQueryDialogBindings{}}
 function test_actual_dialog_bindings(){
  for(var component of [desktopBinding,tabletBinding]){
   var dialog=component.createObject(this,{items:["first","second"],current:1,editable:false});
   compare(dialog.selectedValue(),"second");verify(dialog.selection.activeFocus);dialog.editable=true;
   dialog.selection.editText="typed value ä";compare(dialog.selectedValue(),"typed value ä");dialog.destroy();
   var textDialog=component.createObject(this,{current:"Unicode ä漢"});
   compare(textDialog.selectedValue(),"Unicode ä漢");verify(textDialog.input.activeFocus);textDialog.input.text="";compare(textDialog.selectedValue(),"");textDialog.destroy();
  }
 }
 function test_editing_and_selection(){
  compare(combo.currentText,"second");combo.editable=true;
  var input=combo.control.contentItem;input.forceActiveFocus();input.selectAll();
  for(var i=0;i<"typed value".length;++i){keyClick("typed value"[i]);}compare(combo.editText,"typed value");
  combo.editable=false;combo.currentIndex=0;compare(combo.currentText,"first");
  verify(input.readOnly);combo.showList();tryCompare(combo.popup,"visible",true);
  keyClick(Qt.Key_Escape);tryCompare(combo.popup,"visible",false);
  combo.model=[];combo.control.previousItem();compare(combo.currentHighLightedIndex,-1);
  combo.control.nextItem();compare(combo.currentHighLightedIndex,-1);
 }
}''')
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QUICK_BACKEND='software',QSG_RHI_BACKEND='software')
            result=subprocess.run(['unshare','--user','--map-root-user','--net','qmltestrunner-qt6','-input',str(d)],env=env,capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
if __name__=='__main__':unittest.main()
