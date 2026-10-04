# SPDX-License-Identifier: Apache-2.0
import ast
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import unittest
from network_route_diagnostics import owner_confinement_diagnostic, route_failure_diagnostic

class OwnerContext(unittest.TestCase):
    def observe(self,status=None,label=b'unshare//unpriv (enforce)',same=False):
        status = status if status is not None else b'CapInh:\t0000000000000000\nCapPrm:\t0000000000001000\nCapEff:\t0000000000001000\nCapBnd:\t000001ffffffffff\nCapAmb:\t0000000000000000\n'
        def read(name): return status if name=='/proc/self/status' else label
        def link(name): return name.split('/')[-1]+(':[13]' if same or '/self/' in name else ':[17]')
        return owner_confinement_diagnostic(read,link)
    def test_actual_fixed_proc_observation_is_bounded_and_contains_no_raw_ids(self):
        out=owner_confinement_diagnostic();self.assertEqual(set(out),{'profile','capabilitySets','netAdmin','namespaceRelations'})
        self.assertNotIn('/proc/',json.dumps(out));self.assertNotIn(':[',json.dumps(out))
    def test_primary_shipped_profile_and_cap_fields_are_independent_observations(self):
        out=self.observe();self.assertEqual(out['profile'],'unshare-unpriv');self.assertEqual(out['capabilitySets']['inheritable'],'zero')
        self.assertEqual(out['netAdmin']['effective'],'present');self.assertEqual(out['namespaceRelations']['user'],'different-from-visible-pid1')
        # Kernel bitmap presence does not certify LSM permission to use it.
        out=self.observe(label=b'private-operator-custom-profile (enforce)',same=True)
        self.assertEqual(out['profile'],'unrecognized');self.assertNotIn('private',json.dumps(out));self.assertEqual(out['namespaceRelations']['net'],'same-as-visible-pid1')
    def test_missing_duplicate_oversized_or_invalid_proc_inputs_stay_explicit(self):
        out=self.observe(status=b'CapEff: 1000\nCapEff: 1000\n')
        self.assertEqual(out['capabilitySets']['effective'],'invalid');self.assertEqual(out['netAdmin']['effective'],'invalid')
        out=self.observe(status=b'x'*4097,label=b'x'*4097)
        self.assertEqual(out['capabilitySets']['effective'],'unavailable');self.assertEqual(out['profile'],'unavailable')
        def unavailable(_):raise OSError('private-secret')
        out=owner_confinement_diagnostic(unavailable,unavailable)
        self.assertEqual(out['namespaceRelations']['net'],'unavailable');self.assertNotIn('private',json.dumps(out))
        out=owner_confinement_diagnostic(lambda _:b'',lambda _:'private-secret')
        self.assertEqual(out['namespaceRelations']['net'],'invalid');self.assertNotIn('private',json.dumps(out))
    def test_actual_route_function_samples_once_before_unchanged_commands_and_keeps_failure(self):
        source=Path(__file__).with_name('network-owner.py').read_text();tree=ast.parse(source)
        nodes=[node for node in tree.body if isinstance(node,(ast.FunctionDef,ast.Assign)) and
               (getattr(node,'name',None)=='install_denied_routes' or isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DENIED_ROUTES' for t in node.targets))]
        events=[];context=self.observe();failure=subprocess.CalledProcessError(2,['ip'],stderr=b'RTNETLINK answers: Operation not permitted\n')
        class Process:
            CalledProcessError=subprocess.CalledProcessError
            @staticmethod
            def run(args,**kwargs):
                events.append(('command',args,kwargs));raise failure
        def snapshot():events.append(('snapshot',));return context
        env={'subprocess':Process,'owner_confinement_diagnostic':snapshot,'route_failure_diagnostic':route_failure_diagnostic,'json':json,'sys':__import__('sys')}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(Path(__file__).with_name('network-owner.py')),'exec'),env)
        log=io.StringIO()
        with contextlib.redirect_stderr(log),self.assertRaises(subprocess.CalledProcessError) as caught:env['install_denied_routes']()
        self.assertIs(caught.exception,failure);self.assertEqual(events,[('snapshot',),('command',['ip','route','add','prohibit','10.0.0.0/8'],{'check':True,'capture_output':True})])
        emitted=json.loads(log.getvalue().strip().split('=',1)[1]);self.assertEqual(emitted['ownerContext'],context)
        self.assertEqual(emitted['category'],'permission-denied')
        # Success also observes once; all twelve original commands are unchanged.
        events.clear()
        Process.run=lambda args,**kwargs:events.append(('command',args,kwargs))
        env['install_denied_routes']()
        self.assertEqual(len(events),13);self.assertEqual(events[0],('snapshot',))
        self.assertEqual([event[1] for event in events[1:]], [['ip','route','add','prohibit',route] for route in env['DENIED_ROUTES']])
        self.assertTrue(all(event[2]=={'check':True,'capture_output':True} for event in events[1:]))

if __name__=='__main__':unittest.main()
