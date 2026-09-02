#!/usr/bin/env python3
"""Mock-ADB contract tests for both concrete Android adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "verify_adapter.py"
ADAPTER = ROOT / "adapters/android/adapter.py"


MOCK_ADB = r'''#!/usr/bin/env python3
import json,os,shlex,sys,time
raw=sys.argv[1:]
argv_log=os.environ.get("MOCK_ADB_ARGV_LOG", "")
if argv_log:
    with open(argv_log,"a") as output: output.write(json.dumps(raw)+"\n")
a=list(raw)
isolated=len(a) >= 2 and a[0] == "-P"
if isolated:
    if a[1] != os.environ.get("ANDROID_ADB_SERVER_PORT", a[1]): raise SystemExit(9)
    a=a[2:]
target = a[1] if len(a) > 2 and a[0] == "-s" else None
cmd = a[2:] if target else a
status_path=os.environ.get("MOCK_PICO_OPENXR_STATUS", "")
grant_log=os.environ.get("MOCK_PICO_OPENXR_GRANTS", "")
process_path=os.environ.get("MOCK_ANDROID_PROCESS_STATE", "")
process_state=open(process_path).read().strip() if process_path and os.path.exists(process_path) else "running"
version_state_path=os.environ.get("MOCK_ANDROID_VERSION_STATE", "")
version_state=(open(version_state_path).read().strip()
               if version_state_path and os.path.exists(version_state_path)
               else os.environ.get("MOCK_ANDROID_VERSION", "0.1.0"))
foreground_path=os.environ.get("MOCK_ANDROID_FOREGROUND_STATE", "")
foreground_state=(open(foreground_path).read().strip()
                  if foreground_path and os.path.exists(foreground_path) else "foreground")
home_state_path=os.environ.get("MOCK_ANDROID_HOME_STATE", "")
home_ignored_events=int(os.environ.get("MOCK_ANDROID_HOME_IGNORED_EVENTS", "0"))
control_state_path=os.environ.get("MOCK_ANDROID_CONTROL_STATE", "")
control_available=os.environ.get("MOCK_ANDROID_CONTROL_AVAILABLE", "") == "1"
control_after=int(os.environ.get("MOCK_ANDROID_CONTROL_AFTER_READS", "0"))
control_sequence_path=os.environ.get("MOCK_ANDROID_CONTROL_SEQUENCE_STATE", "")
control_sequence=(int(open(control_sequence_path).read())
                  if control_sequence_path and os.path.exists(control_sequence_path) else 0)
connection_state_path=os.environ.get("MOCK_ANDROID_CONNECTION_STATE", "")
connection_offline_reads=int(os.environ.get("MOCK_ANDROID_CONNECTION_OFFLINE_READS", "0"))
probe_available=os.environ.get("MOCK_ANDROID_PROBE_AVAILABLE", "1") == "1"
probe_control_after=int(os.environ.get("MOCK_ANDROID_PROBE_CONTROL_AFTER_READS", "0"))
control_payload_log=os.environ.get("MOCK_ANDROID_CONTROL_PAYLOAD_LOG", "")
pico_tablet_observation=os.environ.get("MOCK_PICO_TABLET_OBSERVATION", "")
pico_tablet_command=os.environ.get("MOCK_PICO_TABLET_COMMAND", "")
pico_tablet_status=os.environ.get("MOCK_PICO_TABLET_STATUS", "")
probe_sequence_path=os.environ.get("MOCK_PROBE_SEQUENCE_STATE", "")
probe_sequence=int(open(probe_sequence_path).read()) if probe_sequence_path and os.path.exists(probe_sequence_path) else 0
if cmd in (["devices", "-l"], ["devices"]):
    if isolated:
        count=int(os.environ.get("MOCK_PICO_DEVICE_COUNT", "1"))
        print("List of devices attached\n" + "\n".join(
            "pico-secret" + ("" if index == 0 else "-" + str(index + 1)) + " device"
            for index in range(count)))
    else: print("List of devices attached\nphone-secret device model:Phone\npico-secret device model:PICO")
elif cmd == ["get-state"]:
    connection_reads=(int(open(connection_state_path).read())
                      if connection_state_path and os.path.exists(connection_state_path) else 0)
    if connection_state_path: open(connection_state_path,"w").write(str(connection_reads + 1))
    print("offline" if connection_reads < connection_offline_reads else "device")
elif cmd[:2] == ["shell", "getprop"]:
    prop=cmd[2]
    pico=bool(target and target.startswith("pico-secret"))
    values={
      "ro.product.manufacturer": "PICO" if pico else "Example",
      "ro.product.brand": "PICO" if pico else "Example",
      "ro.product.model": "PICO 4" if pico else "Test Phone",
      "ro.product.device": "phoenix" if pico else "phone",
      "ro.build.characteristics": "vr" if pico else "default",
      "ro.product.cpu.abilist": "arm64-v8a,armeabi-v7a",
      "ro.build.version.sdk": "36", "ro.build.version.release": "17",
      "ro.opengles.version": "196610", "ro.kernel.qemu": "0"}
    print(values.get(prop, ""))
elif cmd == ["shell", "pm", "list", "features"]: print("feature:android.hardware.touchscreen")
elif cmd[:4] == ["shell", "pidof", "-s", "org.overte.phone"] and process_state != "stopped": print("45" if process_state == "restarted" else "42")
elif cmd[:4] == ["shell", "pidof", "-s", "org.overte.pico"] and process_state != "stopped": print("44" if process_state == "restarted" else "43")
elif cmd[:3] == ["shell", "cat", "/proc/42/stat"]: print("42 (app) S " + "0 "*18 + "123 0")
elif cmd[:3] == ["shell", "cat", "/proc/43/stat"]: print("43 (app) S " + "0 "*18 + "124 0")
elif cmd[:3] == ["shell", "cat", "/proc/44/stat"]: print("44 (app) S " + "0 "*18 + "125 0")
elif cmd[:3] == ["shell", "cat", "/proc/45/stat"]: print("45 (app) S " + "0 "*18 + "126 0")
elif cmd == ["shell", "dumpsys", "activity", "activities"]:
    package=("com.pvr.home" if foreground_state == "background" else
             ("org.overte.pico" if target and target.startswith("pico-secret") else "org.overte.phone"))
    print("mResumedActivity: x u0 " + package + "/.Main t1")
elif cmd[:3] == ["shell", "am", "force-stop"]:
    if process_path: open(process_path,"w").write("stopped")
elif cmd[:4] == ["shell", "am", "start", "-W"]:
    if process_path: open(process_path,"w").write("running")
    if foreground_path: open(foreground_path,"w").write("foreground")
    print("Status: ok")
elif cmd == ["shell", "input", "keyevent", "KEYCODE_HOME"]:
    home_events=(int(open(home_state_path).read())
                 if home_state_path and os.path.exists(home_state_path) else 0)
    if home_state_path: open(home_state_path,"w").write(str(home_events + 1))
    if foreground_path and home_events >= home_ignored_events:
        open(foreground_path,"w").write("background")
elif cmd[:4] == ["install", "-r", "-d", "-g"]:
    if process_path: open(process_path,"w").write("stopped")
    if version_state_path:
        open(version_state_path,"w").write(os.environ.get("MOCK_ANDROID_SOURCE_VERSION", version_state))
    print("Success")
elif cmd[:3] == ["install", "-r", "-g"]:
    if process_path: open(process_path,"w").write("stopped")
    if version_state_path:
        open(version_state_path,"w").write(os.environ.get("MOCK_ANDROID_CANDIDATE_VERSION", version_state))
    print("Success")
elif cmd[:3] == ["shell", "dumpsys", "package"]:
    print("  versionName=" + version_state)
elif len(cmd) == 3 and cmd[:2] == ["shell", "-T"]:
    payload=sys.stdin.buffer.read()
    if "commands.json" in cmd[2]:
        envelope=json.loads(payload)
        if status_path:
            open(status_path+".operation","w").write(
                envelope["commands"][0]["operation"])
    elif "grant.json" in cmd[2]:
        grant=json.loads(payload)
        operation=(open(status_path+".operation").read()
                   if status_path and os.path.exists(status_path+".operation") else "")
        is_look=operation == "input.look"
        is_move=operation == "input.move"
        is_tablet=operation.startswith("tablet.")
        is_vertical=operation in {"input.jump","input.fly"}
        status={"schemaVersion":1,"buildMarker":"OVERTE_E2E_OPENXR_INPUT_V1",
          "consumer":"XR_APILAYER_OVERTE_e2e_input",
          "profileId":"overte-pico4-controller-v1",
          "bindingProfileSha256":grant["bindingProfileSha256"],"enabled":True,
          "acceptedSequence":grant["sequence"],"acceptedNonce":grant["sessionNonce"],
          "viewAppliedSequence":grant["sequence"] if is_look else 0,
          "viewAppliedYawDegrees":25.0 if is_look else 0.0,
          "viewAppliedPitchDegrees":0.0,
          "vectorAppliedSequence":grant["sequence"] if is_move else 0,
          "leftThumbstickAppliedX":0.0,
          "leftThumbstickAppliedY":0.4 if is_move else 0.0,
          "booleanAppliedSequence":grant["sequence"] if (is_tablet or is_vertical) else 0,
          "leftSecondaryApplied":is_tablet,"rightSecondaryApplied":is_vertical,
          "activeCommandId":"mock-command","state":"active","detail":"command-window",
          "updatedEpochMs":int(time.time()*1000)}
        if status_path:
            open(status_path,"w").write(json.dumps(status))
            open(status_path+".reads","w").write("0")
        if grant_log:
            with open(grant_log,"a") as output: output.write(json.dumps(grant)+"\n")
elif cmd and cmd[0] == "exec-out" and "status.json" in cmd[-1]:
    if status_path and os.path.exists(status_path):
        status=json.loads(open(status_path).read())
        reads_path=status_path+".reads"
        reads=(int(open(reads_path).read())
               if os.path.exists(reads_path) else 0)
        # Model the two distinct native observations deterministically: the
        # first read acknowledges the grant and the second proves that an
        # action query consumed it. The following read exposes the neutral
        # inter-command window without depending on host scheduling latency.
        if status["state"] == "active" and reads >= 2:
            status["state"]="neutral"; status["detail"]="neutral-window"
            status["updatedEpochMs"]=int(time.time()*1000)
            open(status_path,"w").write(json.dumps(status))
        elif status["state"] == "active":
            open(reads_path,"w").write(str(reads+1))
        print(json.dumps(status))
elif cmd and cmd[0] == "exec-out" and "grant.json" in cmd[-1]:
    if status_path and os.path.exists(status_path):
        status=json.loads(open(status_path).read()); status["state"]="neutral"
        status["detail"]="grant-removed"; status["updatedEpochMs"]=int(time.time()*1000)
        open(status_path,"w").write(json.dumps(status))
elif (len(cmd) == 2 and cmd[0] == "shell"
      and (shlex.split(cmd[1])[:3] == ["run-as", "org.overte.phone", "sh"]
           or shlex.split(cmd[1])[:3] == ["run-as", "org.overte.pico", "sh"])):
    payload=sys.stdin.read()
    remote_arguments=shlex.split(cmd[1])
    if remote_arguments[3] != "-c" or remote_arguments[5] != "overte-e2e-write":
        raise SystemExit(8)
    remote=remote_arguments[6]
    if remote.endswith("tablet-ui-command.json"):
        if pico_tablet_command: open(pico_tablet_command,"w").write(payload)
        command=json.loads(payload)
        if pico_tablet_status:
            status={"schemaVersion":1,"commandId":command["commandId"],
                    "performed":True,"error":"",
                    "updatedEpochMs":int(time.time()*1000)}
            open(pico_tablet_status,"w").write(json.dumps(status))
    elif control_state_path: open(control_state_path,"w").write(payload)
    if control_payload_log:
        with open(control_payload_log,"a") as output:
            output.write(json.dumps({"path":remote,"payload":payload})+"\n")
    if os.environ.get("MOCK_ANDROID_RESTART_ON_CONTROL", "") == "1" and process_path:
        open(process_path,"w").write("restarted")
elif cmd[:4] == ["shell", "run-as", "org.overte.phone", "cat"] or cmd[:4] == ["shell", "run-as", "org.overte.pico", "cat"]:
    remote=cmd[4]
    if remote.endswith("android-control.json"):
        control_sequence += 1
        if control_sequence_path:
            open(control_sequence_path,"w").write(str(control_sequence))
        if control_available and control_sequence > control_after:
            print(json.dumps({"schemaVersion":1,"channel":"android-debug-file-v1",
                              "probe":"overte_e2e_probe.js"},separators=(",",":"),sort_keys=True))
    elif remote.endswith("android-control-command.json"):
        if control_state_path and os.path.exists(control_state_path):
            print(open(control_state_path).read(),end="")
    elif remote.endswith("tablet-ui-observation.json"):
        if pico_tablet_observation and os.path.exists(pico_tablet_observation):
            print(open(pico_tablet_observation).read(),end="")
    elif remote.endswith("tablet-ui-command.json"):
        if pico_tablet_command and os.path.exists(pico_tablet_command):
            print(open(pico_tablet_command).read(),end="")
    elif remote.endswith("tablet-ui-status.json"):
        if pico_tablet_status and os.path.exists(pico_tablet_status):
            print(open(pico_tablet_status).read(),end="")
    elif probe_available:
        probe_sequence += 1
        if probe_sequence_path: open(probe_sequence_path,"w").write(str(probe_sequence))
        stale_reads=int(os.environ.get("MOCK_PROBE_STALE_READS", "0"))
        sampled=1 if probe_sequence <= stale_reads else int(time.time()*1000)
        snapshot={"schemaVersion":1,"sampleEpochMs":sampled,"sampleSequence":probe_sequence,
          "build":{"platform":"Mock","version":"android-contract","date":"1970-01-01"},
          "application":{"running":True,"foreground":True},
          "scene":{"url":"file:///fixture/scene.json","ready":True,"entityCount":4,
                   "fixtureMarkerCount":4},
          "avatar":{"position":{"x":0,"y":1,"z":4}},
          "view":{"orientation":{"x":0,"y":0,"z":0}},
          "tablet":{"open":False}}
        if control_available and probe_sequence > probe_control_after:
            last_command_id=""
            if control_state_path and os.path.exists(control_state_path):
                try:
                    last_command_id=json.loads(
                        open(control_state_path).read()).get("commandId","")
                except (OSError,ValueError,TypeError):
                    last_command_id=""
            snapshot["control"]={"schemaVersion":1,"channel":"android-debug-file-v1",
                                 "probe":"overte_e2e_probe.js",
                                 "lastCommandId":last_command_id}
        print(json.dumps(snapshot))
else: print("Success")
'''


class AndroidAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="android-adapter-test-")
        self.adb = Path(self.temporary.name) / "adb"
        self.adb.write_text(MOCK_ADB, encoding="utf-8")
        self.adb.chmod(0o700)
        self.environment = os.environ.copy()
        for name in (
                "OVERTE_ANDROID_E2E_DEBUG", "OVERTE_PICO_OPENXR_INPUT",
                "ANDROID_ADB_SERVER_PORT", "OVERTE_PICO_OPENXR_STATE_DIR"):
            self.environment.pop(name, None)
        default_process = Path(self.temporary.name) / "default-process"
        default_process.write_text("running", encoding="utf-8")
        self.environment["OVERTE_ANDROID_ADB"] = str(self.adb)
        self.environment["OVERTE_ANDROID_E2E_PROBE_ATTEMPTS"] = "1"
        self.environment["MOCK_ANDROID_PROCESS_STATE"] = str(default_process)

    def tearDown(self):
        self.temporary.cleanup()

    def test_android_control_reads_app_private_files_through_module_loader(self):
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn('Script.require("./android-control.json")', probe)
        self.assertIn(
            'Script.require("./android-control-command.json?sample="', probe)
        self.assertNotIn('request.open("GET", Script.resolvePath("android-control', probe)

    def test_probe_retains_asynchronous_control_requests_until_completion(self):
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        for name in ("clientCommandRequest", "soundCommandRequest"):
            self.assertIn(f"var {name} = null;", probe)
            self.assertIn(f"{name} = request;", probe)
            self.assertIn(f"{name} = null;", probe)
        self.assertIn('Script.require("./android-control.json")', probe)
        self.assertIn('Script.require("./android-control-command.json?sample="', probe)
        for obsolete_name in ("clientCommandRequestPending",
                              "androidControlCommandRequestPending",
                              "androidControlMarkerRequestPending",
                              "soundCommandRequestPending"):
            self.assertNotIn(obsolete_name, probe)

    def verify(self, kind: str) -> subprocess.CompletedProcess:
        return subprocess.run([
            sys.executable, str(VERIFIER), "--adapter-manifest",
            str(ROOT / "adapters" / "android" / f"{kind}.json"), "--check-cleanup",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

    def prepare_pico_session(self, prefix: str) -> list[str]:
        state = Path(self.temporary.name) / f"{prefix}-state"
        state.mkdir(mode=0o700)
        process = Path(self.temporary.name) / f"{prefix}-process"
        process.write_text("stopped", encoding="utf-8")
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
        })
        common = [sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
                  "--target", "pico-secret"]
        launched = subprocess.run(
            [*common, "--operation", "app.launch", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, launched.returncode, launched.stdout)
        return common

    def enable_controlled_phone(self) -> tuple[Path, Path, Path]:
        process = Path(self.temporary.name) / "phone-process"
        process.write_text("running", encoding="utf-8")
        state = Path(self.temporary.name) / "android-control-command.json"
        payload_log = Path(self.temporary.name) / "android-control-payloads.jsonl"
        argv_log = Path(self.temporary.name) / "android-control-adb.jsonl"
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "MOCK_ANDROID_CONTROL_AVAILABLE": "1",
            "MOCK_ANDROID_CONTROL_STATE": str(state),
            "MOCK_ANDROID_CONTROL_PAYLOAD_LOG": str(payload_log),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })
        return process, payload_log, argv_log

    def discover_phone(self) -> list[str]:
        result = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "phone", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        return json.loads(result.stdout)[0]["capabilities"]

    def invoke_phone(self, operation: str, arguments: dict) -> subprocess.CompletedProcess:
        return subprocess.run([
            sys.executable, str(ADAPTER), "--kind", "phone", "invoke",
            "--target", "phone-secret", "--operation", operation,
            "--arguments", json.dumps(arguments),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)

    def start_fixture(self) -> tuple[subprocess.Popen, dict]:
        ready = Path(self.temporary.name) / "fixture-ready.json"
        process = subprocess.Popen([
            sys.executable, str(ROOT / "fixture/serve.py"),
            "--ready-file", str(ready),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            if process.poll() is not None:
                break
            time.sleep(0.02)
        if not ready.exists():
            stdout, stderr = process.communicate(timeout=2)
            self.fail(f"fixture failed: {stdout}\n{stderr}")
        self.addCleanup(process.communicate, timeout=5)
        self.addCleanup(process.terminate)
        return process, json.loads(ready.read_text(encoding="utf-8"))

    def test_phone_profile_discovers_only_phone(self):
        result = self.verify("phone")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("for 1 target(s)", result.stdout)

    def test_pico_profile_discovers_only_pico(self):
        result = self.verify("pico")
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertIn("for 1 target(s)", result.stdout)

    def test_debug_e2e_fixture_capabilities_satisfy_contract(self):
        self.environment["OVERTE_ANDROID_E2E_DEBUG"] = "1"
        for kind in ("phone", "pico"):
            result = self.verify(kind)
            self.assertEqual(0, result.returncode, result.stdout)

    def test_pico_does_not_advertise_an_unaudited_accessibility_tree(self):
        state = Path(self.temporary.name) / "accessibility-state"
        state.mkdir(mode=0o700)
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
        })
        result = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        capabilities = json.loads(result.stdout)[0]["capabilities"]
        self.assertNotIn("accessibility.snapshot", capabilities)

    def test_controlled_capabilities_are_declared_before_suite_launch(self):
        controlled = {"asset.load", "navigation.enter-domain", "sound.play"}
        self.assertTrue(controlled.isdisjoint(self.discover_phone()))

        self.environment["OVERTE_ANDROID_E2E_DEBUG"] = "1"
        self.assertTrue(controlled.issubset(self.discover_phone()))

        # Capabilities describe what the configured debug build can do after
        # launch-smoke.  Transient marker/probe state is validated only when
        # the operation is invoked, not during the runner's one-time discovery.
        self.environment["MOCK_ANDROID_CONTROL_AVAILABLE"] = "1"
        self.environment["MOCK_ANDROID_PROBE_AVAILABLE"] = "0"
        self.assertTrue(controlled.issubset(self.discover_phone()))

        self.environment["MOCK_ANDROID_PROBE_AVAILABLE"] = "1"
        self.environment["MOCK_PROBE_STALE_READS"] = "999"
        self.assertTrue(controlled.issubset(self.discover_phone()))

        self.environment.pop("MOCK_PROBE_STALE_READS")
        self.assertTrue(controlled.issubset(self.discover_phone()))

    def test_controlled_operations_deliver_exact_payloads_without_relaunch(self):
        _process, payload_log, argv_log = self.enable_controlled_phone()
        _fixture_process, fixture = self.start_fixture()
        domain_url = "hifi://127.0.0.1:40102/0,0,4/0,0,0,1"
        asset_arguments = {
            "assetId": fixture["asset"]["id"],
            "url": fixture["asset"]["url"] + "?requestId=android-exact",
            "entityName": fixture["asset"]["entityName"],
        }
        sound_arguments = {
            "schemaVersion": 1,
            "commandId": "sound-android-exact",
            "url": fixture["soundUrl"] + "?e2eCommand=sound-android-exact",
            "commandUrl": fixture["soundCommandUrl"],
        }
        for operation, arguments in (
                ("navigation.enter-domain", {"url": domain_url}),
                ("asset.load", asset_arguments),
                ("sound.play", sound_arguments)):
            result = self.invoke_phone(operation, arguments)
            self.assertEqual(0, result.returncode, result.stdout)
            response = json.loads(result.stdout)
            self.assertTrue(response["requested"])
            if operation == "sound.play":
                self.assertEqual(sound_arguments["commandId"], response["commandId"])

        payloads = [json.loads(item)["payload"]
                    for item in payload_log.read_text(encoding="utf-8").splitlines()]
        commands = [json.loads(item) for item in payloads]
        self.assertEqual({"schemaVersion", "commandId", "action", "url"},
                         set(commands[0]))
        self.assertTrue(commands[0]["commandId"].startswith(
            "android-navigation-enter-domain-"))
        self.assertEqual("enter-domain", commands[0]["action"])
        self.assertEqual(domain_url, commands[0]["url"])
        self.assertEqual({"schemaVersion", "commandId", "action", "assetId",
                          "entityName", "url"}, set(commands[1]))
        self.assertTrue(commands[1]["commandId"].startswith("android-asset-load-"))
        self.assertEqual({
            "action": "load-asset",
            "assetId": asset_arguments["assetId"],
            "entityName": asset_arguments["entityName"],
            "url": asset_arguments["url"],
        }, {key: commands[1][key] for key in
            ("action", "assetId", "entityName", "url")})
        self.assertEqual("sound-channel", commands[2]["action"])
        self.assertEqual({"schemaVersion", "commandId", "action", "commandUrl"},
                         set(commands[2]))
        self.assertTrue(commands[2]["commandId"].startswith("android-sound-play-"))
        self.assertEqual(sound_arguments["commandUrl"], commands[2]["commandUrl"])
        with urlopen(fixture["soundCommandUrl"], timeout=2) as response:
            sound_command = json.load(response)
        self.assertEqual({
            "schemaVersion": 1,
            "commandId": sound_arguments["commandId"],
            "action": "play",
            "soundUrl": sound_arguments["url"],
        }, sound_command)

        adb_commands = [json.loads(line) for line in
                        argv_log.read_text(encoding="utf-8").splitlines()]
        writes = [command for command in adb_commands
                  if len(command) >= 4 and command[2] == "shell"
                  and shlex.split(command[3])[-1].endswith(
                      "android-control-command.json")]
        self.assertEqual(3, len(writes))
        self.assertTrue(all(shlex.split(command[3])[:4]
                            == ["run-as", "org.overte.phone", "sh", "-c"]
                            for command in writes))
        self.assertFalse(any("am" in command and "start" in command
                             for command in adb_commands))
        self.assertFalse(any("force-stop" in command for command in adb_commands))

    def test_safe_setting_uses_the_bounded_debug_command(self):
        _process, payload_log, _argv_log = self.enable_controlled_phone()
        result = self.invoke_phone("setting.set", {
            "settingId": "audio.warn-when-muted", "enabled": False})
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual({"performed": True}, json.loads(result.stdout))
        command = json.loads(json.loads(
            payload_log.read_text(encoding="utf-8").splitlines()[0])["payload"])
        self.assertEqual({
            "schemaVersion", "commandId", "action", "settingId", "enabled"},
            set(command))
        self.assertEqual("set-safe-setting", command["action"])
        self.assertEqual("audio.warn-when-muted", command["settingId"])
        self.assertIs(command["enabled"], False)

    def test_versioned_upgrade_is_metadata_checked_and_preserves_package_data(self):
        process, _payload_log, argv_log = self.enable_controlled_phone()
        source = Path(self.temporary.name) / "source.apk"
        candidate = Path(self.temporary.name) / "candidate.apk"
        source.write_bytes(b"source")
        candidate.write_bytes(b"candidate")
        version_state = Path(self.temporary.name) / "installed-version"
        version_state.write_text("1.0.0", encoding="utf-8")
        aapt = Path(self.temporary.name) / "aapt"
        aapt.write_text(
            "#!/bin/sh\n"
            "case \"$3\" in *source.apk) code=1; version=1.0.0 ;; "
            "*) code=2; version=2.0.0 ;; esac\n"
            "printf \"package: name='org.overte.phone' versionCode='%s' "
            "versionName='%s'\\n\" \"$code\" \"$version\"\n", encoding="utf-8")
        aapt.chmod(0o700)
        self.environment.update({
            "OVERTE_E2E_UPGRADE_SOURCE_ARTIFACT": str(source),
            "OVERTE_E2E_UPGRADE_CANDIDATE_ARTIFACT": str(candidate),
            "OVERTE_E2E_UPGRADE_FROM_VERSION": "1.0.0",
            "OVERTE_E2E_UPGRADE_TO_VERSION": "2.0.0",
            "OVERTE_ANDROID_AAPT": str(aapt),
            "MOCK_ANDROID_VERSION_STATE": str(version_state),
            "MOCK_ANDROID_SOURCE_VERSION": "1.0.0",
            "MOCK_ANDROID_CANDIDATE_VERSION": "2.0.0",
        })
        self.assertIn("app.upgrade", self.discover_phone())
        installed = self.invoke_phone("app.install", {"path": str(source)})
        self.assertEqual(0, installed.returncode, installed.stdout)
        result = self.invoke_phone("app.upgrade", {
            "fromVersion": "1.0.0", "toVersion": "2.0.0"})
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual({"applied": True}, json.loads(result.stdout))
        self.assertEqual("2.0.0", version_state.read_text(encoding="utf-8"))
        self.assertEqual("running", process.read_text(encoding="utf-8"))
        commands = [json.loads(line) for line in
                    argv_log.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(command[-4:] == ["install", "-r", "-g", str(candidate)]
                            for command in commands))

    def test_controlled_phone_launch_preserves_confirmed_process(self):
        process, _payload_log, argv_log = self.enable_controlled_phone()

        result = self.invoke_phone("app.launch", {})

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual({"launched": True}, json.loads(result.stdout))
        self.assertEqual("running", process.read_text(encoding="utf-8"))
        adb_commands = [json.loads(line) for line in
                        argv_log.read_text(encoding="utf-8").splitlines()]
        self.assertFalse(any(command[:3] == ["shell", "am", "force-stop"]
                             for command in adb_commands))
        self.assertFalse(any(command[:4] == ["shell", "am", "start", "-W"]
                             for command in adb_commands))

    def test_pico_launch_replaces_an_unbound_orphan_process(self):
        state = Path(self.temporary.name) / "orphan-state"
        state.mkdir(mode=0o700)
        process = Path(self.temporary.name) / "orphan-process"
        process.write_text("running", encoding="utf-8")
        argv_log = Path(self.temporary.name) / "orphan-adb.jsonl"
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })
        result = subprocess.run([
            sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
            "--target", "pico-secret", "--operation", "app.launch",
            "--arguments", "{}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

        self.assertEqual(0, result.returncode, result.stdout)
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        payloads = [command[4:] if command[2:3] == ["-s"] else command[2:]
                    for command in commands]
        self.assertTrue(any(command[:3] == ["shell", "am", "force-stop"]
                            for command in payloads))
        self.assertTrue(any(command[:4] == ["shell", "am", "start", "-W"]
                            for command in payloads))

    def test_pico_launch_waits_for_transient_wlan_reconnect(self):
        state = Path(self.temporary.name) / "reconnect-openxr-state"
        state.mkdir(mode=0o700)
        process = Path(self.temporary.name) / "reconnect-process"
        process.write_text("stopped", encoding="utf-8")
        connection = Path(self.temporary.name) / "reconnect-reads"
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ANDROID_CONNECTION_STATE": str(connection),
            "MOCK_ANDROID_CONNECTION_OFFLINE_READS": "1",
        })

        result = subprocess.run([
            sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
            "--target", "pico-secret", "--operation", "app.launch",
            "--arguments", "{}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertGreaterEqual(int(connection.read_text(encoding="utf-8")), 2)

    def test_pico_invoke_auto_selects_the_isolated_live_target(self):
        state = Path(self.temporary.name) / "auto-select-openxr-state"
        state.mkdir(mode=0o700)
        process = Path(self.temporary.name) / "auto-select-process"
        process.write_text("stopped", encoding="utf-8")
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
        })

        result = subprocess.run([
            sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
            "--operation", "app.launch", "--arguments", "{}",
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
           env=self.environment, check=False)

        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual({"launched": True}, json.loads(result.stdout))

    def test_controlled_pico_launch_reactivates_background_process(self):
        state = Path(self.temporary.name) / "reactivate-state"
        state.mkdir(mode=0o700)
        process = Path(self.temporary.name) / "reactivate-process"
        process.write_text("stopped", encoding="utf-8")
        foreground = Path(self.temporary.name) / "reactivate-foreground"
        foreground.write_text("background", encoding="utf-8")
        home_state = Path(self.temporary.name) / "reactivate-home-events"
        argv_log = Path(self.temporary.name) / "reactivate-adb.jsonl"
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_CONTROL_AVAILABLE": "1",
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ANDROID_FOREGROUND_STATE": str(foreground),
            "MOCK_ANDROID_HOME_STATE": str(home_state),
            "MOCK_ANDROID_HOME_IGNORED_EVENTS": "1",
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })
        common = [sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
                  "--target", "pico-secret"]

        def invoke(operation: str) -> dict:
            result = subprocess.run(
                [*common, "--operation", operation, "--arguments", "{}"],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=self.environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            return json.loads(result.stdout)

        first = subprocess.run(
            [*common, "--operation", "app.launch", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, first.returncode, first.stdout)
        before = invoke("app.process")
        backgrounded = invoke("lifecycle.background")
        self.assertTrue(backgrounded["backgrounded"])
        self.assertFalse(invoke("app.foreground")["foreground"])
        self.assertEqual("2", home_state.read_text(encoding="utf-8"))

        second = subprocess.run(
            [*common, "--operation", "app.launch", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, second.returncode, second.stdout)
        self.assertTrue(invoke("app.foreground")["foreground"])
        self.assertEqual(before, invoke("app.process"))
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        payloads = [command[4:] if command[2:3] == ["-s"] else command[2:]
                    for command in commands]
        self.assertEqual(2, sum(command[:4] == ["shell", "am", "start", "-W"]
                                for command in payloads))

    def test_probe_executes_real_controlled_actions_and_reports_observations(self):
        probe = (ROOT / "probe/overte_e2e_probe.js").read_text(encoding="utf-8")
        self.assertIn('Script.require("./android-control.json")', probe)
        self.assertIn('Script.require("./android-control-command.json?sample="', probe)
        self.assertNotIn('Script.resolvePath("android-control.json")', probe)
        self.assertNotIn('Script.resolvePath("android-control-command.json")', probe)
        self.assertIn("location.handleLookupString(command.url)", probe)
        self.assertNotIn("location.href = command.url", probe)
        self.assertEqual(1, probe.count("androidAssetEntityId = Entities.addEntity("))
        self.assertIn('"userData", "dimensions", "naturalDimensions"', probe)
        self.assertIn("if (!properties.naturalDimensions)", probe)
        self.assertIn("overteE2EAssetId: command.assetId", probe)
        self.assertIn('}, "local")', probe)
        self.assertIn("appendAssetCandidate(candidates, androidAssetEntityId)", probe)
        self.assertIn("appendAssetCandidate(candidates, controlledAssetEntity)", probe)
        self.assertIn('"userData", "dimensions", "naturalDimensions"', probe)
        self.assertIn("naturalDimensions: pendingVector(properties.naturalDimensions)", probe)
        self.assertIn('}, "overte-probe-error.json")', probe)
        self.assertIn("soundCommandUrl = String(command.commandUrl)", probe)
        self.assertIn("SoundCache.getSound(soundState.url)", probe)
        self.assertIn("Audio.playSound(soundResource", probe)
        self.assertNotIn("soundState.resourceReady = true", probe)
        self.assertNotIn("soundState.injectorCreated = true", probe)

    def test_controlled_identity_waits_for_marker_and_probe_without_process_change(self):
        self.enable_controlled_phone()
        marker_sequence = Path(self.temporary.name) / "controlled-marker-sequence"
        marker_sequence.write_text("0", encoding="utf-8")
        probe_sequence = Path(self.temporary.name) / "controlled-probe-sequence"
        probe_sequence.write_text("0", encoding="utf-8")
        self.environment.update({
            "MOCK_ANDROID_CONTROL_AFTER_READS": "2",
            "MOCK_ANDROID_CONTROL_SEQUENCE_STATE": str(marker_sequence),
            "MOCK_ANDROID_PROBE_CONTROL_AFTER_READS": "2",
            "MOCK_PROBE_SEQUENCE_STATE": str(probe_sequence),
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "6",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        })
        result = self.invoke_phone("asset.load", {
            "assetId": "texture-rgb-3x1-v1",
            "url": "http://fixture.invalid/asset.png",
            "entityName": "OVERTE_E2E_ASSET_LOAD_retry",
        })
        self.assertEqual(0, result.returncode, result.stdout)

    def test_controlled_operations_reject_invalid_arguments_before_delivery(self):
        _process, payload_log, _argv_log = self.enable_controlled_phone()
        cases = (
            ("navigation.enter-domain", {"url": "hifi://user@host:40102"}),
            ("asset.load", {
                "assetId": "bad id", "url": "file:///tmp/asset.png",
                "entityName": "OVERTE_E2E_ASSET_LOAD",
            }),
            ("sound.play", {
                "schemaVersion": 1, "commandId": "sound-invalid",
                "url": "file:///tmp/sound.wav", "commandUrl": "not-a-url",
            }),
        )
        for operation, arguments in cases:
            with self.subTest(operation=operation):
                result = self.invoke_phone(operation, arguments)
                self.assertEqual(2, result.returncode, result.stdout)
        self.assertFalse(payload_log.exists())

    def test_controlled_operations_fail_without_debug_or_probe_channel(self):
        arguments = {"url": "hifi://127.0.0.1:40102"}
        missing_debug = self.invoke_phone("navigation.enter-domain", arguments)
        self.assertEqual(2, missing_debug.returncode, missing_debug.stdout)
        self.assertIn("E2E-enabled debug APK", missing_debug.stdout)

        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "MOCK_ANDROID_CONTROL_AVAILABLE": "1",
            "MOCK_ANDROID_PROBE_AVAILABLE": "0",
        })
        missing_probe = self.invoke_phone("navigation.enter-domain", arguments)
        self.assertEqual(2, missing_probe.returncode, missing_probe.stdout)
        self.assertIn("fresh probe and confirmed debug channel", missing_probe.stdout)

    def test_controlled_operation_rejects_process_change_during_delivery(self):
        process, payload_log, _argv_log = self.enable_controlled_phone()
        self.environment["MOCK_ANDROID_RESTART_ON_CONTROL"] = "1"
        result = self.invoke_phone("asset.load", {
            "assetId": "texture-rgb-3x1-v1",
            "url": "http://127.0.0.1:18080/asset.png?requestId=restart",
            "entityName": "OVERTE_E2E_ASSET_LOAD",
        })
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("process changed during asset.load", result.stdout)
        self.assertEqual("restarted", process.read_text(encoding="utf-8"))
        self.assertEqual(1, len(payload_log.read_text(encoding="utf-8").splitlines()))

    def test_debug_launcher_accepts_only_the_embedded_fixture_identifier(self):
        _process, payload_log, _argv_log = self.enable_controlled_phone()
        common = [sys.executable, str(ADAPTER), "--kind", "phone", "invoke",
                  "--target", "phone-secret", "--operation", "scene.load"]
        accepted = subprocess.run(
            [*common, "--arguments", json.dumps({
                "url": "overte-e2e://fixture/scene"})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, accepted.returncode, accepted.stdout)
        command = json.loads(json.loads(
            payload_log.read_text(encoding="utf-8").splitlines()[0])["payload"])
        self.assertEqual({"schemaVersion", "commandId", "action"}, set(command))
        self.assertTrue(command["commandId"].startswith("android-scene-reload-"))
        self.assertEqual("reload-scene", command["action"])
        rejected = subprocess.run(
            [*common, "--arguments", json.dumps({
                "url": "https://production.invalid/scene.json"})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, rejected.returncode, rejected.stdout)
        self.assertIn("only the embedded fixture URL", rejected.stdout)

    def test_pico_openxr_opt_in_exposes_and_sequences_common_operations(self):
        state = Path(self.temporary.name) / "state"
        state.mkdir(mode=0o700)
        grants = Path(self.temporary.name) / "grants.jsonl"
        process = Path(self.temporary.name) / "process-state"
        process.write_text("stopped", encoding="utf-8")
        argv_log = Path(self.temporary.name) / "adb-argv.jsonl"
        apk = Path(self.temporary.name) / "fixture.apk"
        apk.write_bytes(b"apk")
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_PICO_OPENXR_STATUS": str(Path(self.temporary.name) / "status.json"),
            "MOCK_PICO_OPENXR_GRANTS": str(grants),
            "MOCK_ANDROID_CONTROL_AVAILABLE": "1",
            "MOCK_ANDROID_CONTROL_STATE": str(
                Path(self.temporary.name) / "pico-control-command.json"),
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })
        discovered = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, discovered.returncode, discovered.stdout)
        capabilities = json.loads(discovered.stdout)[0]["capabilities"]
        self.assertTrue({"input.fly", "input.jump", "input.look", "input.move",
                         "tablet.open", "tablet.close"}
                        .issubset(capabilities))

        common = [sys.executable, str(ADAPTER), "--kind", "pico", "invoke",
                  "--target", "pico-secret"]
        setup_calls = [
            ("app.install", {"path": str(apk)}),
            ("app.launch", {}),
            ("app.process", {}),
            ("app.foreground", {}),
            ("scene.load", {"url": "overte-e2e://fixture/scene"}),
            ("probe.snapshot", {}),
        ]
        for operation, arguments in setup_calls:
            result = subprocess.run(
                [*common, "--operation", operation,
                 "--arguments", json.dumps(arguments)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=self.environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
        calls = [
            ("input.look", {"horizontal": 0.25, "vertical": 0.0}),
            ("input.move", {"direction": "forward", "durationSeconds": 1.5}),
            ("input.jump", {}),
            ("input.fly", {"durationSeconds": 3.0}),
            ("tablet.open", {}),
            ("tablet.close", {}),
        ]
        outputs = []
        for operation, arguments in calls:
            result = subprocess.run(
                [*common, "--operation", operation,
                 "--arguments", json.dumps(arguments)],
                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=self.environment, check=False)
            self.assertEqual(0, result.returncode, result.stdout)
            outputs.append(json.loads(result.stdout))
        committed = [json.loads(line) for line in grants.read_text().splitlines()]
        self.assertEqual([1, 2, 3, 4, 5, 6],
                         [item["sequence"] for item in committed])
        self.assertEqual(1, len({item["sessionNonce"] for item in committed}))
        self.assertEqual(["head-pose", "controller-action", "controller-action",
                          "controller-action", "controller-action", "controller-action"],
                         [item["inputDomain"] for item in outputs])
        self.assertTrue(outputs[0]["viewApplied"])
        self.assertEqual(25.0, outputs[0]["viewYawDegrees"])
        self.assertTrue(outputs[1]["openXrVectorApplied"])
        self.assertEqual(0.0, outputs[1]["openXrLeftThumbstickX"])
        self.assertEqual(0.4, outputs[1]["openXrLeftThumbstickY"])
        self.assertTrue(outputs[2]["openXrBooleanApplied"])
        self.assertTrue(outputs[2]["openXrRightSecondaryApplied"])
        self.assertTrue(outputs[3]["openXrBooleanApplied"])
        self.assertTrue(outputs[3]["openXrRightSecondaryApplied"])
        self.assertTrue(outputs[4]["openXrLeftSecondaryApplied"])
        self.assertTrue(outputs[5]["openXrLeftSecondaryApplied"])
        self.assertNotIn(committed[0]["sessionNonce"], json.dumps(outputs))
        self.assertNotIn("pico-secret", json.dumps(outputs))

        second_launch = subprocess.run(
            [*common, "--operation", "app.launch", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, second_launch.returncode, second_launch.stdout)
        self.assertEqual({"launched": True}, json.loads(second_launch.stdout))

        process.write_text("restarted", encoding="utf-8")
        changed = subprocess.run(
            [*common, "--operation", "scene.load", "--arguments", json.dumps({
                "url": "overte-e2e://fixture/scene"})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, changed.returncode, changed.stdout)
        self.assertIn("identity changed", changed.stdout)

        cleaned = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "cleanup"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        self.assertTrue(commands)
        self.assertTrue(all(command[:2] == ["-P", "5041"] for command in commands))
        payloads = [command[4:] if command[2:3] == ["-s"] else command[2:]
                    for command in commands]
        self.assertEqual(1, sum(command[:4] == ["install", "-r", "-d", "-g"]
                                for command in payloads))
        self.assertEqual(1, sum(command[:4] == ["shell", "am", "start", "-W"]
                                for command in payloads))
        self.assertEqual(1, sum(command[:3] == ["shell", "am", "force-stop"]
                                for command in payloads))
        self.assertFalse(any(command[:2] == ["shell", "settings"]
                             for command in payloads))

    def test_pico_semantic_tablet_bridge_snapshot_and_pointer_activation(self):
        unqualified = self.invoke_phone("tablet.snapshot", {})
        self.assertEqual(2, unqualified.returncode, unqualified.stdout)
        self.assertIn("Pico OpenXR input requires", unqualified.stdout)
        self.assertNotIn("phone-secret", unqualified.stdout)

        observation_path = Path(self.temporary.name) / "tablet-observation.json"
        command_path = Path(self.temporary.name) / "tablet-command.json"
        status_path = Path(self.temporary.name) / "tablet-status.json"
        process_path = Path(self.temporary.name) / "tablet-process.json"
        process_path.write_text("stopped", encoding="utf-8")
        observation = {
            "bridgeVersion": 1,
            "updatedEpochMs": int(time.time() * 1000),
            "snapshot": {
                "contractVersion": 1,
                "schemaVersion": 1,
                "screenId": "tablet.home",
                "ready": True,
                "visibleControlIds": ["app.settings"],
            },
        }
        observation_path.write_text(json.dumps(observation), encoding="utf-8")
        state = Path(self.temporary.name) / "tablet-openxr-state"
        state.mkdir(mode=0o700)
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(process_path),
            "MOCK_ANDROID_CONTROL_AVAILABLE": "1",
            "MOCK_ANDROID_CONTROL_STATE": str(
                Path(self.temporary.name) / "tablet-debug-control.json"),
            "MOCK_PICO_TABLET_OBSERVATION": str(observation_path),
            "MOCK_PICO_TABLET_COMMAND": str(command_path),
            "MOCK_PICO_TABLET_STATUS": str(status_path),
        })
        common = self.prepare_pico_session("semantic-tablet")

        discovered = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, discovered.returncode, discovered.stdout)
        capabilities = set(json.loads(discovered.stdout)[0]["capabilities"])
        self.assertTrue({"tablet.snapshot", "tablet.activate"} <= capabilities)

        snapshot = subprocess.run(
            [*common, "--operation", "tablet.snapshot", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, snapshot.returncode, snapshot.stdout)
        self.assertEqual(observation["snapshot"], json.loads(snapshot.stdout))

        activated = subprocess.run(
            [*common, "--operation", "tablet.activate", "--arguments",
             json.dumps({"contractVersion": 1, "controlId": "app.settings"})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, activated.returncode, activated.stdout)
        self.assertEqual({"performed": True}, json.loads(activated.stdout))
        command = json.loads(command_path.read_text(encoding="utf-8"))
        self.assertEqual("app.settings", command["controlId"])
        self.assertEqual(1, command["contractVersion"])
        self.assertNotIn("pico-secret", activated.stdout)

        observation["snapshot"].pop("ready")
        observation["updatedEpochMs"] = int(time.time() * 1000)
        observation_path.write_text(json.dumps(observation), encoding="utf-8")
        malformed = subprocess.run(
            [*common, "--operation", "tablet.snapshot", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, malformed.returncode, malformed.stdout)
        self.assertIn("snapshot is invalid", malformed.stdout)

        cleaned = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "cleanup"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)

    def test_cleanup_auto_selection_is_pico_only_and_fails_closed(self):
        state = Path(self.temporary.name) / "cleanup-state"
        state.mkdir(mode=0o700)
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
            "ANDROID_ADB_SERVER_PORT": "5041",
            "OVERTE_PICO_OPENXR_STATE_DIR": str(state),
            "MOCK_ANDROID_PROCESS_STATE": str(Path(self.temporary.name) / "stopped-process"),
            "MOCK_PICO_DEVICE_COUNT": "2",
        })
        Path(self.environment["MOCK_ANDROID_PROCESS_STATE"]).write_text(
            "stopped", encoding="utf-8")
        ambiguous = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "cleanup"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, ambiguous.returncode, ambiguous.stdout)
        self.assertIn("exactly one eligible target", ambiguous.stdout)
        self.assertNotIn("pico-secret", ambiguous.stdout)

        phone = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "phone", "cleanup"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, phone.returncode, phone.stdout)
        self.assertIn("cleanup requires --target", phone.stdout)

    def test_cleanup_force_stops_and_confirms_process_exit(self):
        process = Path(self.temporary.name) / "cleanup-process"
        process.write_text("running", encoding="utf-8")
        argv_log = Path(self.temporary.name) / "cleanup-adb.jsonl"
        self.environment.update({
            "MOCK_ANDROID_PROCESS_STATE": str(process),
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })

        cleaned = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "phone", "cleanup",
             "--target", "phone-secret"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=self.environment, check=False)

        self.assertEqual(0, cleaned.returncode, cleaned.stdout)
        self.assertEqual("stopped", process.read_text(encoding="utf-8"))
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        force_stop = [index for index, command in enumerate(commands)
                      if command[2:] == ["shell", "am", "force-stop",
                                         "org.overte.phone"]]
        stopped_probe = [index for index, command in enumerate(commands)
                         if command[2:] == ["shell", "pidof", "-s",
                                            "org.overte.phone"]]
        self.assertEqual(1, len(force_stop))
        self.assertTrue(stopped_probe)
        self.assertGreater(stopped_probe[-1], force_stop[0])

    def test_phone_ignores_pico_server_port_without_openxr_opt_in(self):
        argv_log = Path(self.temporary.name) / "phone-adb-argv.jsonl"
        self.environment.update({
            "ANDROID_ADB_SERVER_PORT": "5041",
            "MOCK_ADB_ARGV_LOG": str(argv_log),
        })
        result = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "phone", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        self.assertTrue(commands)
        self.assertTrue(all(command[:1] != ["-P"] for command in commands))

    def test_pico_probe_polls_from_stale_to_newer_sequence(self):
        common = self.prepare_pico_session("advancing-probe")
        sequence = Path(self.temporary.name) / "advancing-probe-sequence"
        argv_log = Path(self.temporary.name) / "advancing-probe-adb.jsonl"
        self.environment.update({
            "MOCK_PROBE_SEQUENCE_STATE": str(sequence),
            "MOCK_PROBE_STALE_READS": "2",
            "MOCK_ADB_ARGV_LOG": str(argv_log),
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "5",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        })
        result = subprocess.run(
            [*common, "--operation", "probe.snapshot", "--arguments",
             json.dumps({"afterSampleSequence": 3})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, result.returncode, result.stdout)
        self.assertEqual(4, json.loads(result.stdout)["sampleSequence"])
        self.assertEqual("4", sequence.read_text(encoding="utf-8"))
        commands = [json.loads(line) for line in argv_log.read_text().splitlines()]
        self.assertFalse(any("getprop" in command for command in commands))
        self.assertFalse(any("pidof" in command for command in commands), commands)
        cleaned = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "cleanup",
             "--target", "pico-secret"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=self.environment, check=False)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)

    def test_pico_probe_fails_closed_when_snapshot_never_becomes_fresh(self):
        common = self.prepare_pico_session("stalled-probe")
        sequence = Path(self.temporary.name) / "stalled-probe-sequence"
        self.environment.update({
            "MOCK_PROBE_SEQUENCE_STATE": str(sequence),
            "MOCK_PROBE_STALE_READS": "999",
            "OVERTE_ANDROID_E2E_PROBE_ATTEMPTS": "3",
            "OVERTE_ANDROID_E2E_PROBE_POLL_SECONDS": "0.01",
        })
        result = subprocess.run(
            [*common, "--operation", "probe.snapshot", "--arguments", "{}"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("unavailable, stale, or did not advance", result.stdout)
        self.assertNotIn("pico-secret", result.stdout)
        self.assertEqual("3", sequence.read_text(encoding="utf-8"))
        cleaned = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "cleanup",
             "--target", "pico-secret"], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, env=self.environment, check=False)
        self.assertEqual(0, cleaned.returncode, cleaned.stdout)

    def test_pico_openxr_opt_in_fails_closed_without_isolated_adb(self):
        self.environment.update({
            "OVERTE_ANDROID_E2E_DEBUG": "1",
            "OVERTE_PICO_OPENXR_INPUT": "1",
        })
        self.environment.pop("ANDROID_ADB_SERVER_PORT", None)
        result = subprocess.run(
            [sys.executable, str(ADAPTER), "--kind", "pico", "discover"],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(2, result.returncode, result.stdout)
        self.assertIn("isolated ADB server", result.stdout)


if __name__ == "__main__":
    unittest.main()
