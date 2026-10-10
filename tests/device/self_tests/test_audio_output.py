"""Execute the internal output workflow and reject invalid physical evidence."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import array
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ios.audio_output import AudioOutputError, evaluate
from ios import audio_output
from voice_peer.voice_signal import samples

RUN = {"id": "output-fixture", "challenges": ["a" * 32, "b" * 32, "c" * 32], "permission": 1}


class OutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import wave
        cls.document = {"schemaVersion": 1, "runId": RUN["id"], "ok": True,
                        "buildVersion": "fixture", "foregroundContinuous": True, "cleanup": {"restored": True}, "captures": []}
        for index, phase in enumerate(("quiet-control", "local-playback-1", "local-playback-2", "local-playback-3")):
            pcm = array.array("h", [0]) * (24000 * 8)
            if index:
                signal = samples(RUN["challenges"][index - 1])
                pcm[19200:19200 + len(signal)] = signal
            if sys.byteorder != "little":
                pcm.byteswap()
            content = io.BytesIO()
            with wave.open(content, "wb") as output:
                output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(pcm.tobytes())
            data = content.getvalue()
            muted = index == 2
            cls.document["captures"].append({
                "ok": True, "phase": phase, "challenge": RUN["challenges"][max(0, index - 1)],
                "wavBase64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest(),
                "status": {"iosPermission": 1, "iosOutcome": 3 if muted else 2, "nativeMuted": muted,
                           "iosCaptureAllowed": not muted, "inputPresent": not muted,
                           "inputState": 0, "inputError": 0, "physicalDevice": True,
                           "builtInSpeaker": True, "iosForeground": True, "sourceEnabled": False,
                           "sourceClockActive": False, "iosInterrupted": False, "prepared": False,
                           "measurementMode": False, "outputVolume": 0}})

        cls.document["voiceTransitions"] = [
            {"phase": phase, "status": copy.deepcopy(cls.document["captures"][index]["status"])}
            for index, phase in ((1, "unmuted"), (2, "muted"), (3, "unmuted-again"))]
        for capture in cls.document["captures"]:
            capture["status"] = copy.deepcopy(cls.document["voiceTransitions"][1]["status"])

    def evaluate(self, document, run=RUN):
        with tempfile.TemporaryDirectory() as private:
            return evaluate(document, run, Path(private))

    def test_zero_volume_local_output_continues_when_microphone_muted(self):
        result = self.evaluate(self.document)
        self.assertTrue(result["passed"])
        self.assertEqual([m["phase"] for m in result["measurements"]],
                         ["quiet-control", "local-playback-1", "local-playback-2", "local-playback-3"])
        self.assertTrue(result["measurements"][2]["patternDetected"])
        self.assertNotIn("wavBase64", json.dumps(result))

    def test_denied_microphone_preserves_local_output(self):
        doc = copy.deepcopy(self.document)
        run = {**RUN, "permission": 2}
        for index, capture in enumerate(doc["captures"]):
            capture["status"].update(iosPermission=2, iosOutcome=3,
                                     iosCaptureAllowed=False, inputPresent=False)
        for index, transition in enumerate(doc["voiceTransitions"]):
            transition["status"].update(iosPermission=2, iosOutcome=3 if index == 1 else 1,
                                        iosCaptureAllowed=False, inputPresent=False)
        self.assertTrue(self.evaluate(doc, run)["passed"])

    def test_rejects_nonzero_volume_synthetic_input_and_wrong_microphone_state(self):
        for field, value in (("outputVolume", 1), ("sourceEnabled", True), ("sourceClockActive", True),
                             ("iosCaptureAllowed", True), ("physicalDevice", False),
                             ("measurementMode", True), ("iosInterrupted", True)):
            doc = copy.deepcopy(self.document)
            doc["captures"][0]["status"][field] = value
            with self.subTest(field=field), self.assertRaises(AudioOutputError):
                self.evaluate(doc)

    def test_rejects_wrong_nonce_missing_output_and_failed_cleanup(self):
        for kind in ("nonce", "missing-output", "control-playback", "cleanup", "foreground", "input-not-open"):
            doc = copy.deepcopy(self.document)
            if kind == "nonce":
                doc["captures"][1]["challenge"] = "d" * 32
            elif kind == "input-not-open":
                doc["voiceTransitions"][0]["status"]["inputPresent"] = False
            elif kind == "foreground":
                doc["foregroundContinuous"] = False
            elif kind == "cleanup":
                doc["cleanup"]["restored"] = False
            else:
                destination, source = (1, 0) if kind == "missing-output" else (0, 1)
                for key in ("wavBase64", "sha256"):
                    doc["captures"][destination][key] = doc["captures"][source][key]
            with self.subTest(kind=kind), self.assertRaises(AudioOutputError):
                self.evaluate(doc)

    def test_cli_answers_reset_dialog_and_fails_closed_if_normal_relaunch_fails(self):
        for relaunch_failure in (False, True):
            with self.subTest(relaunch_failure=relaunch_failure), tempfile.TemporaryDirectory() as private:
                root = Path(private)
                target = {"platform": "ios", "enabled": True, "appId": "fixture.app",
                          "serverUrl": "http://127.0.0.1:4723",
                          "capabilities": {"appium:udid": "private-fixture-device", "appium:bundleId": "fixture.app"},
                          "testBuild": {"resultsDirectory": "fixture-results"}}
                (root / "targets.json").write_text(json.dumps({"targets": [target]}))
                doc = copy.deepcopy(self.document)
                doc.update(runId="output-" + "f" * 32, startedEpochMs=1000000)
                class Driver:
                    def __init__(self, *_):
                        self.reset = self.answered = self.started = self.expired = self.closed = False
                        self.pid = 1
                    def call(self, method, route, payload=None):
                        if route == "/session":
                            return {"sessionId": "fixture-session"}
                        if method == "DELETE":
                            self.closed = True
                    def execute(self, session, command, fields=None):
                        if command == "mobile: resetPermission":
                            self.reset = True
                        elif command == "mobile: launchApp":
                            if "--testScript" in fields["arguments"]:
                                assert self.reset and self.answered
                                self.started = True
                            elif self.started:
                                assert self.expired
                                if relaunch_failure:
                                    raise RuntimeError("fixture-relaunch-failure")
                            self.pid += 1
                        elif command == "mobile: activeAppInfo":
                            return {"bundleId": "fixture.app", "pid": self.pid}
                client = Driver()
                def permission(driver, session, decision, *, required, timeout):
                    if required:
                        self.assertTrue(driver.reset)
                        self.assertFalse(driver.started)
                        driver.answered = True
                    return required
                def expired(driver, *args):
                    self.assertTrue(driver.started)
                    driver.expired = True
                from contextlib import nullcontext
                # Host tests must never contend for the real installation lock
                # while an authorized physical laboratory run is in progress.
                with patch.object(audio_output.Path, "home", return_value=root), \
                        patch.object(audio_output, "WebDriver", return_value=client), \
                        patch.object(audio_output, "serve_script", return_value=nullcontext("http://fixture/script.js")), \
                        patch.object(audio_output, "handle_permission", side_effect=permission), \
                        patch.object(audio_output, "wait_capture_removal", side_effect=expired), \
                        patch.object(audio_output, "appium_read", return_value=json.dumps(doc)), \
                        patch.object(audio_output.time, "time", return_value=1000), \
                        patch.object(audio_output.secrets, "token_hex", side_effect=["f" * 32, *RUN["challenges"]]):
                    code = audio_output.main(["--target-config", str(root / "targets.json"),
                        "--listen-address", "192.0.2.1", "--output", str(root / "result"),
                        "--source-revision", "1" * 40, "--producer-artifact-sha256", "2" * 64,
                        "--expected-build-version", "fixture", "--reset-microphone",
                        "--lock-file", str(root / "lab.lock")])
                result = json.loads((root / "result/result.json").read_text())
                self.assertEqual(code, int(relaunch_failure))
                self.assertEqual(result["passed"], not relaunch_failure)
                self.assertTrue(result["permissionDialogAnswered"] and result["onDeviceCaptureRemoved"])
                self.assertTrue(client.closed)
                self.assertNotIn("private-fixture-device", json.dumps(result))

    @unittest.skipUnless(shutil.which("node"), "requires Node.js")
    def test_actual_script_permission_order_mute_and_restoration(self):
        script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
function scenario(permission, volume, loseForeground=false) {
 let now=1000,tick,end,saved,active=false,foreground=false,writes=0,local=true,server=true;
 let original={muted:true,pushToTalk:true,avatarGain:-1,serverInjectorGain:-2,localInjectorGain:-3,systemInjectorGain:-4};
 let operations=[],plays=0,timers=[],heartbeats=[];
 const Audio=new Proxy({...original,getLocalEcho:()=>local,getServerEcho:()=>server,
  setLocalEcho:x=>{local=x;writes++},setServerEcho:x=>{server=x;writes++},
  playSound:()=>{assert(Audio.muted);plays++;return {stop:()=>{}}}}, {set:(o,k,v)=>{o[k]=v;writes++;return true}});
 const Test={acousticTest:()=>({ok:true,iosPermission:permission,iosForeground:foreground,
  sourceEnabled:false,sourceClockActive:false,prepared:false,measurementMode:false,physicalDevice:true,
  builtInSpeaker:true,iosInterrupted:false,nativeMuted:Audio.muted,outputVolume:permission===1&&!Audio.muted?0.05:volume,
  iosOutcome:Audio.muted?3:(permission===1?2:1),iosCaptureAllowed:permission===1&&!Audio.muted,
  inputPresent:permission===1&&!Audio.muted,inputState:0,inputError:0}),
  voiceTest:c=>{operations.push(c.action);if(c.action==='capture-start')active=true;
   if(c.action==='capture-stop'){assert(active);active=false;}if(c.action==='reset')active=false;
   return {ok:true,wavBase64:'private-fixture'};},saveObject:(r,name)=>{if(name==='output-playback-result.json')saved=JSON.parse(JSON.stringify(r));else heartbeats.push(JSON.parse(JSON.stringify(r)));}};
 const context={OVERTE_OUTPUT_RUN:{id:'output-fixture',permission,challenges:['a'.repeat(32),'b'.repeat(32),'c'.repeat(32)],urls:['a','b','c']},
  Test,Audio,About:{buildVersion:'fixture'},location:{protocol:'file'},SoundCache:{getSound:()=>({downloaded:true})},
  Date:{now:()=>now},Script:{setInterval:(cb,ms)=>{if(ms===100)tick=cb;else context.heartbeat=cb;return ms},clearInterval:id=>{if(id===100)tick=null},
   setTimeout:(cb,ms)=>{timers.push({cb,ms});return timers.length},clearTimeout:()=>{},
   scriptEnding:{connect:cb=>end=cb},stop:()=>{}}};
 vm.runInNewContext(source,context);
 for(let i=0;i<10;i++){now+=100;tick();}
 assert.equal(writes,0);assert.equal(plays,0);assert.equal(operations.length,0);
 foreground=true;
 for(let i=0;i<700&&tick;i++){now+=100;if(loseForeground&&i===20)foreground=false;context.heartbeat();tick&&tick();}
 assert(saved&&saved.cleanup.restored);assert.equal(saved.ok,volume===0&&!loseForeground);
 assert.deepEqual(Object.fromEntries(Object.keys(original).map(k=>[k,Audio[k]])),original);
 assert(local&&server&&!active);assert(!operations.includes('prepare')&&!operations.includes('send'));
 assert(heartbeats.length>0&&heartbeats.every(h=>h.runId==='output-fixture'&&h.observedEpochMs<=now));
 if(loseForeground){assert.equal(saved.foregroundContinuous,false);assert.equal(saved.error,'output-left-foreground');assert(heartbeats.some(h=>!h.iosForeground));}
 else if(volume===0){assert.equal(plays,3);assert.equal(saved.captures.length,4);
  assert(saved.captures.every(c=>c.status.nativeMuted));
  assert.deepEqual(saved.voiceTransitions.map(t=>t.status.nativeMuted),[false,true,false]);
  if(permission===1)assert.equal(saved.voiceTransitions[0].status.outputVolume,0.05);
  timers.find(x=>x.ms===45000).cb();assert(saved.capturePayloadExpired);
  assert(saved.captures.every(c=>!('wavBase64' in c)));}
 else assert.equal(plays,0);
 end();
}
scenario(1,0);scenario(2,0);scenario(1,1);scenario(1,0,true);
'''
        subprocess.run(["node", "-e", script, str(ROOT / "ios/audio_output.js")], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
