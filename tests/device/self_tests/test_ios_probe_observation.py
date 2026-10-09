"""Exercise the actual observer when About.platform contains product branding."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shutil
import subprocess
import unittest


class NativeProbeObservation(unittest.TestCase):
    def test_production_domain_observation_distinguishes_loaded_http_scenes_from_live_domains(self):
        source = (Path(__file__).resolve().parents[1] / "probe/overte_e2e_probe.js").read_text()
        start = source.index("            domain: {") + len("            domain: ")
        end = source.index("            input: effectiveInputState(),",start)
        expression = source[start:end].strip().rstrip(",")
        harness = r'''
const assert=require('assert');
const location={isConnected:true,hostname:'actual-host',domainID:'actual-id',protocol:'hifi'};
const observe=()=>EXPRESSION;
assert.equal(observe().connected,true);
assert.equal(observe().serverless,false);
for (const protocol of ['file','http','https']) {
 location.protocol=protocol;
 const observed=observe();
 assert.equal(observed.connected,false);
 assert.equal(observed.serverless,true);
 assert.equal(observed.hostname,'actual-host');
 assert.equal(observed.id,'actual-id');
}
location.protocol='hifi';location.isConnected=false;
assert.equal(observe().connected,false);
'''.replace("EXPRESSION", "(" + expression + ")")
        subprocess.run(["node","-e",harness],check=True,timeout=5)

    @unittest.skipUnless(shutil.which("node"), "probe execution requires Node.js")
    def test_real_observation_emits_geometry_with_product_branding(self):
        source = (Path(__file__).resolve().parents[1] / "probe/overte_e2e_probe.js").read_text()
        start = source.index("        sampleSequence += 1;")
        end = source.index("        orientationHistory.push({", start)
        harness = r'''
const assert = require('assert');
var About = {platform:'Overte'};
var Tablet = {touchUiRuntimeMetrics:{valid:true,surfaceWidth:1024,surfaceHeight:768}};
var Window = {innerWidth:2048,innerHeight:1536};
var sampleSequence=0, now=Date.now(), lastClientCommandId='ios-executed-command';
var sharedEntityCount=0, sharedObservation=null;
var saved={};
var Test = {saveObject:(value,name)=>{saved[name]=value;}};
OBSERVE
assert.equal(saved['ios-ui-observation.json'].sampleSequence,1);
assert.deepEqual(saved['ios-ui-observation.json'].nativeUi,Tablet.touchUiRuntimeMetrics);
assert.equal(saved['ios-ui-observation.json'].sampleEpochMs,now);
assert.equal(saved['client-command-result.json'].commandId,lastClientCommandId);
delete Tablet.touchUiRuntimeMetrics;
saved={};
OBSERVE
assert.equal(saved['ios-ui-observation.json'],undefined);
'''.replace("OBSERVE", source[start:end])
        subprocess.run(["node", "-e", harness], check=True, timeout=5)

    @unittest.skipUnless(shutil.which("node"), "probe execution requires Node.js")
    def test_periodic_probe_does_not_replace_requested_native_ui_observations(self):
        source = (Path(__file__).resolve().parents[1] / "probe/overte_e2e_probe.js").read_text()
        start = source.index("        sampleSequence += 1;")
        end = source.index("        orientationHistory.push({", start)
        harness = r'''
const assert = require('assert');
var Tablet = {}, Window = {}, sampleSequence=0, now=Date.now(), lastClientCommandId=null;
var sharedEntityCount=0, sharedObservation=null;
var observation={schemaVersion:1, valid:true, sampleEpochMs:now, processId:42, elements:[]};
var saved={}, calls=0;
var Test={iosNativeUiSnapshot:()=>{calls++;return observation;}, saveObject:(value,name)=>{saved[name]=value;}};
OBSERVE
assert.equal(calls,0);
assert.equal(saved['e2e-collaboration-observation.json'].entityCount,0);
assert.strictEqual(saved['e2e-collaboration-observation.json'].observation,null);
assert.equal(saved['ios-native-ui.json'],undefined);
assert.equal(saved['ios-native-ui-request-result.json'],undefined);
delete Test.iosNativeUiSnapshot;
saved={};
OBSERVE
assert.equal(saved['ios-native-ui.json'],undefined);
'''.replace("OBSERVE", source[start:end])
        subprocess.run(["node", "-e", harness], check=True, timeout=5)

    def test_actual_client_command_captures_native_ui_once_per_exact_request(self):
        source = (Path(__file__).resolve().parents[1] / "probe/overte_e2e_probe.js").read_text()
        start = source.index("    function applyClientCommand(command) {")
        end = source.index("    function pollClientCommand()", start)
        harness = r'''
const assert = require('assert');
let lastClientCommandId='',lastTextCommandId='',calls=0,saved={};
const applyVoice=()=>false;
const objectKeysMatch=(v,k)=>Object.keys(v).sort().join('|')===k.sort().join('|');
const observation={schemaVersion:1,valid:true,sampleEpochMs:Date.now(),processId:42,elements:[]};
const Test={iosNativeUiSnapshot:()=>{calls++;return observation;},
 saveObject:(value,name)=>{saved[name]=value;}};
FUNCTION
const command={schemaVersion:1,commandId:'ios-'+'a'.repeat(32),action:'native-ui-snapshot'};
applyClientCommand(command);
const result=saved['ios-native-ui-request-result.json'];
assert.equal(calls,1);
assert.equal(result.commandId,command.commandId);
assert.strictEqual(result.observation,observation);
assert.equal(lastClientCommandId,command.commandId);
applyClientCommand(command);
assert.equal(calls,1);
for (const invalid of [{...command,commandId:'foreign',elements:[]},
 {...command,commandId:'foreign',schemaVersion:true}]) {
 applyClientCommand(invalid);
 assert.equal(calls,1);
 assert.equal(lastClientCommandId,command.commandId);
}
delete Test.iosNativeUiSnapshot;
applyClientCommand({...command,commandId:'ios-'+'b'.repeat(32)});
assert.equal(lastClientCommandId,command.commandId);
'''.replace("FUNCTION", source[start:end])
        subprocess.run(["node", "-e", harness], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
