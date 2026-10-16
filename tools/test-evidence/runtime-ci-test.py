#!/usr/bin/env python3
"""Fake CI37 identity and strict-negative tests; no installed tool queries/builds."""
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import runtime_ci as C

NOW = datetime(2026,10,16,12,tzinfo=timezone.utc)
QUALIFIED = '2026-10-16T11:00:00Z'
EXPIRES = '2026-10-16T13:00:00Z'
HASH = 'sha256:'+'a'*64
FILE = {'mode':0o755,'size':12,'sha256':HASH}
INVENTORY = {'entries':3,'bytes':12,'digest':HASH}


class OriginalCIEnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'schema':2,'profile':C.ci_profile.PROFILE,'suites':list(C.ci_profile.SUITES)}
        self.policy = {'not_before':'2026-10-16T00:00:00Z','max_age_seconds':86400}
        required,_ = C.runtime._requirement_inventory(C.ROOT)
        self.environment = {'schema':2,'profile':C.ci_profile.PROFILE,'selection':deepcopy(self.binding),
            'os':{'architecture':'x86_64','distribution':'ubuntu','version':'24.04','kernel':'6.17.0-azure',
                'namespace':{'apparmor_restrict_unprivileged_userns':'0','max_user_namespaces':'63838'},
                'runner':{'ImageOS':'ubuntu24','ImageVersion':'20261012.334.1','RUNNER_ENVIRONMENT':'github-hosted'},
                'timezone_digest':HASH},
            'python':{'implementation':'CPython','version':'3.12.15','executable':deepcopy(FILE),'library':deepcopy(FILE),
                'flags':deepcopy(C.attested._PYTHON_FLAGS),'packages':required,
                'process_lookup':{'aliases':['python','python3'],'include_system_site_packages':False,
                    'mode':'controller-virtualenv','user_site_enabled':False}},
            'prepared':{name:deepcopy(INVENTORY) for name in (str(C.VENV),
                '/opt/hostedtoolcache/Python/3.12.15/x64','/opt/hostedtoolcache/node/22.23.3/x64')},
            'tools':{name:{'version':'Fixture 1.0','file':deepcopy(FILE)} for name in C._TOOLS},
            'native':{'family':'system-gcc','target':'x86_64-linux-gnu','version':'13.3.0',
                'sysroot':{'kind':'verified-compiler-default','root':'/','include_search':['/usr/include'],
                    'search_directories':{name:[{'path':'/usr/lib','present':True}] for name in ('install','programs','libraries')}},
                'pipeline':{name:{'path':'/usr/bin/'+name,'file':deepcopy(FILE)} for name in ('cc1','cc1plus','collect2','as','ld')},
                'content':{name:deepcopy(INVENTORY) for name in ('/usr/include','/usr/lib/gcc/x86_64-linux-gnu/13','/usr/share/cmake-3.28')},
                'crt_stdlib':{name:{'path':'/usr/lib/'+name,'file':deepcopy(FILE)} for name in C._CRT},
                'linker_scripts':{'/usr/lib/libc.so':{'/usr/lib/libc_nonshared.a':deepcopy(FILE)}}},
            'loader':{'cache':deepcopy(FILE),'libraries':{'/usr/lib/libc.so.6':deepcopy(FILE)}},
            'system_packages':{'libc6:amd64':'2.39-0ubuntu8.6','make':'4.3-4.1build2'},
            'process':{'no_new_privileges':True,'capabilities':'none','umask':'0022',
                'limits':{name:[-1,-1] for name in C._LIMITS}},
            'flags':{'git_process_overrides':'maintenance-disabled-safe-work','locale':'C.UTF-8',
                'path':'prepared-python-node-system','library_lookup':'prepared-python-base','home':'/home/candidate',
                'cwd':'/work','tmpdir':'/tmp','compiler_overrides':'absent','qt_overrides':'absent','java_overrides':'absent'},
            'trusted_execution':{'fixture':HASH}}
        self.environment['tools'].update({name:{'file':deepcopy(FILE)} for name in ('sh','system-python')})
        for name,value in {'node':'v22.23.3','cmake':'cmake version 3.28.3','cc':'cc (Ubuntu) 13.3.0','cxx':'c++ (Ubuntu) 13.3.0'}.items():
            self.environment['tools'][name]['version']=value
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(C.ci_profile,'validate_selection',return_value=self.binding))
        self.stack.enter_context(patch.object(C.ci_profile,'load_policy',return_value=self.policy))
        self.stack.enter_context(patch.object(C.ci_profile,'policy_identity',return_value=HASH))
        self.stack.enter_context(patch.object(C.runtime,'_controller_file_hashes',return_value={'fixture':HASH}))
        self.stack.enter_context(patch.object(C,'_FILES',()))
        self.stack.enter_context(patch.object(C,'_query',side_effect=AssertionError('no consumer identity queries')))
        self.stack.enter_context(patch.object(C,'capture_ci_environment',side_effect=AssertionError('no unused consumer VM')))

    def admit(self, environment=None, **times):
        return C.validate_environment(self.environment if environment is None else environment,
            times.get('qualified',QUALIFIED),times.get('expires',EXPIRES),times.get('now',NOW),{}, {}, {}, {})

    def test_original_e_admitted_unchanged_without_qt_glm_java_or_unused_consumer_queries(self):
        before=deepcopy(self.environment)
        value=self.admit()
        self.assertEqual(self.environment,before)
        self.assertEqual(value['environment_digest'],C.digest(before))
        self.assertEqual(value['profile'],'ubuntu24-ci37-v1')
        self.assertFalse({'qt','glm','java'} & self.environment.keys())
        self.assertEqual(set(self.environment['native']['crt_stdlib']),set(C._CRT))

    def test_each_complete_identity_component_is_mandatory(self):
        for key in self.environment:
            changed=deepcopy(self.environment); del changed[key]
            with self.subTest(key=key),self.assertRaises(C.CIEnvironmentError):self.admit(changed)

    def test_unknown_nested_shapes_never_become_equal_unknowns(self):
        paths=(('tools','node'),('native','sysroot'),('native','pipeline'),('native','content'),
            ('loader','libraries'),('python','packages'),('prepared',),('os','runner'),('process','limits'))
        for path in paths:
            for unknown in (None,{},'unknown',False):
                changed=deepcopy(self.environment); target=changed
                for key in path[:-1]:target=target[key]
                target[path[-1]]=unknown
                with self.subTest(path=path,unknown=unknown),self.assertRaises(C.CIEnvironmentError):self.admit(changed)

    def test_product_fields_other_profile_or_changed_selection_cannot_enter_quick_admission(self):
        for key,value in (('schema',1),('profile','ubuntu24-host-qt5-qt6-v1'),('qt',{}),('glm',{}),('java',{}),
                ('selection',{'suites':[ *self.binding['suites'],'device-control-plane-full']})):
            changed=deepcopy(self.environment); changed[key]=value
            with self.subTest(key=key),self.assertRaises(C.CIEnvironmentError):self.admit(changed)

    def test_native_search_content_pipeline_loader_and_pins_are_not_optional(self):
        for mutation in ('compiler','target','sysroot','search','header','crt','pipeline','loader','mutable','package','controller','limits'):
            changed=deepcopy(self.environment)
            if mutation=='compiler':changed['tools']['cxx']['version']='unidentified compiler'
            elif mutation=='target':changed['native']['target']='aarch64-linux-gnu'
            elif mutation=='sysroot':changed['native']['sysroot']['kind']='unknown'
            elif mutation=='search':changed['native']['sysroot']['search_directories']['libraries'][0]['path']='/work/overlay'
            elif mutation=='header':changed['native']['content'].pop('/usr/include')
            elif mutation=='crt':changed['native']['crt_stdlib'].pop('crt1.o')
            elif mutation=='pipeline':changed['native']['pipeline'].pop('cc1plus')
            elif mutation=='loader':changed['loader']['libraries']={}
            elif mutation=='mutable':changed['tools']['make']['file']['mode']=0o777
            elif mutation=='package':changed['python']['packages'].pop(next(iter(changed['python']['packages'])))
            elif mutation=='controller':changed['trusted_execution']['fixture']='sha256:'+'b'*64
            else:changed['process']['limits']['RLIMIT_CPU']=['unknown',0]
            with self.subTest(mutation=mutation),self.assertRaises(C.CIEnvironmentError):self.admit(changed)

    def test_original_qualification_and_expiry_cannot_be_renewed(self):
        for times in ({'expires':QUALIFIED},{'qualified':'2026-10-15T11:00:00Z'},
            {'expires':'2026-10-18T13:00:00Z'},{'qualified':'unknown'},{'now':NOW.replace(tzinfo=None)}):
            with self.subTest(times=times),self.assertRaises(C.CIEnvironmentError):self.admit(**times)

    def test_same37_plan_uses_original_e_and_cannot_claim_the_omitted23(self):
        tree={'fixture.txt':{'mode':'100644','type':'blob','sha':'a'*40}}
        registry={'schema':1,'control_inputs':['fixture.txt'],'suites':{name:{'command':['python','fixture.py'],
            'layer':'quick','scope':'content','environment':'host-qt5-qt6',
            'closure':{'kind':'repository','inputs':[],'required':[]}} for name in C.ci_profile.SUITES}}
        results={name:{'status':'passed','fingerprint':C.inputs.suite_fingerprint(registry,name,tree,self.environment)}
                 for name in registry['suites']}
        def plan(current=tree,proof=results):
            return C.plan_original_reuse(self.environment,QUALIFIED,EXPIRES,NOW,{}, {},tree,current,tree,registry,proof)
        value=plan()
        self.assertEqual(value['reused_suites'],list(C.ci_profile.SUITES))
        self.assertEqual(value['executed_suites'],[])
        self.assertFalse(value['reusable'])
        self.assertEqual(value['original_expires_at'],EXPIRES)
        changed=deepcopy(tree);changed['fixture.txt']['sha']='b'*40
        with self.assertRaises(C.CIEnvironmentError):plan(changed)
        with self.assertRaises(C.CIEnvironmentError):plan(proof={**results,'device-control-plane-full':{'status':'passed'}})


