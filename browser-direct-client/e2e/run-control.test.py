#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Real owned-process regressions; no browser, domain, display or GPU involved."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

spec = importlib.util.spec_from_file_location("own_browser_runner", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

HOLDER = """
import fcntl,importlib.util,json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from manage import process_identity
directory=Path(sys.argv[2]); corrupt=sys.argv[3]=='true'
spec=importlib.util.spec_from_file_location('owned_holder_runner',sys.argv[4])
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
runner.REGISTRY=directory/'registry.json'
with (directory/'run.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 worker=subprocess.Popen([sys.executable,'-c',"import time;print('ready',flush=True);time.sleep(20)"],stdout=subprocess.PIPE,text=True)
 try:
  assert worker.stdout.readline().strip()=='ready'
  identity=process_identity(worker.pid)
  if corrupt: identity['startTicks']=str(int(identity['startTicks'])+1)
  # Match the production launcher's atomic publication, including final cleanup.
  # A reader must never observe the fixture's truncate/write window.
  runner.save({'driver':{'parent':identity,'children':[]}})
  print('ready',flush=True)
  if corrupt:
   time.sleep(.5)
   assert worker.poll() is None,'Wrong start ticks must prevent signals'
   worker.terminate();worker.wait(timeout=2)
  else:
   assert worker.wait(timeout=5)==-15,'Active owned stop must terminate its exact registered driver'
 finally:
  if worker.poll() is None: worker.terminate();worker.wait(timeout=2)
  worker.stdout.close()
  runner.save({})
"""


INTERRUPTED_HOLDER = r'''
import fcntl,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('owned_interrupted_runner',sys.argv[1])
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
directory=Path(sys.argv[2]);runner.REGISTRY=directory/'registry.json';state={}
lock=(directory/'registry.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
# A missing handler deliberately exercises the old default TERM/HUP behavior.
begin_cleanup,restore=getattr(runner,'install_launcher_interruption_handlers',lambda:(lambda:None,lambda:None))()
outsider=None
try:
 worker=runner.start(state,'driver',[sys.executable,'-c',
  "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True);print('ready',flush=True);time.sleep(20)"],
  os.environ.copy(),directory/'worker.log')
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  runner.refresh(state)
  if state['driver']['children'] and 'ready' in (directory/'worker.log').read_text():break
  time.sleep(.02)
 assert state['driver']['children'],'Actual owned grandchild must be registered'
 outsider=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'],start_new_session=True,
  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 identity=runner.process_identity(outsider.pid);changed=dict(identity);changed['startTicks']=str(int(changed['startTicks'])+1)
 state['changed-identity']={'parent':changed,'children':[]};runner.save(state)
 (directory/'fixture-identities.json').write_text(json.dumps({'driver':state['driver'],'outsider':identity}))
 print('ready',flush=True)
 while True:time.sleep(.05)
finally:
 begin_cleanup();print('cleanup',flush=True)
 # Test a second interruption while the original cleanup owns the registry.
 time.sleep(.15)
 try:
  runner.stop(state)
  identities=json.loads((directory/'fixture-identities.json').read_text())
  (directory/'cleanup-proof.json').write_text(json.dumps({
   'driverStopped':not runner.owns_process(identities['driver']['parent']),
   'registeredChildrenStopped':all(not runner.owns_process(child) for child in identities['driver']['children']),
   'changedIdentityRemainedAlive':outsider is not None and outsider.poll() is None,
   'registryEmpty':json.loads(runner.REGISTRY.read_text())=={}}))
 finally:
  if outsider is not None and outsider.poll() is None:outsider.terminate();outsider.wait(timeout=2)
  restore();lock.close()
'''


class LauncherInterruptionTests(unittest.TestCase):
    def exercise(self, first_signal):
        with tempfile.TemporaryDirectory(prefix="owned-launcher-interruption-") as temporary:
            directory = Path(temporary)
            holder = subprocess.Popen([sys.executable, "-c", INTERRUPTED_HOLDER,
                str(Path(__file__).with_name("run.py")), str(directory)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=runner.CLIENT,
                start_new_session=True)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "ready")
                holder.send_signal(first_signal)
                self.assertEqual(holder.stdout.readline().strip(), "cleanup")
                holder.send_signal(signal.SIGHUP if first_signal == signal.SIGTERM else signal.SIGTERM)
                _, errors = holder.communicate(timeout=8)
                self.assertEqual(holder.returncode, 128 + first_signal, errors)
                self.assertEqual(json.loads((directory / "cleanup-proof.json").read_text()), {
                    "driverStopped": True, "registeredChildrenStopped": True,
                    "changedIdentityRemainedAlive": True, "registryEmpty": True})
                with (directory / "registry.json").with_suffix(".lock").open("a") as lock:
                    runner.acquire_run_lock(lock, False, directory / "registry.json")
            finally:
                if holder.poll() is None:
                    holder.kill(); holder.wait(timeout=3)
                # Also clean this fixture safely when checking the old failing behavior.
                identities = directory / "fixture-identities.json"
                if identities.exists():
                    values = json.loads(identities.read_text())
                    for identity in [values["driver"]["parent"], *values["driver"]["children"], values["outsider"]]:
                        if runner.owns_process(identity):
                            os.kill(identity["pid"], signal.SIGTERM)
                holder.stdout.close(); holder.stderr.close()

    def test_term_closes_actual_owned_driver_children_without_signalling_changed_identity(self):
        self.exercise(signal.SIGTERM)

    def test_hup_and_repeated_cleanup_signal_cannot_orphan_actual_owned_processes(self):
        self.exercise(signal.SIGHUP)


class ActiveStopTests(unittest.TestCase):
    def exercise(self, corrupt: bool, parent: Path | None = None):
        parent = parent or runner.STATE / "e2e"
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="runner-stop-regression-", dir=parent) as temporary:
            directory = Path(temporary)
            holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(runner.LAB), str(directory), str(corrupt).lower(),
                                       str(Path(__file__).with_name("run.py"))],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=runner.CLIENT)
            try:
                self.assertEqual(holder.stdout.readline().strip(), "ready")
                with (directory / "run.lock").open("a") as lock:
                    runner.acquire_run_lock(lock, True, directory / "registry.json")
                output, errors = holder.communicate(timeout=8)
                self.assertEqual(holder.returncode, 0, errors)
                self.assertEqual(json.loads((directory / "registry.json").read_text()), {})
            finally:
                if holder.poll() is None: holder.terminate(); holder.wait(timeout=3)
                holder.stdout.close(); holder.stderr.close()

    def test_active_owned_runner_stop_acquires_lock_after_cleanup(self):
        self.exercise(False)

    def test_changed_process_start_ticks_prevent_signals(self):
        self.exercise(True)

    def test_fresh_checkout_missing_result_parent(self):
        with tempfile.TemporaryDirectory(prefix="fresh-runner-parent-") as temporary:
            parent = Path(temporary) / "missing-build" / "browser-direct" / "e2e"
            self.assertFalse(parent.exists())
            self.exercise(False, parent)
            self.assertTrue(parent.is_dir())


