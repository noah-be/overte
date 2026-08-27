#!/usr/bin/env python3
"""Mock-ADB contract tests for both concrete Android adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "verify_adapter.py"
ADAPTER = ROOT / "adapters/android/adapter.py"


MOCK_ADB = r'''#!/usr/bin/env python3
import json,os,sys,time
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
probe_sequence_path=os.environ.get("MOCK_PROBE_SEQUENCE_STATE", "")
probe_sequence=int(open(probe_sequence_path).read()) if probe_sequence_path and os.path.exists(probe_sequence_path) else 0
if cmd in (["devices", "-l"], ["devices"]):
    if isolated:
        count=int(os.environ.get("MOCK_PICO_DEVICE_COUNT", "1"))
        print("List of devices attached\n" + "\n".join(
            "pico-secret" + ("" if index == 0 else "-" + str(index + 1)) + " device"
            for index in range(count)))
    else: print("List of devices attached\nphone-secret device model:Phone\npico-secret device model:PICO")
elif cmd == ["get-state"]: print("device")
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
elif cmd[:4] == ["shell", "pidof", "-s", "org.overte.phone"] and process_state != "stopped": print("42")
elif cmd[:4] == ["shell", "pidof", "-s", "org.overte.pico"] and process_state != "stopped": print("44" if process_state == "restarted" else "43")
elif cmd[:3] == ["shell", "cat", "/proc/42/stat"]: print("42 (app) S " + "0 "*18 + "123 0")
elif cmd[:3] == ["shell", "cat", "/proc/43/stat"]: print("43 (app) S " + "0 "*18 + "124 0")
elif cmd[:3] == ["shell", "cat", "/proc/44/stat"]: print("44 (app) S " + "0 "*18 + "125 0")
elif cmd == ["shell", "dumpsys", "activity", "activities"]:
    package="org.overte.pico" if target and target.startswith("pico-secret") else "org.overte.phone"
    print("mResumedActivity: x u0 " + package + "/.Main t1")
elif cmd[:3] == ["shell", "am", "force-stop"]:
    if process_path: open(process_path,"w").write("stopped")
elif cmd[:4] == ["shell", "am", "start", "-W"]:
    if process_path: open(process_path,"w").write("running")
    print("Status: ok")
elif cmd[:3] == ["install", "-r", "-g"]:
    if process_path: open(process_path,"w").write("stopped")
    print("Success")
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
          "leftThumbstickAppliedY":0.4 if is_move else 0.0,
          "booleanAppliedSequence":grant["sequence"] if (is_tablet or is_vertical) else 0,
          "leftSecondaryApplied":is_tablet,"rightSecondaryApplied":is_vertical,
          "activeCommandId":"mock-command","state":"active","detail":"command-window",
          "updatedEpochMs":int(time.time()*1000)}
        if status_path: open(status_path,"w").write(json.dumps(status))
        if grant_log:
            with open(grant_log,"a") as output: output.write(json.dumps(grant)+"\n")
elif cmd and cmd[0] == "exec-out" and "status.json" in cmd[-1]:
    if status_path and os.path.exists(status_path):
        status=json.loads(open(status_path).read())
        if status["state"] == "active" and int(time.time()*1000)-status["updatedEpochMs"] >= 50:
            status["state"]="neutral"; status["detail"]="neutral-window"
            status["updatedEpochMs"]=int(time.time()*1000)
            open(status_path,"w").write(json.dumps(status))
        print(json.dumps(status))
elif cmd and cmd[0] == "exec-out" and "grant.json" in cmd[-1]:
    if status_path and os.path.exists(status_path):
        status=json.loads(open(status_path).read()); status["state"]="neutral"
        status["detail"]="grant-removed"; status["updatedEpochMs"]=int(time.time()*1000)
        open(status_path,"w").write(json.dumps(status))
elif cmd[:4] == ["shell", "run-as", "org.overte.phone", "cat"] or cmd[:4] == ["shell", "run-as", "org.overte.pico", "cat"]:
    probe_sequence += 1
    if probe_sequence_path: open(probe_sequence_path,"w").write(str(probe_sequence))
    stale_reads=int(os.environ.get("MOCK_PROBE_STALE_READS", "0"))
    sampled=1 if probe_sequence <= stale_reads else int(time.time()*1000)
    print(json.dumps({"schemaVersion":1,"sampleEpochMs":sampled,"sampleSequence":probe_sequence,
      "build":{"platform":"Mock","version":"android-contract","date":"1970-01-01"},
      "application":{"running":True,"foreground":True},
      "scene":{"url":"file:///fixture/scene.json","ready":True,"entityCount":4,
               "fixtureMarkerCount":4},
      "avatar":{"position":{"x":0,"y":1,"z":4}},
      "view":{"orientation":{"x":0,"y":0,"z":0}},
      "tablet":{"open":False}}))
else: print("Success")
'''


class AndroidAdapterTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="android-adapter-test-")
        self.adb = Path(self.temporary.name) / "adb"
        self.adb.write_text(MOCK_ADB, encoding="utf-8")
        self.adb.chmod(0o700)
        self.environment = os.environ.copy()
        self.environment["OVERTE_ANDROID_ADB"] = str(self.adb)

    def tearDown(self):
        self.temporary.cleanup()

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

    def test_debug_launcher_accepts_only_the_embedded_fixture_identifier(self):
        self.environment["OVERTE_ANDROID_E2E_DEBUG"] = "1"
        common = [sys.executable, str(ADAPTER), "--kind", "phone", "invoke",
                  "--target", "phone-secret", "--operation", "scene.load"]
        accepted = subprocess.run(
            [*common, "--arguments", json.dumps({
                "url": "overte-e2e://fixture/scene"})],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=self.environment, check=False)
        self.assertEqual(0, accepted.returncode, accepted.stdout)
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
        self.assertEqual(2, second_launch.returncode, second_launch.stdout)
        self.assertIn("single launch", second_launch.stdout)

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
        self.assertEqual(1, sum(command[:3] == ["install", "-r", "-g"]
                                for command in payloads))
        self.assertEqual(1, sum(command[:4] == ["shell", "am", "start", "-W"]
                                for command in payloads))
        self.assertEqual(1, sum(command[:3] == ["shell", "am", "force-stop"]
                                for command in payloads))
        self.assertFalse(any(command[:2] == ["shell", "settings"]
                             for command in payloads))

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
        self.environment.update({
            "MOCK_PROBE_SEQUENCE_STATE": str(sequence),
            "MOCK_PROBE_STALE_READS": "2",
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