class CaptureBoundaryTests(unittest.TestCase):
    def test_shipping_guard_fails_before_any_identity_probe(self):
        with patch.object(C,'_query',side_effect=AssertionError('no queries before source admission')):
            with self.assertRaises(C.CIEnvironmentError):C.capture_ci_environment({}, {}, {}, {})

    def test_sensitive_overrides_are_rejected_before_tool_or_sysroot_queries(self):
        for name in ('QT_PLUGIN_PATH','OVERTE_QML_TEST_RUNNER','JAVA_HOME','NODE_OPTIONS','PYTHONPATH',
                'CXX','CPATH','LD_PRELOAD','CMAKE_PREFIX_PATH','BASH_ENV','MAKEFLAGS','GIT_EXEC_PATH',
                'SOURCE_DATE_EPOCH','FUTURE_UNREVIEWED_LOOKUP','GH_TOKEN'):
            with patch.dict(C.os.environ,{name:'/unreviewed'},clear=True),self.subTest(name=name):
                with self.assertRaises(C.CIEnvironmentError):C._flags()

    def test_fixed_identity_query_cannot_run_a_build_or_inherit_credentials(self):
        observed=Mock(stdout='GNU Make 4.3\n',stderr='')
        with patch.dict(C.os.environ,{'GH_TOKEN':'fixture-secret','CXXFLAGS':'-bad'},clear=True), \
             patch.object(C.subprocess,'run',return_value=observed) as run:
            self.assertEqual(C._query(Path('/usr/bin/make'),'--version'),'GNU Make 4.3')
        self.assertEqual(run.call_args.args[0],['/usr/bin/make','--version'])
        self.assertEqual(run.call_args.kwargs['cwd'],'/')
        self.assertNotIn('GH_TOKEN',run.call_args.kwargs['env'])
        self.assertNotIn('CXXFLAGS',run.call_args.kwargs['env'])
        self.assertEqual(run.call_args.kwargs['input'],'')

    def test_incomplete_or_oversized_query_cannot_return_partial_identity(self):
        for stdout in ('', 'a'*2_000_001):
            with patch.object(C.subprocess,'run',return_value=Mock(stdout=stdout,stderr='')):
                with self.assertRaises(C.CIEnvironmentError):C._query(Path('/usr/bin/c++'),'--version')

    def test_mutable_nonroot_files_and_unknown_native_paths_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'input';path.write_text('fixture');path.chmod(0o666)
            with self.assertRaises(C.CIEnvironmentError):C._file(path)
        for path in ('relative','/usr/../work/overlay','/work/tool'):
            with self.subTest(path=path),self.assertRaises(C.CIEnvironmentError):C._path(path)

    def test_full_profile_reader_remains_separate(self):
        self.assertNotIn('java',C._TOOLS)
        self.assertNotIn('pkg-config',C._TOOLS)
        self.assertIn('make',C._TOOLS)
        self.assertIn('compiler',C.runtime._COMMANDS)
        self.assertTrue(C.runtime._QT_MODULES)
        self.assertFalse(C.ci_profile.SOURCE_READY)

    def test_elf_relocatable_startup_objects_are_not_sent_to_ldd(self):
        with tempfile.TemporaryDirectory() as folder:
            objects=[]
            for kind in (1,3):
                path=Path(folder)/str(kind)
                header=bytearray(20);header[:6]=b'\x7fELF\x02\x01';header[16:18]=kind.to_bytes(2,'little')
                path.write_bytes(header);objects.append(path)
            with patch.object(C,'_query',return_value='/lib64/ld-linux-x86-64.so.2 (0xabc)') as query, \
                 patch.object(C,'_path',return_value=Path('/usr/lib/ld-linux-x86-64.so.2')), \
                 patch.object(C,'_file',return_value=FILE), \
                 patch.object(C.runtime,'_checked_executable',return_value=Path('/usr/bin/ldd')):
                value=C._loader(objects)
            query.assert_called_once_with(Path('/usr/bin/ldd'),str(objects[1]))
            self.assertIn('/usr/lib/ld-linux-x86-64.so.2',value['libraries'])

    def test_native_union_keeps_default_pie_and_nonshared_glibc_inputs(self):
        self.assertTrue({'Scrt1.o','crtbeginS.o','crtendS.o','libc_nonshared.a'}<=set(C._CRT))
        with tempfile.TemporaryDirectory() as folder:
            script=Path(folder)/'libc.so';script.write_text('GROUP ( /work/unreviewed.a )')
            with self.assertRaises(C.CIEnvironmentError):
                C._linker_scripts({'libc':{'path':str(script)}},Path('/usr/bin/c++'))

    def test_linker_script_actual_referents_and_large_binary_inputs_are_distinguished(self):
        with tempfile.TemporaryDirectory() as folder:
            binary=Path(folder)/'libc.so.6';binary.write_bytes(b'\x7fELF'+b'\0'*1_000_100)
            archive=Path(folder)/'libgcc.a';archive.write_bytes(b'!<arch>\n'+b'\0'*1_000_100)
            script=Path(folder)/'libc.so';script.write_text('/* GNU ld script */\nOUTPUT_FORMAT(elf64-x86-64)\nGROUP ( /usr/lib/libc.so.6 )')
            with patch.object(C,'_path',return_value=binary),patch.object(C,'_file',return_value=FILE):
                identities,readers=C._linker_scripts({name:{'path':str(path)} for name,path in
                    (('binary',binary),('archive',archive),('script',script))},Path('/usr/bin/c++'))
            self.assertEqual(readers,[binary])
            self.assertEqual(identities,{str(script):{str(binary):FILE}})


if __name__=='__main__':unittest.main()