class NativeDiagnosticBindingTests(unittest.TestCase):
    def setUp(self):
        self.native = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(10)"], start_new_session=True)
        self.identity = runner.process_identity(self.native.pid)
        self.visitor = {"parent": self.identity}
        self.qualification = {"nativeProcessIdentity": self.identity, "nativeMotionControlVersion": 2,
            "observerScriptSHA256": "reviewed-source", "explicitNativePlacementObservation": {"session": "unit-session"}}

    def tearDown(self):
        if self.native.poll() is None:
            self.native.terminate()
        self.native.wait(timeout=3)

    def test_stationary_mode_cannot_launch_native_actions_but_named_motion_mode_can(self):
        self.assertEqual(runner.qualify_native_browser("avatar-probe", self.visitor, self.qualification, "reviewed-source"), "unit-session")
        for mode in ("avatar-probe", "asset-probe", "asset-dispatch-probe", "scene-probe", "benchmark"):
            with self.assertRaises(RuntimeError):
                runner.require_native_action_mode(mode)
        runner.require_native_action_mode("direct")
        runner.require_native_action_mode("avatar-motion-probe")

    def test_motion_diagnostic_requires_actual_live_pinned_process_and_exact_observer_source(self):
        self.assertEqual(runner.qualify_native_browser("avatar-motion-probe", self.visitor, self.qualification, "reviewed-source"), "unit-session")
        corrupt = {**self.identity, "startTicks": str(int(self.identity["startTicks"]) + 1)}
        with self.assertRaises(RuntimeError):
            runner.qualify_native_browser("avatar-motion-probe", {"parent": corrupt},
                {**self.qualification, "nativeProcessIdentity": corrupt}, "reviewed-source")
        for changes in ({"nativeProcessIdentity": corrupt}, {"nativeMotionControlVersion": 1}, {"observerScriptSHA256": "stale-source"}):
            with self.assertRaises(RuntimeError):
                runner.qualify_native_browser("avatar-motion-probe", self.visitor, {**self.qualification, **changes}, "reviewed-source")
        self.native.terminate(); self.native.wait(timeout=3)
        with self.assertRaises(RuntimeError):
            runner.qualify_native_browser("avatar-motion-probe", self.visitor, self.qualification, "reviewed-source")


