#!/usr/bin/env python3
"""Production SafeLanding lifecycle with real Qt signals and controlled races.

Entity/render/physics fixtures isolate the synchronization behavior. The real
header and implementation are compiled, except for physics readiness and a
mutex-entry scheduling hook. This is not a full renderer or device test.
"""
from pathlib import Path
import re
import os
import signal
import resource
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(os.environ.get('SAFE_LANDING_SOURCE_ROOT', Path(__file__).resolve().parents[2])).resolve()
HERE = Path(__file__).resolve().parent
QT_CORE = os.environ.get('SAFE_LANDING_QT_CORE', 'Qt6Core')
if QT_CORE not in ('Qt5Core', 'Qt6Core'):
    raise ValueError('SAFE_LANDING_QT_CORE must be Qt5Core or Qt6Core')


def replace_method(source, signature, replacement):
    start = source.index(signature)
    end = source.index('{', start) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[:start] + replacement + source[end:]


class SafeLandingLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='safe-landing-')
        cls.addClassCleanup(cls.tmp.cleanup)
        path = Path(cls.tmp.name)
        header = (ROOT / 'interface/src/octree/SafeLanding.h').read_text()
        source = (ROOT / 'interface/src/octree/SafeLanding.cpp').read_text()
        header = re.sub(r'^#include .*$', '', header, flags=re.M)
        source = re.sub(r'^#include .*$', '', source, flags=re.M)
        # slots is a C++ access annotation; hiding it from moc allows the
        # unchanged baseline (QObject without Q_OBJECT) in the combined driver.
        header = header.replace('private slots:', 'private:')
        header = header.replace('std::mutex', 'TestMutex')
        source = replace_method(source, 'bool SafeLanding::isEntityPhysicsReady(',
                                'bool SafeLanding::isEntityPhysicsReady(const EntityItemPointer& e) { return e->physicsReady; }')
        driver = ((HERE / 'safe-landing-fixture.h').read_text() + '\n' + header + '\n' + source
                  + '\n' + (HERE / 'safe-landing-driver.cpp').read_text() + '\n#include "test.moc"\n')
        cls.driver = driver
        (path / 'test.cpp').write_text(driver)
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', QT_CORE], text=True, timeout=10))
        cls.flags = flags
        moc_dir = 'host_bins' if QT_CORE == 'Qt5Core' else 'libexecdir'
        libexec = subprocess.check_output(['pkg-config', '--variable=' + moc_dir, QT_CORE], text=True, timeout=10).strip()
        subprocess.run([str(Path(libexec) / 'moc'), str(path / 'test.cpp'), '-o', str(path / 'test.moc')], check=True, timeout=30)
        cls.executables = {}
        for mode in ('pico', 'shared'):
            exe = path / mode
            defines = ['-DANDROID_APP_PICO_INTERFACE'] if mode == 'pico' else []
            subprocess.run(['c++', '-std=c++17', '-O1', '-g', '-fPIC', '-pthread', *defines,
                            str(path / 'test.cpp'), '-o', str(exe), *flags], check=True, timeout=60)
            cls.executables[mode] = exe

    def check_case(self, case):
        for mode, exe in self.executables.items():
            with self.subTest(platform=mode):
                subprocess.run([str(exe), case], check=True, timeout=15)

    def test_inflight_callback_after_stop(self): self.check_case('callback-stop')
    def test_inflight_callback_after_reset(self): self.check_case('callback-reset')
    def test_old_callback_after_new_session(self): self.check_case('callback-restart')
    def test_queued_delete_cannot_delete_new_session_entity(self): self.check_case('queued-delete')
    def test_repeated_start_reset_retires_connections_and_priority(self): self.check_case('repeated-start-reset')
    def test_physics_readiness_and_missing_packets(self): self.check_case('readiness-and-gaps')
    def test_empty_scene_requires_completion(self): self.check_case('empty-scene')
    def test_pico_preserves_playable_handoff(self): self.check_case('visual-readiness')

    def test_concurrent_start_is_idempotent(self): self.check_case('concurrent-start')
    def test_update_after_stop_and_reset(self): self.check_case('update-retired')
    def test_sequence_restart_keeps_entities_and_connections(self): self.check_case('sequence-restart')
    def test_completion_and_callback_are_atomic(self): self.check_case('completion-callback')
    def test_original_completion_gap_is_closed(self): self.check_case('completion-legacy-gap')
    def test_null_renderer_and_missing_tree(self): self.check_case('null-start')
    def test_shared_interstitial_disabled(self): self.check_case('interstitial-disabled')
    def test_status_queries_during_reset_and_start(self): self.check_case('status-race')

    def test_regressions_are_detected(self):
        # Negative controls establish that scheduling tests fail when either
        # the original ordering or stale-session admission is reintroduced.
        if os.environ.get('SAFE_LANDING_BASELINE') == '1':
            self.skipTest('negative controls target the fixed source shape')
        mutations = {
            'non-atomic-completion': (
                self.driver.replace('void SafeLanding::updateTracking() {\n    Locker lock(_lock);',
                                    'void SafeLanding::updateTracking() {\n    std::unique_lock<TestMutex> lock(_lock);')
                .replace('            stopTrackingLocked();', '            lock.unlock(); stopTracking();'),
                'completion-callback'),
            'guard-before-lock': (
                self.driver.replace(
                    '    Locker lock(_lock);\n    if (!_trackingEntities || !_entityTreeRenderer || generation != _generation) {\n        return;\n    }',
                    '    if (!_trackingEntities || !_entityTreeRenderer || generation != _generation) {\n        return;\n    }\n    Locker lock(_lock);'),
                'callback-stop'),
            'no-session-check': (
                self.driver.replace(' || generation != _generation', '').replace(' && generation == _generation', ''),
                'callback-restart'),
            'stale-delete': (
                self.driver.replace(' && generation == _generation', ''),
                'queued-delete'),
        }
        path = Path(self.tmp.name)
        for name, (source, case) in mutations.items():
            for mode in ('pico', 'shared'):
                with self.subTest(regression=name, platform=mode):
                    self.assertNotEqual(source, self.driver)
                    cpp, exe = path / (mode + '-' + name + '.cpp'), path / (mode + '-' + name)
                    cpp.write_text(source)
                    defines = ['-DANDROID_APP_PICO_INTERFACE'] if mode == 'pico' else []
                    subprocess.run(['c++', '-std=c++17', '-O1', '-fPIC', '-pthread', *defines,
                                    str(cpp), '-o', str(exe), *self.flags], check=True, timeout=60)
                    result = subprocess.run([str(exe), case], capture_output=True, timeout=15,
                                            preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
                    self.assertIn(result.returncode, (-signal.SIGABRT, -signal.SIGSEGV),
                                  'regression must fail by assertion or invalid renderer access')
                    print(f'Negative control {name} [{mode}]: signal {-result.returncode}', flush=True)



if __name__ == '__main__':
    unittest.main()
