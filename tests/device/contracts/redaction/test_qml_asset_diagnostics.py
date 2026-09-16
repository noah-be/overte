#!/usr/bin/env python3
"""Run actual QML JS functions with asset/UI seams and private-value canaries."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[4]
QML = Path(os.environ.get('OVERTE_QML_DIAGNOSTIC_SOURCE', str(ROOT / 'interface/resources/qml')))

def function(source, name):
    a = source.index('function ' + name + '(')
    b = source.index('{', a) + 1
    depth = 1
    while depth:
        depth += (source[b] == '{') - (source[b] == '}')
        b += 1
    return source[a:b]

class QmlDiagnostics(unittest.TestCase):
    def test_actual_asset_functions(self):
        with tempfile.TemporaryDirectory(prefix='qml-diagnostics-') as temp:
            temp = Path(temp)
            for relative in ['hifi/AssetServer.qml', 'hifi/dialogs/TabletAssetServer.qml']:
                source = (QML / relative).read_text()
                functions = '\n'.join(function(source, name) for name in ['doDeleteFile', 'doRenameFile', 'uploadClicked'])
                if os.environ.get('OVERTE_QML_RENAME_AFTER_COLLISION') == '1':
                    functions = functions.replace('box.selected.connect(reload);\n            return;', 'box.selected.connect(reload);')
                # All diagnostics in these two production components have a closed
                # literal vocabulary. Execute the actual expressions as well as
                # whole delete/rename/upload functions below.
                diagnostics = re.findall(r'^\s*((?:console\.log|print)\(.*\);)\s*$', source, re.M)
                data = temp / 'source.json'
                data.write_text(json.dumps({'functions': functions, 'diagnostics': diagnostics}))
                with self.subTest(caller=relative):
                    subprocess.run(['unshare','--user','--map-root-user','--net','node','--jitless',
                        str(Path(__file__).with_name('qml-asset-diagnostics-test.js')),str(data)],check=True,timeout=10)

    def test_web_failure_and_card_fallback(self):
        web = function((QML / 'controls/+webengine/FlickableWebViewCore.qml').read_text(), 'onLoadingChanged')
        card = (QML / 'hifi/Card.qml').read_text()
        a = card.index('        onStatusChanged: {')
        b = card.index('\n        }',a)
        handler = card[card.index('{',a)+1:b]
        code = '''const vm=require('vm'), assert=require('assert');
const secret='CANARY_PRIVATE_opaque_path_token';
let logs=[], reads=0;
let c=vm.createContext({console:{log:(...a)=>logs.push(a.join(' '))},WebEngineView:{LoadStartedStatus:1,LoadFailedStatus:2,LoadSucceededStatus:3}});
vm.runInContext(WEB,c);
c.onLoadingChanged({status:2,url:{toString(){reads++;return secret;}}});
assert.strictEqual(reads,0);assert.strictEqual(logs.length,1);assert(!logs.join('').includes(secret));
logs=[];c=vm.createContext({console:{log:(...a)=>logs.push(a.join(' '))},Image:{Error:3},status:3,source:secret,defaultThumbnail:'fallback'});
vm.runInContext(CARD,c);assert.strictEqual(c.source,'fallback');assert.strictEqual(logs.length,1);assert(!logs.join('').includes(secret));
'''.replace('WEB',json.dumps(web)).replace('CARD',json.dumps(handler))
        subprocess.run(['unshare','--user','--map-root-user','--net','node','--jitless','-e',code],check=True,timeout=10)
if __name__ == '__main__': unittest.main(verbosity=2)
