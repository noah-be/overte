"""Internal acoustic signal, permission sequencing and cleanup regressions."""
# SPDX-License-Identifier: Apache-2.0
import array
import base64
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ios.acoustic_loopback import AcousticError, evaluate, handle_permission, main, wait_capture_removal
from adapters.appium.adapter import WebDriverRequestError
from voice_peer import voice_signal as dsp

RUN = {"id": "acoustic-fixture", "control": "abcdef0123456789abcdef0123456789",
       "signal": "0123456789abcdef0123456789abcdef"}


class AcousticTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name)

    def capture(self, kind, signal):
        p = self.private / "fixture.wav"
        data = array.array("h", signal)
        if sys.byteorder != "little": data.byteswap()
        with wave.open(str(p), "wb") as source:
            source.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            source.writeframes(data.tobytes())
        data = p.read_bytes()
        return {"ok": True, "kind": kind, "challenge": RUN["control" if kind == "control" else "signal"],
                "captureSource": "physical-device-input-before-processing", "captureComplete": True,
                "physicalDevice": True, "builtInMicrophone": True, "builtInSpeaker": True,
                "measurementMode": True, "iosForeground": True, "iosCaptureAllowed": True,
                "inputPresent": True, "captureInvalid": False, "sourceEnabled": False,
                "sourceClockActive": False, "iosInterrupted": False, "nativeMuted": False,
                "iosPermission": 1, "inputState": 0, "inputError": 0, "physicalInputCallbacks": 800,
                "captureRate": 24000, "captureChannels": 1, "captureBytes": len(signal) * 2,
                "wavBase64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest()}

    def document(self, challenge=RUN["signal"]):
        rng = random.Random(8)
        noise = [rng.randrange(-100, 101) for _ in range(8 * 24000)]
        signal = dsp.samples(challenge, amplitude=0.04)
        # Acoustic delay plus mild noise, with exactly eight seconds of capture.
        received = noise[:]
        for index, value in enumerate(signal): received[19200 + index] += value
        return {"schemaVersion": 1, "runId": RUN["id"], "ok": True, "buildVersion": "fixture-only",
                "cleanup": {"restored": True}, "playbackStarted": True,
                "captures": [self.capture("control", noise), self.capture("playback", received)]}

    def test_delayed_noisy_acoustic_fixture_and_control(self):
        result = evaluate(self.document(), RUN, self.private)
        self.assertTrue(result["passed"])
        self.assertEqual([x["patternDetected"] for x in result["measurements"]], [False, True])
        self.assertNotIn("wavBase64", json.dumps(result))

    def test_other_nonce_cannot_pass(self):
        self.assertFalse(evaluate(self.document(RUN["control"]), RUN, self.private)["passed"])

    def test_tone_in_quiet_control_fails(self):
        document = self.document()
        tone = array.array("h", [0]) * (8 * 24000)
        signal = dsp.samples(RUN["control"])
        tone[:len(signal)] = signal
        document["captures"][0] = self.capture("control", tone)
        self.assertFalse(evaluate(document, RUN, self.private)["passed"])

    def test_synthetic_or_external_or_stale_evidence_is_rejected(self):
        base = self.document()
        for key, value in (("sourceEnabled", True), ("sourceClockActive", True), ("physicalDevice", False),
                           ("builtInSpeaker", False), ("builtInMicrophone", False), ("captureComplete", False),
                           ("physicalInputCallbacks", 0), ("captureInvalid", True), ("inputError", 1),
                           ("challenge", RUN["control"]), ("sha256", "0" * 64)):
            document = deepcopy(base)
            document["captures"][1][key] = value
            with self.subTest(key=key), self.assertRaises((AcousticError, ValueError)):
                evaluate(document, RUN, self.private)
        base["runId"] = "previous-run"
        with self.assertRaises(AcousticError): evaluate(base, RUN, self.private)

    def test_missing_samples_and_failed_cleanup_are_rejected(self):
        doc = self.document()
        doc["captures"][1] = self.capture("playback", [0] * 24000)
        with self.assertRaises(AcousticError): evaluate(doc, RUN, self.private)
        doc = self.document()
        doc["cleanup"]["restored"] = False
        with self.assertRaises(AcousticError): evaluate(doc, RUN, self.private)

    def test_permission_decision_must_close_dialog(self):
        for decision, label, action in (("allow", "Erlauben", "accept"), ("deny", "Nicht erlauben", "dismiss")):
            client = Mock()
            client.call.side_effect = ["Overte möchte auf das Mikrofon zugreifen", WebDriverRequestError(404)]
            client.execute.return_value = ["Nicht erlauben", "Erlauben"]
            self.assertTrue(handle_permission(client, "session", decision, required=True, timeout=1))
            self.assertEqual(client.execute.call_args.args[2], {"action": action, "buttonLabel": label})
        client.call.side_effect = ["Mikrofon", "Mikrofon"]
        with self.assertRaisesRegex(AcousticError, "STILL_OPEN"):
            handle_permission(client, "session", "allow", required=True, timeout=1)
        client = Mock()
        with self.assertRaisesRegex(AcousticError, "MISSING"):
            handle_permission(client, "session", "allow", required=True, timeout=0)
        client.execute.assert_not_called()

    def test_actual_host_runner_answers_reset_dialog_before_script_and_requires_cleanup(self):
        app = "org.example.overte.e2e"
        config = self.private / "target.json"
        config.write_text(json.dumps({"targets": [{"platform": "ios", "appId": app,
            "serverUrl": "http://127.0.0.1:4723", "capabilities": {"appium:udid": "fixture-private-device",
            "appium:bundleId": app}, "testBuild": {"resultsDirectory": "results"}}]}))
        @contextmanager
        def server(*_): yield "http://192.0.2.1:1234/script.js"
        for cleanup in (True, False):
            document = self.document()
            document["cleanup"]["restored"] = cleanup
            document["startedEpochMs"] = time.time() * 1000
            events = []
            class Client:
                pending = False
                armed = False
                answered = False
                def call(inner, method, path, payload=None):
                    if path == "/session":
                        self.assertFalse(payload["capabilities"]["alwaysMatch"]["appium:autoAcceptAlerts"])
                        return {"sessionId": "fixture-session"}
                    if path.endswith("/alert/text"):
                        if inner.pending: return "Overte möchte auf das Mikrofon zugreifen"
                        raise WebDriverRequestError(404)
                    events.append("session-close")
                def execute(inner, session, method, arguments=None):
                    if inner.pending:
                        self.assertEqual(method, "mobile: alert", "other test action before dialog decision")
                    if method == "mobile: alert":
                        if arguments["action"] == "getButtons": return ["Nicht erlauben", "Erlauben"]
                        self.assertEqual(arguments["buttonLabel"], "Erlauben")
                        inner.pending = False; inner.answered = True
                        events.append("permission-answered")
                    elif method == "mobile: activeAppInfo": return {"bundleId": app, "pid": 123}
                    elif method == "mobile: resetPermission":
                        inner.armed = True; events.append("permission-reset")
                    elif method == "mobile: launchApp":
                        if "--testScript" in arguments["arguments"]:
                            self.assertTrue(inner.answered)
                            events.append("test-script-launch")
                        else:
                            events.append("normal-launch")
                            if inner.armed: inner.pending = True; inner.armed = False
            clock = [0.0]
            def monotonic(): clock[0] += 0.6; return clock[0]
            output = self.private / ("run-ok" if cleanup else "run-cleanup-failed")
            expired = deepcopy(document)
            for capture in expired["captures"]:
                capture.pop("wavBase64")
            expired["capturePayloadExpired"] = True
            with patch("ios.acoustic_loopback.serve_script", server), patch("ios.acoustic_loopback.WebDriver", return_value=Client()), \
                 patch("ios.acoustic_loopback.appium_read", side_effect=[json.dumps(document).encode(), json.dumps(expired).encode()]), \
                 patch("ios.acoustic_loopback.secrets.token_hex", side_effect=["fixture", RUN["control"], RUN["signal"]]), \
                 patch("ios.acoustic_loopback.time.sleep"), patch("ios.acoustic_loopback.time.monotonic", monotonic), \
                 patch("ios.acoustic_loopback.fcntl.flock"), patch("ios.acoustic_loopback.Path.home", return_value=self.private):
                rc = main(["--target-config", str(config), "--listen-address", "192.0.2.1", "--output", str(output),
                           "--source-revision", "a" * 40, "--producer-artifact-sha256", "b" * 64,
                           "--expected-build-version", "fixture-only", "--reset-microphone"])
            self.assertEqual(rc, 0 if cleanup else 1)
            self.assertLess(events.index("permission-answered"), events.index("test-script-launch"))
            self.assertEqual(events[-1], "session-close")
            self.assertEqual(events[-2], "normal-launch" if cleanup else "test-script-launch")
            self.assertNotIn("fixture-private-device", (output / "result.json").read_text())

    def test_capture_payload_must_expire_before_host_relaunch(self):
        document = self.document()
        expired = deepcopy(document)
        for capture in expired["captures"]:
            capture.pop("wavBase64")
        wrong_run = deepcopy(expired)
        wrong_run["runId"] = "another-run"
        with patch("ios.acoustic_loopback.appium_read", side_effect=[
                json.dumps(wrong_run), json.dumps(document), json.dumps(expired)]), \
                patch("ios.acoustic_loopback.time.sleep") as sleep:
            wait_capture_removal(Mock(), "session", "remote", RUN["id"])
        self.assertEqual(sleep.call_count, 2)
        with self.assertRaisesRegex(AcousticError, "TRANSFER_CLEANUP_FAILED"):
            wait_capture_removal(Mock(), "session", "remote", RUN["id"], timeout=0)

    @unittest.skipUnless(shutil.which("c++") and shutil.which("pkg-config"), "requires host C++ and Qt6 Core")
    def test_actual_native_capture_and_script_api(self):
        subprocess.run([sys.executable, str(ROOT / "contracts/audio/test_acoustic_capture.py")], check=True, timeout=65)

    @unittest.skipUnless(shutil.which("node"), "requires Node.js")
    def test_actual_script_waits_for_permission_and_restores_on_success_and_failure(self):
        script = r'''
const assert = require('assert'), vm = require('vm'), fs = require('fs');
const source = fs.readFileSync(process.argv[1], 'utf8');
function scenario(failure, recovery) {
 let now=1000, tick, end, recordStart=0, active=false, prepared=false, saved=null, stopped=false;
 let unavailable=false, preparedAt=0;
 let permission=0, foreground=false, revision=1, operations=[], writes=0, local=true, server=true;
 let original={muted:true,pushToTalk:true,noiseReduction:true,acousticEchoCancellation:true,
   avatarGain:-3,serverInjectorGain:-4,localInjectorGain:-5,systemInjectorGain:-6};
 const Audio=new Proxy({...original,getLocalEcho:()=>local,getServerEcho:()=>server,
   setLocalEcho:x=>{writes++;local=x},setServerEcho:x=>{writes++;server=x}},
   {set:(obj,key,value)=>{writes++;obj[key]=value;return true}});
 const state=()=>({ok:true,iosPermission:permission,iosForeground:foreground,iosInterrupted:false,
   iosCaptureAllowed:permission===1 && !Audio.muted,builtInMicrophone:true,builtInSpeaker:true,
   physicalDevice:true,inputPresent:!unavailable,inputState:0,inputError:0,sourceEnabled:false,sourceClockActive:false,
   outputRevision:revision,prepared,measurementMode:prepared,captureInvalid:false,
   physicalInputCallbacks:now-recordStart>400?8:0,captureComplete:active && now-recordStart>=8000});
 const Test={acousticTest:command=>{
   operations.push(command);
   if(command.action==='prepare'){prepared=true;preparedAt=now;revision++}
   if(command.action==='capture-start'){active=true;recordStart=now}
   if(command.action==='play'){
     assert.equal(Audio.systemInjectorGain,0); // non-spatial playback must reach the speaker bus
     assert.equal(Audio.localInjectorGain,-96);
     return {...state(),playing:true};
   }
   if(command.action==='capture-stop'){active=false;return {...state(),captureComplete:true}}
   if(command.action==='reset'){prepared=false;active=false;revision++}
   return state();
 },saveObject:r=>saved=JSON.parse(JSON.stringify(r))};
 const context={OVERTE_ACOUSTIC_RUN:{id:'acoustic-fixture',control:'a'.repeat(32),signal:'b'.repeat(32)},
  About:{buildVersion:'fixture'},Audio,Test,location:{protocol:'file',isConnected:true},
  Date:{now:()=>now},Script:{setInterval:cb=>{tick=cb;return 1},clearInterval:()=>{tick=null},
    setTimeout:()=>2,clearTimeout:()=>{},scriptEnding:{connect:cb=>end=cb},stop:()=>stopped=true}};
 vm.runInNewContext(source,context);
 for(let i=0;i<10;i++){now+=200;tick()}
 assert.equal(writes,0); assert(operations.every(x=>x.action==='status'));
 permission=1;
 for(let i=0;i<10;i++){now+=200;tick()}
 assert.equal(writes,0); // granted callback before dialog/foreground restoration is insufficient
 foreground=true;
 for(let i=0;i<160 && tick;i++){
  now+=200;
  // One transient input loss must restart stability even without a new route revision.
  unavailable=(recovery==='native' && i===3) ||
    (recovery==='measurement' && prepared && now-preparedAt===600);
  if(failure && active && now-recordStart>=1000)permission=2;
  tick();
 }
 assert(saved && saved.cleanup.restored);
 assert.equal(saved.ok,!failure);
 assert.deepEqual(Object.fromEntries(Object.keys(original).map(k=>[k,Audio[k]])),original);
 assert(local && server && !prepared);
 if(!failure){
   assert.equal(operations.filter(x=>x.action==='play').length,1);
   assert.equal(operations.filter(x=>x.action==='capture-start').length,2);
   assert.equal(saved.captures.length,2);
 } else assert.equal(operations.filter(x=>x.action==='play').length,0);
 end(); assert(!prepared); // scriptEnding cleanup remains idempotent
}
scenario(false);scenario(true);scenario(false,'native');scenario(false,'measurement');
'''
        subprocess.run(["node", "-e", script, str(ROOT / "ios/acoustic_loopback.js")], check=True, timeout=15)


if __name__ == "__main__": unittest.main()
