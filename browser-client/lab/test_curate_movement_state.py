# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Actual report projection; these checks do not qualify native movement."""
import importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('curate_movement',Path(__file__).with_name('curate-core-journey.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class MovementStateTests(unittest.TestCase):
    def raw(self):
        return {'completed':False,'checkpoints':[{'name':'movement-measured','performance':{
            'initialSurfaceWait':{'verified':False,'waiting':True,'expired':False,'startedAt':200}},
            'browserPresentation':{'visibility':'visible','focused':True}}]}
    def test_actual_existing_producer_fields_survive_curating_without_changing_acceptance(self):
        result=module.curate(self.raw(),'chrome');row=result['checkpoints'][0]
        self.assertEqual(row['initialSurfaceWait'],{'verified':False,'waiting':True,'expired':False,'startedAtMs':200})
        self.assertEqual(row['browserPresentation'],{'visibility':'visible','focused':True})
        self.assertFalse(result['completed']);self.assertEqual(result['status'],'incomplete')
    def test_private_values_extra_fields_and_nonfinite_clocks_are_not_published(self):
        raw=self.raw();row=raw['checkpoints'][0]
        row['performance']['initialSurfaceWait']={'verified':'PRIVATE','waiting':1,'expired':None,'startedAt':float('inf'),'device':'PRIVATE'}
        row['browserPresentation']={'visibility':'PRIVATE','focused':'PRIVATE','window':'PRIVATE'}
        result=module.curate(raw,'chrome');self.assertNotIn('PRIVATE',json.dumps(result))
        self.assertEqual(result['checkpoints'][0]['initialSurfaceWait'],{})
        self.assertEqual(result['checkpoints'][0]['browserPresentation'],{})
    def test_optional_malformed_diagnostics_remain_optional(self):
        for value in (None,False,[], 'PRIVATE'):
            raw=self.raw();row=raw['checkpoints'][0];row['performance']=value;row['browserPresentation']=value
            result=module.curate(raw,'chrome');self.assertFalse(result['completed'])
            self.assertNotIn('initialSurfaceWait',result['checkpoints'][0])
            self.assertNotIn('browserPresentation',result['checkpoints'][0])

if __name__=='__main__':unittest.main()
