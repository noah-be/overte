"""Reject world input without an independently visible, fresh picked target."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import copy
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_primary


class NativePrimary(unittest.TestCase):
    def test_installed_feature_is_exact_and_not_inferred(self):
        self.assertTrue(native_primary.enabled({"nativeWorldTap": {"kind":"ios-documents","version":1}}))
        for value in (None, {"kind":"ios-documents","version":True}, {"kind":"ios-documents","version":2}):
            self.assertFalse(native_primary.enabled({"nativeWorldTap":value}))

    def test_stale_foreign_and_unpicked_targets_cannot_receive_physical_input(self):
        doc = {"schemaVersion":1,"sampleEpochMs":10000,"sampleSequence":10,"commandId":"exact",
               "valid":True,"entityName":"OVERTE_E2E_INTERACTABLE","point":{"x":0.5,"y":0.4}}
        self.assertEqual(native_primary.point(doc,"exact",10000),[0.5,0.4])
        for field, value in (("valid",False),("commandId","previous"),("sampleEpochMs",6000),
                             ("schemaVersion",True),("entityName","other"),("sampleSequence",0),
                             ("point",{"x":float('nan'),"y":0.5}),("point",{"x":0.01,"y":0.5})):
            invalid = copy.deepcopy(doc);invalid[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                native_primary.point(invalid,"exact",10000)

    def test_production_projection_requires_a_unique_front_facing_unoccluded_entity(self):
        source = (Path(__file__).resolve().parents[1]/"probe/overte_e2e_probe.js").read_text()
        begin = source.index("    function primaryViewObservation(")
        end = source.index("    function controllerPose(",begin)
        harness = r'''
const assert=require('assert');
let primaryOriginalCameraMode='third person', primaryViewCommandId='exact';
let interactionTargetName='OVERTE_E2E_INTERACTABLE', ids=['target'];
let point={x:0,y:0,z:-2};
let hit={intersects:true,entityID:'target'};
let Camera={mode:'first person',frustum:{orientation:{},position:{},projection:{}},
 computePickRay:(x,y)=>({x,y})};
let MyAvatar={position:{}}, Window={innerWidth:1000,innerHeight:800};
let Mat4={inverse:x=>x,createFromRotAndTrans:()=>({}),transformPoint:(m,p)=>p};
let Entities={findEntities:()=>ids,getEntityProperties:()=>({name:interactionTargetName,position:point}),
 findRayIntersection:()=>hit};
FUNCTION
assert.deepEqual(primaryViewObservation(10000,10).point,{x:0.5,y:0.5});
hit={intersects:true,entityID:'occluder'};
assert.equal(primaryViewObservation(10000,11).valid,false);
hit={intersects:false,entityID:'target'};
assert.equal(primaryViewObservation(10000,12).valid,false);
hit={intersects:true,entityID:'target'};
point={x:0,y:0,z:2};
assert.equal(primaryViewObservation(10000,13).valid,false);
point={x:0,y:0,z:-2};ids=['target','duplicate'];
assert.equal(primaryViewObservation(10000,14).valid,false);
ids=['target'];Camera.mode='third person';
assert.equal(primaryViewObservation(10000,15).valid,false);
'''.replace("FUNCTION",source[begin:end])
        subprocess.run(["node","-e",harness],check=True,timeout=5)


if __name__ == '__main__':
    unittest.main()
