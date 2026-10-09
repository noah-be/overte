"""Exercise the actual observer when About.platform contains product branding."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shutil
import subprocess
import unittest


class NativeProbeObservation(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