class AssetDispatchModeTests(unittest.TestCase):
    def test_page_diagnostic_requires_reviewed_digest_and_rejects_changed_current_artifacts(self):
        manifest = b'complete-current-manifest'; digest = runner.hashlib.sha256(manifest).hexdigest()
        runner.require_validated_bundle("asset-dispatch-probe", digest, manifest)
        for missing in (None, "", "a" * 63, "A" * 64, "z" * 64):
            with self.assertRaises(RuntimeError):
                runner.require_validated_bundle("asset-dispatch-probe", missing, manifest)
        with self.assertRaises(RuntimeError):
            runner.require_validated_bundle("asset-dispatch-probe", digest, manifest + b'changed')
        with self.assertRaises(RuntimeError):
            runner.require_validated_bundle("benchmark-asset-route", digest, manifest)
        runner.require_validated_bundle("benchmark-asset-route", None, manifest)

    def test_asset_route_comparison_keeps_original_batch_bound_without_native_actions(self):
        self.assertIn("benchmark-asset-route", runner.DIRECT_NATIVE_MODES)
        self.assertEqual(runner.BROWSER_DRIVERS["benchmark-asset-route"], "benchmark.mjs")
        self.assertEqual(runner.driver_budget_seconds("benchmark-asset-route", 240), 1200)
        self.assertEqual(runner.driver_budget_seconds("benchmark-asset-route", 99999), 1200)
        with self.assertRaises(RuntimeError):
            runner.require_native_action_mode("benchmark-asset-route")
        with self.assertRaises(RuntimeError):
            runner.qualify_native_browser("benchmark-asset-route", {}, {}, "source")

    def test_real_domain_dispatch_probe_has_one_fixed_budget_and_no_native_action_authority(self):
        self.assertIn("asset-dispatch-probe", runner.DIRECT_NATIVE_MODES)
        self.assertEqual(runner.BROWSER_DRIVERS["asset-dispatch-probe"], "asset-dispatch-probe-driver.mjs")
        self.assertEqual(runner.driver_budget_seconds("asset-dispatch-probe", 240), 315)
        self.assertEqual(runner.driver_budget_seconds("asset-dispatch-probe", 99999), 315)
        with self.assertRaises(RuntimeError):
            runner.require_native_action_mode("asset-dispatch-probe")
        with self.assertRaises(RuntimeError):
            runner.qualify_native_browser("asset-dispatch-probe", {}, {}, "source")
        self.assertEqual(runner.driver_budget_seconds("benchmark", 240), 1200)
        self.assertEqual(runner.driver_budget_seconds("permission-probe", 55), 180)
        self.assertEqual(runner.driver_budget_seconds("direct", 180), 1080)


if __name__ == "__main__":
    unittest.main()
