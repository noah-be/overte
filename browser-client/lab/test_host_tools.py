#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Path/CLI/negative-preflight contracts, not a native-domain acceptance test."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import host_tools


class HostToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='overte-host-tools-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binaries = self.root / 'bin'
        self.binaries.mkdir()
        self.modules = self.root / 'modules'
        self.modules.mkdir()
        for name in host_tools.MODULES:
            (self.modules / name).write_bytes(b'\x7fELFtest-fixture')
        self.paths = {}
        for name in ['Xvfb', 'pulseaudio', 'slirp4netns', 'ldd', 'ffmpeg', 'pactl', 'rpm2cpio', 'cpio', 'ar', 'tar', 'bwrap', 'xauth', 'ip', 'unshare', 'g++', 'true']:
            path = self.binaries / name
            path.write_bytes(b'\x7fELFtest-fixture')
            path.chmod(0o755)
            self.paths[name] = str(path)

    def tools(self):
        return host_tools.select_tools(self.root, 'system', xvfb=self.paths['Xvfb'], pulseaudio=self.paths['pulseaudio'],
                                       pulse_modules=self.modules, slirp=self.paths['slirp4netns'])

    def test_explicit_system_selection_canonicalizes_only_existing_regular_tools(self):
        alias = self.root / 'xvfb-alias'
        alias.symlink_to(self.paths['Xvfb'])
        tools = host_tools.select_tools(self.root, 'system', xvfb=alias, pulseaudio=self.paths['pulseaudio'],
                                       pulse_modules=self.modules, slirp=self.paths['slirp4netns'])
        self.assertEqual(tools['xvfb'], self.paths['Xvfb'])
        self.assertEqual(tools['mode'], 'system')
        self.assertEqual(host_tools.verify_tools(tools), tools)

    def test_discovered_executables_and_module_root_are_still_checked(self):
        with mock.patch.object(host_tools.shutil, 'which', side_effect=self.paths.get), mock.patch.object(host_tools, 'discover_modules', return_value=self.modules):
            tools = host_tools.select_tools(self.root, 'system')
        self.assertEqual(tools, self.tools())

    def test_fedora_default_retains_private_rpm_layout_and_rejects_system_overrides(self):
        base = self.root / 'host-tools/usr'
        for name in ['Xvfb', 'pulseaudio', 'slirp4netns']:
            target = base / 'bin' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fixture');target.chmod(0o755)
        modules = base / 'lib64/pulseaudio/modules'
        modules.mkdir(parents=True)
        for name in host_tools.MODULES:
            (modules / name).write_bytes(b'fixture')
        with mock.patch.object(host_tools.shutil, 'which', return_value=None):
            tools = host_tools.select_tools(self.root)
        self.assertEqual(tools['xvfb'], str(base / 'bin/Xvfb'))
        self.assertEqual(tools['pulseLibraries'], [str(base/'lib64'),str(base/'lib64/pulseaudio'),str(modules)])
        with self.assertRaisesRegex(RuntimeError, 'system'):
            host_tools.select_tools(self.root, xvfb=self.paths['Xvfb'])

    def test_invalid_paths_broad_roots_nonexecutables_and_module_escape_are_rejected(self):
        for value in ['relative/tool', '/missing/overte-tool', '/tmp/a:b', '/tmp/a\n', '/tmp/a\x00']:
            with self.subTest(value=repr(value)), self.assertRaises(RuntimeError):
                host_tools.checked_path(value, executable=True)
        with self.assertRaises(RuntimeError):host_tools.checked_path('/', directory=True)
        Path(self.paths['Xvfb']).chmod(0o644)
        with self.assertRaises(RuntimeError):host_tools.checked_path(self.paths['Xvfb'], executable=True)
        module = self.modules / host_tools.MODULES[0]
        module.unlink();module.symlink_to(self.paths['ldd'])
        with self.assertRaisesRegex(RuntimeError, 'escapes'):host_tools.module_directory(self.modules)

    def test_configuration_and_library_metadata_are_bounded(self):
        with self.assertRaises(RuntimeError):host_tools.verify_tools({'version':2})
        tools=self.tools();tools['version']=True
        with self.assertRaises(RuntimeError):host_tools.verify_tools(tools)
        tools=self.tools();tools['pulseLibraries']='not-a-list'
        with self.assertRaises(RuntimeError):host_tools.verify_tools(tools)
        with self.assertRaisesRegex(RuntimeError, 'eight'):
            host_tools.select_tools(self.root,'system',pulse_libraries=[self.modules]*9)
        config=self.root/'config/host-tools.json';config.parent.mkdir();config.write_text(' '*65537)
        with self.assertRaisesRegex(RuntimeError,'too large'):host_tools.load_tools(self.root)

    def test_audio_environment_does_not_inherit_native_qt_libraries_or_mutate_input(self):
        tools=self.tools();environment={'LD_LIBRARY_PATH':'/private/native-qt','KEEP_ME':'value'}
        self.assertEqual(host_tools.pulse_environment(tools,environment),{'KEEP_ME':'value'})
        self.assertEqual(environment['LD_LIBRARY_PATH'],'/private/native-qt')
        tools['pulseLibraries']=[str(self.modules)]
        self.assertEqual(host_tools.pulse_environment(tools,environment)['LD_LIBRARY_PATH'],str(self.modules))
        self.assertEqual(host_tools.pulse_arguments(tools,['-F',self.root/'private.pa']),[tools['pulseaudio'],'--dl-search-path='+tools['pulseModules'],'-F',str(self.root/'private.pa')])
        for argument in ['--dl-search-path','--dl-search-path=/another-root']:
            with self.assertRaises(RuntimeError):host_tools.pulse_arguments(tools,[argument])

    def test_namespace_refusal_is_a_hard_failure_before_any_native_audio_process(self):
        with mock.patch.object(host_tools.shutil,'which',side_effect=self.paths.get), mock.patch.object(host_tools,'bounded_command',side_effect=RuntimeError('namespace denied')) as command:
            with self.assertRaisesRegex(RuntimeError,'namespace denied'):host_tools.preflight(self.root,self.tools())
        self.assertEqual(command.call_count,1)
        self.assertIn('--ipc',command.call_args.args[0])
        self.assertIn('--net',command.call_args.args[0])

    def test_missing_actual_native_dependency_cannot_be_converted_to_success_or_skip(self):
        targets=['server/opt/overte/domain-server','server/opt/overte/assignment-client','appimage/squashfs-root/usr/bin/interface',
                 'appimage/squashfs-root/usr/plugins/platforms/libqxcb.so','qt-tablet/usr/lib/x86_64-linux-gnu/qt5/qml/QtTest/libqmltestplugin.so',
                 'native-input/qml/BrowserNativeInput/libbrowsernativeinput.so']
        for relative in targets:
            path=self.root/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'\x7fELFfixture')
        def diagnostic(arguments,**unused):
            return 'libnode.so.127 => not found' if str(arguments[-1]).endswith('/interface') else ''
        with mock.patch.object(host_tools.shutil,'which',side_effect=self.paths.get), mock.patch.object(host_tools,'bounded_command',side_effect=diagnostic), mock.patch.object(host_tools.subprocess,'Popen') as start:
            with self.assertRaisesRegex(RuntimeError,'closure.*interface'):host_tools.preflight(self.root,self.tools())
        start.assert_not_called()

    def test_cli_rejects_tool_selection_outside_preparation_and_has_explicit_preflight(self):
        source=Path(__file__).with_name('manage.py')
        env=dict(os.environ,OVERTE_LAB_ROOT=str(self.root/'lab'))
        help_result=subprocess.run([sys.executable,source,'--help'],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(help_result.returncode,0);self.assertIn('preflight',help_result.stdout);self.assertIn('--host-tools',help_result.stdout)
        rejected=subprocess.run([sys.executable,source,'status','--host-tools','system'],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(rejected.returncode,2);self.assertIn('belongs to prepare',rejected.stderr)
        self.assertFalse((self.root/'lab').exists())
        rejected=subprocess.run([sys.executable,source,'prepare','--xvfb',self.paths['Xvfb']],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(rejected.returncode,2);self.assertIn('require --host-tools system',rejected.stderr)
        self.assertFalse((self.root/'lab').exists())

    def test_pulse_wrapper_uses_saved_system_binary_modules_and_clear_library_environment(self):
        tools=self.tools();pulse=Path(tools['pulseaudio'])
        # A fake executable verifies argv/environment dispatch only, never ABI.
        pulse.write_text('#!/bin/sh\nprintf "%s\\n" "${LD_LIBRARY_PATH:-cleared}" "$@"\n');pulse.chmod(0o755)
        config=self.root/'config/host-tools.json';config.parent.mkdir();config.write_text(json.dumps(tools))
        env=dict(os.environ,OVERTE_LAB_ROOT=str(self.root),LD_LIBRARY_PATH='/private/native-qt')
        result=subprocess.run(['bash',Path(__file__).with_name('pulseaudio-local.sh'),'--version'],env=env,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.splitlines(),['cleared','--dl-search-path='+str(self.modules),'--version'])

    def test_audio_wrapper_refuses_implicit_desktop_daemon_actions(self):
        tools=self.tools();config=self.root/'config/host-tools.json';config.parent.mkdir();config.write_text(json.dumps(tools))
        env=dict(os.environ,OVERTE_LAB_ROOT=str(self.root))
        result=subprocess.run(['bash',Path(__file__).with_name('pulseaudio-local.sh'),'--start'],env=env,capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0);self.assertIn('desktop daemon actions are refused',result.stderr)

    def test_portable_tool_identities_bind_actual_bytes_without_private_paths(self):
        tools=self.tools();first=host_tools.tool_identities(tools)
        self.assertNotIn(str(self.root),json.dumps(first));self.assertEqual(len(first['tools']),5)
        Path(tools['xvfb']).write_bytes(b'changed-fixture')
        second=host_tools.tool_identities(tools)
        self.assertNotEqual(first['tools']['xvfb']['sha256'],second['tools']['xvfb']['sha256'])


if __name__ == '__main__':
    unittest.main()
