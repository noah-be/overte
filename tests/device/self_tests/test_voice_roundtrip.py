"""Received-PCM assertions, native signal parity, transport and fixture failures."""
from __future__ import annotations

import array
import base64
import hashlib
import importlib.util
import itertools
import json
import os
import shlex
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from voice_contract import command, result, wav
from voice_peer import voice_signal as dsp
from voice_peer.fixture import VoicePeerFixture
from adapters.voice_transport import exchange as transport

os.environ.setdefault("OVERTE_DEVICE_ADAPTER_MANIFEST", str(ROOT / "adapters/mock/adapter.json"))
os.environ.setdefault("OVERTE_DEVICE_TARGET_SELECTOR", "voice-self-test")
os.environ.setdefault("OVERTE_DEVICE_ARTIFACT_DIR", tempfile.gettempdir())
SPEC = importlib.util.spec_from_file_location("voice_roundtrip_module", ROOT / "modules/voice_roundtrip.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
CHALLENGE = "0123456789abcdef0123456789abcdef"


class VoiceContractTests(unittest.TestCase):
    def test_closed_commands_reject_bypass_and_unbounded_capture(self):
        valid = {"schemaVersion": 1, "commandId": "fresh", "action": "send", "challenge": CHALLENGE, "muted": False}
        self.assertEqual(command(valid), valid)
        for changes in ({"muted": 0}, {"challenge": "old"}, {"echo": True}, {"schemaVersion": True}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                command(dict(valid, **changes))
        for seconds in (0, 5, 11, True, 8.0):
            with self.assertRaises(ValueError):
                command({"schemaVersion": 1, "commandId": "fresh", "action": "capture-start", "seconds": seconds})
        for url in ("hifi://hub", "hifi://user:secret@host:40102", "http://host:40102", "hifi://host:99999"):
            with self.assertRaises(ValueError):
                command({"schemaVersion": 1, "commandId": "fresh", "action": "prepare", "domainUrl": url})

    def test_native_diagnostics_reject_unknown_errors_and_invalid_types(self):
        valid = {"schemaVersion": 1, "commandId": "fresh", "ok": True,
                 "sourceClockActive": True, "sourceError": "", "testCallbacks": 480,
                 "iosPermission": 1, "iosOutcome": 3, "inputState": -1, "inputError": -1}
        self.assertEqual(result(valid), valid)
        for fields in ({"sourceClockActive": 1}, {"testCallbacks": -1}, {"testCallbacks": True},
                       {"iosPermission": 4}, {"iosOutcome": 7}, {"inputState": 4},
                       {"sourceError": "arbitrary native message"}, {"sourceError": []}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                result(dict(valid, **fields))

    def test_pcm_digest_and_encoding_are_verified_before_analysis(self):
        data = b"received PCM"
        value = {"schemaVersion": 1, "commandId": "fresh", "ok": True,
                 "wavBase64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest()}
        self.assertEqual(wav(result(value)), data)
        for changes in ({"sha256": "0" * 64}, {"wavBase64": "!"}, {"wavBase64": "A" * (8 * 1024 * 1024)}):
            with self.assertRaises(ValueError):
                result(dict(value, **changes))

    def test_transport_ignores_retained_results_and_checks_process(self):
        value = {"schemaVersion": 1, "commandId": "fresh", "action": "status"}
        reads = iter((json.dumps({"commandId": "old"}), json.dumps({"schemaVersion": 1, "commandId": "fresh", "ok": True, "sampleEpochMs": 100000})))
        checks, sent = [], []
        with patch("adapters.voice_transport.time.time", return_value=100), patch("adapters.voice_transport.time.sleep"):
            observed = transport(value, sent.append, lambda: next(reads), lambda: checks.append(True))
        self.assertEqual(observed["commandId"], "fresh")
        self.assertEqual(sent[0]["request"], value)
        self.assertGreaterEqual(len(checks), 4)
        with self.assertRaisesRegex(RuntimeError, "process changed"):
            transport(value, sent.append, lambda: "{}", lambda: (_ for _ in ()).throw(RuntimeError("process changed")))

    def test_stale_and_malformed_results_cannot_pass(self):
        value = {"schemaVersion": 1, "commandId": "fresh", "action": "status"}
        for fields in ({"sampleEpochMs": 1}, {"sampleEpochMs": 100000, "frames": -1}):
            response = {"schemaVersion": 1, "commandId": "fresh", "ok": True, **fields}
            with patch("adapters.voice_transport.time.time", return_value=100), self.assertRaises((RuntimeError, ValueError)):
                transport(value, lambda _: None, lambda: json.dumps(response), lambda: None)


class AdapterVoiceTests(unittest.TestCase):
    def test_phone_and_pico_use_their_owned_debug_file_transport(self):
        from adapters.android.adapter import AndroidAdapter, PROFILES
        for kind in ("phone", "pico"):
            with self.subTest(kind=kind), patch.dict(os.environ, {"OVERTE_ANDROID_E2E_DEBUG": "1", "OVERTE_E2E_VOICE_TESTS": "1", "OVERTE_PICO_OPENXR_INPUT": "0"}):
                adapter = object.__new__(AndroidAdapter)
                adapter.kind, adapter.profile = kind, PROFILES[kind]
                adapter.require = Mock()
                adapter.require_controlled_debug_identity = Mock(return_value="123:99")
                adapter.require_same_process = Mock()
                response = {}
                def deliver(_target, _identity, _operation, payload):
                    response.update(schemaVersion=1, commandId=payload["commandId"], ok=True, sampleEpochMs=100000)
                adapter.write_control_command = Mock(side_effect=deliver)
                adapter.adb = Mock()
                adapter.adb.read_debug_app_file.side_effect = lambda *_, **__: json.dumps(response)
                value = {"schemaVersion": 1, "commandId": "fresh", "action": "status"}
                with patch("adapters.voice_transport.time.time", return_value=100):
                    observed = adapter.invoke("private-test-target", "voice.exchange", value)
                self.assertTrue(observed["ok"])
                self.assertEqual(adapter.write_control_command.call_args.args[3]["request"], value)
                self.assertEqual(adapter.adb.read_debug_app_file.call_args.args[2], "files/overte-e2e/voice-result.json")

    def test_ios_uses_documents_pcm_and_the_controlled_fixture(self):
        # apple-ios owns a richer Appium implementation; shared branches expose
        # the parent implementation through this same compatibility entrypoint.
        from adapters.appium.adapter import AppiumAdapter
        adapter = object.__new__(AppiumAdapter)
        adapter.platform = "ios"
        target = {"platform": "ios", "appId": "org.example.overte.e2e", "testBuild": {
            "fixtureOrigin": "http://127.0.0.1:18080", "resultsDirectory": "results"},
            "probe": {"kind": "ios-documents"}}
        adapter.target = Mock(return_value=target)
        adapter.ensure_session = Mock(return_value=(Mock(), "session", {}))
        adapter.process_state = Mock(return_value={"running": True, "identity": "123"})
        adapter.assert_ios_process_identity = Mock(return_value="123")
        adapter.query_app_state = Mock(return_value=4)
        value = {"schemaVersion": 1, "commandId": "fresh", "action": "status"}
        response = {"schemaVersion": 1, "commandId": "fresh", "ok": True, "sampleEpochMs": 100000}
        with patch.dict(os.environ, {"OVERTE_E2E_VOICE_TESTS": "1"}), patch("adapters.voice_transport.time.time", return_value=100), patch("adapters.voice_transport.fixture_command") as deliver, patch("adapters.voice_transport.appium_read", return_value=json.dumps(response).encode()) as read:
            self.assertTrue(adapter.invoke("private-test-target", "voice.exchange", value)["ok"])
        self.assertEqual(deliver.call_args.args, ("http://127.0.0.1:18080/e2e-client-command.json", value))
        self.assertEqual(read.call_args.args[2], "@org.example.overte.e2e:documents/results/voice-result.json")
        with patch.dict(os.environ, {"OVERTE_E2E_VOICE_TESTS": "0"}):
            self.assertNotIn("voice.exchange", adapter.advertised_capabilities(target))


class NativeVoiceSignalTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("c++") and shutil.which("pkg-config"), "native clock check requires a C++ compiler and Qt6 pkg-config")
    def test_actual_clock_survives_input_shutdown_and_cancels_on_lifecycle_loss(self):
        subprocess.run([sys.executable, str(ROOT / "contracts/audio/test_voice_clock.py")],
                       check=True, timeout=65)

    @unittest.skipUnless(shutil.which("node"), "probe execution requires Node.js")
    def test_actual_probe_restores_audio_state_and_rejects_release_client(self):
        source = (ROOT / "probe/overte_e2e_probe.js").read_text()
        start = source.index("    var voiceOriginal = null;")
        end = source.index("    function applyClientCommand(command)", start)
        voice = source[start:end]
        script = r'''
const assert = require('assert');
var lastClientCommandId = '';
function objectKeysMatch(value, expected) { return Object.keys(value).sort().join('|') === expected.slice().sort().join('|'); }
var Audio = {muted:false, pushToTalk:true, noiseReduction:true, acousticEchoCancellation:true,
    avatarGain:-2, serverInjectorGain:-3, localInjectorGain:-4, systemInjectorGain:-5,
    getLocalEcho:()=>true, getServerEcho:()=>true,
    setLocalEcho:value=>{Audio.localEcho=value;}, setServerEcho:value=>{Audio.serverEcho=value;}};
var native=[], saved=[];
var Test={voiceTest:request=>{native.push(request);return {schemaVersion:1,commandId:request.commandId,ok:true};},
    saveObject:(value,path)=>{assert.equal(path,'voice-result.json');saved.push(value);}};
var Script={setTimeout:()=>1,clearTimeout:()=>{}};
var location={isConnected:true,domainID:'domain',handleLookupString:value=>{location.url=value;}};
var MyAvatar={position:{x:0,y:2,z:0}};
var About={buildVersion:'installed-version'};
VOICE
function apply(id,action,extra={}) {
    return applyVoice({schemaVersion:1,commandId:id,action:'voice-test',
        request:{schemaVersion:1,commandId:id,action,...extra}});
}
assert(apply('prepare','prepare',{domainUrl:'hifi://fixture:40102'}));
assert.equal(Audio.muted,true);assert.equal(Audio.avatarGain,0);
assert.equal(Audio.localEcho,false);assert.equal(location.url,'hifi://fixture:40102');
var calls=native.length;assert.equal(apply('prepare','prepare'),false);assert.equal(native.length,calls);
apply('muted-send','send',{challenge:'0123456789abcdef0123456789abcdef',muted:true});
assert.equal(Audio.muted,true);assert.equal(native.at(-1).action,'send');
apply('reset','reset');assert.equal(Audio.muted,false);assert.equal(Audio.pushToTalk,true);
assert.equal(Audio.noiseReduction,true);assert.equal(Audio.avatarGain,-2);assert.equal(Audio.localEcho,true);
assert(!saved.at(-1).wavBase64);
delete Test.voiceTest;
apply('release','prepare',{domainUrl:'hifi://fixture:40102'});
assert.equal(saved.at(-1).ok,false);assert.equal(Audio.muted,false);
'''.replace("VOICE", voice)
        subprocess.run(["node", "-e", script], check=True, timeout=5)

    @unittest.skipUnless(shutil.which("c++") and shutil.which("pkg-config"), "native hook check requires a C++ compiler and Qt6 pkg-config")
    def test_actual_qt_hook_compiles_and_bounds_recording_lifecycle(self):
        source = (ROOT.parents[1] / "interface/src/scripting/TestScriptingInterface.cpp").read_text()
        start = source.index("QVariantMap TestScriptingInterface::voiceTest(")
        end = source.index("\n#endif", start)
        method = source[start:end]
        audio_source = (ROOT.parents[1] / "libraries/audio-client/src/AudioClient.cpp").read_text()
        input_start = audio_source.index("void AudioClient::handleAudioInput(QByteArray& audioBuffer) {")
        input_start = audio_source.index("#if defined(OVERTE_E2E_VOICE_TESTS)", input_start)
        input_end = audio_source.index("#endif", input_start)
        input_hook = audio_source[input_start:input_end].split("\n", 1)[1]
        fixture = r'''
#include <QCoreApplication>
#include <QObject>
#include <QThread>
#include <QSharedPointer>
#include <QVariantMap>
#include <QCryptographicHash>
#include <QRegularExpression>
#include <QTimer>
#include <QFile>
#include <QDir>
#include <QTemporaryDir>
#include <functional>
#include <cassert>
#include "VoiceTestSignal.h"
namespace AudioConstants { constexpr int SAMPLE_RATE = 24000; }
class AudioClient : public QObject {
public:
    bool recording = false;
    VoiceTestSignal signal;
    VoiceTestSignal& _voiceTestSignal = signal;
    bool _isStereoInput = false, _isMuted = false;
    bool _voiceTestInputEnabled = false, _voiceTestDelivering = false;
    bool prepared = false;
    bool prepareVoiceTest() {
        if (prepared) { return false; }
        signal.enable(); prepared = true; return true;
    }
    bool sendVoiceTest(const std::array<int, 12>& symbols) {
        if (!prepared || signal.active()) { return false; }
        signal.send(symbols); return true;
    }
    void resetVoiceTest() { signal.reset(); prepared = false; }
    void touchVoiceTest() {}
    QVariantMap voiceTestStatus() const { return {{"sending", signal.active()}, {"frames", signal.frames()}}; }
    void handleAudioInput(QByteArray& audioBuffer) { INPUT_HOOK }
    bool getRecording() { return recording; }
    VoiceTestSignal& voiceTestSignal() { return signal; }
    bool startRecording(const QString& path) {
        QFile file(path); if (!file.open(QIODevice::WriteOnly)) { return false; }
        file.write("received-wav"); recording = true; return true;
    }
    void stopRecording() { recording = false; }
};
struct DependencyManager {
    template<class T> static QSharedPointer<T> get() { static auto pointer = QSharedPointer<T>::create(); return pointer; }
};
class TestScriptingInterface : public QObject {
public:
    QString _testResultsLocation, _voiceCapturePath;
    quint64 _voiceCaptureGeneration = 0;
    QVariantMap voiceTest(const QVariantMap&);
};
METHOD
int main(int argc, char** argv) {
    QCoreApplication application(argc, argv);
    QTemporaryDir directory;
    TestScriptingInterface test;
    QVariantMap command { { "schemaVersion", 1 }, { "commandId", "fresh" }, { "action", "prepare" } };
    assert(!test.voiceTest(command).value("ok").toBool());
    test._testResultsLocation = directory.path();
    assert(test.voiceTest(command).value("ok").toBool());
    command["action"] = "send"; command["challenge"] = "invalid";
    assert(!test.voiceTest(command).value("ok").toBool());
    command["challenge"] = "0123456789abcdef0123456789abcdef";
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!test.voiceTest(command).value("ok").toBool()); // overlapping sender
    command["action"] = "capture-start"; command["seconds"] = 100;
    assert(!test.voiceTest(command).value("ok").toBool());
    command["seconds"] = 8;
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!test.voiceTest(command).value("ok").toBool()); // overlapping capture
    auto path = test._voiceCapturePath;
    command["action"] = "capture-stop";
    auto capture = test.voiceTest(command);
    assert(capture.value("ok").toBool());
    assert(QByteArray::fromBase64(capture.value("wavBase64").toByteArray()) == "received-wav");
    assert(!QFile::exists(path));
    assert(!test.voiceTest(command).value("ok").toBool());
    command["action"] = "reset";
    assert(test.voiceTest(command).value("ok").toBool());
    assert(!DependencyManager::get<AudioClient>()->signal.active());
    command["action"] = "send";
    assert(!test.voiceTest(command).value("ok").toBool()); // send requires an owned clock
    command["action"] = "reset";
    auto audio = DependencyManager::get<AudioClient>();
    audio->signal.send({0,1,2,3,4,5,6,7,0,1,2,3});
    QByteArray pcm(480, '\0');
    for (int i = 0; i < 51; ++i) { audio->handleAudioInput(pcm); }
    assert(pcm != QByteArray(480, '\0'));
    const int before = audio->signal.frames();
    audio->_isMuted = true;
    audio->handleAudioInput(pcm);
    assert(pcm == QByteArray(480, '\0')); // codec-flush input cannot leak synthetic audio
    assert(audio->signal.frames() == before + 240);
    audio->_isMuted = false;
    audio->handleAudioInput(pcm);
    assert(pcm != QByteArray(480, '\0'));
}
'''.replace("METHOD", method).replace("INPUT_HOOK", input_hook)
        flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        with tempfile.TemporaryDirectory() as private:
            root = Path(private)
            (root / "test.cpp").write_text(fixture)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-I" + str(ROOT.parents[1] / "libraries/audio-client/src"), str(root / "test.cpp"), "-o", str(root / "test"), *flags], check=True, timeout=30)
            subprocess.run([str(root / "test"), "--testScript", "probe.js"], check=True, timeout=5)

    @unittest.skipUnless(shutil.which("c++"), "native PCM check requires a C++ compiler")
    def test_actual_cpp_generator_matches_python_reference_and_reset(self):
        with tempfile.TemporaryDirectory() as private:
            root = Path(private)
            source = r'''
#include "VoiceTestSignal.h"
#include <cassert>
#include <cstdio>
#include <vector>
int main() {
    VoiceTestSignal signal;
    int16_t untouched[2] = {123, 456};
    signal.replace(untouched, 1, 2); assert(untouched[0] == 123);
    signal.enable(); signal.replace(untouched, 1, 2); assert(untouched[0] == 0);
    signal.send({ SYMBOLS });
    std::vector<int16_t> pcm(VoiceTestSignal::FRAMES * 2);
    for (int offset = 0; offset < VoiceTestSignal::FRAMES; offset += 240) {
        signal.replace(pcm.data() + offset * 2, 240, 2);
    }
    assert(!signal.active() && signal.frames() == VoiceTestSignal::FRAMES);
    signal.replace(untouched, 1, 2); assert(untouched[0] == 0);
    signal.reset(); untouched[0] = 777; signal.replace(untouched, 1, 2); assert(untouched[0] == 777);
    std::fwrite(pcm.data(), sizeof(int16_t), pcm.size(), stdout);
}
'''.replace("SYMBOLS", ",".join(map(str, dsp.sequence(CHALLENGE))))
            (root / "test.cpp").write_text(source)
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I" + str(ROOT.parents[1] / "libraries/audio-client/src"), str(root / "test.cpp"), "-o", str(root / "test")], check=True, timeout=30)
            completed = subprocess.run([str(root / "test")], capture_output=True, check=True, timeout=5)
            native = array.array("h")
            native.frombytes(completed.stdout)
            expected = dsp.samples(CHALLENGE)
            self.assertEqual(len(native), 2 * len(expected))
            self.assertLessEqual(max(abs(a - b) for a, b in zip(native[::2], expected)), 1)
            self.assertEqual(native[::2], native[1::2])
            path = root / "native.wav"
            with wave.open(str(path), "wb") as output:
                output.setparams((2, 2, 24000, 0, "NONE", "not compressed"))
                output.writeframes(completed.stdout)
            self.assertTrue(dsp.analyze(path, CHALLENGE)["passed"])


class VoiceModuleTests(unittest.TestCase):
    def test_native_clock_failure_is_saved_and_cannot_pass_with_complete_frames(self):
        def response(_, request):
            return {"schemaVersion": 1, "commandId": request["commandId"], "ok": False,
                    "frames": 116160, "sending": False, "sourceError": "voice-source-clock-late",
                    "sourceClockActive": False, "nativeMuted": True, "iosPermission": 1,
                    "routeName": "private-test-route", "wavBase64": "private-audio"}
        with patch.object(MODULE, "contract_operation", side_effect=response), patch.object(MODULE, "write_json") as saved:
            with self.assertRaisesRegex(MODULE.fail.__globals__["AssertionFailure"], "voice-source-clock-late"):
                MODULE.exchange("send", challenge=CHALLENGE, muted=False)
        name, evidence = saved.call_args.args
        self.assertEqual(name, "voice-native-status.json")
        self.assertEqual(evidence["sourceError"], "voice-source-clock-late")
        self.assertNotIn("routeName", evidence)
        self.assertNotIn("wavBase64", evidence)

    def test_cleanup_preserves_a_product_failure_classification(self):
        calls = []
        def exchange(action, **_):
            calls.append(action)
            if action == "status":
                MODULE.fail("observed product failure")
            if action == "reset":
                raise MODULE.InfrastructureError("cleanup channel failed")
            return {"ok": True}
        environment = {"OVERTE_E2E_VOICE_TESTS": "1", "OVERTE_E2E_VOICE_PEER_STATE": "unused",
                       "OVERTE_E2E_DOMAIN_URL": "hifi://fixture:40102", "OVERTE_E2E_DOMAIN_ID": "domain"}
        with patch.dict(os.environ, environment), patch.object(MODULE, "exchange", side_effect=exchange), patch.object(MODULE, "process_identity", return_value="process"), patch.object(MODULE, "assert_process"), patch.object(MODULE, "write_json"), self.assertRaisesRegex(MODULE.fail.__globals__["AssertionFailure"], "observed product failure"):
            MODULE.main()
        self.assertEqual(calls, ["prepare", "status", "reset"])

    def exercise(self, corrupt=False):
        sent = {}
        pending = {}
        observed_ids = []
        event = threading.Event()
        legs = []
        def peer(_state, action, **values):
            if action == "domain-check":
                return {"sameDomain": True}
            if action == "status":
                return {"snapshotFresh": True, "audioRouted": True, "receivingChallenge": pending.get("challenge"),
                        "client": {"connected": True, "mixerReady": True, "domainId": "domain", "localEcho": False, "serverEcho": False}}
            if action in {"send", "send-muted"}:
                sent.update(challenge=values["challenge"], muted=action == "send-muted")
                return {"sent": True, **sent}
            if action == "receive":
                event.clear()
                pending.update(values)
                if not event.wait(5):
                    raise RuntimeError("test device never sent")
                return {"passed": True, "challenge": values["challenge"], "expected": values["expect"]}
            raise AssertionError(action)
        def exchange(action, **values):
            if action == "send":
                observed_ids.append(values["challenge"])
                event.set()
            if action == "status":
                return {"sending": False, "frames": 116160, "version": "device-test-version"}
            if action == "capture-stop":
                with tempfile.TemporaryDirectory() as private:
                    path = Path(private) / "capture.wav"
                    if sent["muted"] or corrupt:
                        with wave.open(str(path), "wb") as output:
                            output.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
                            output.writeframes(b"\0" * 24000 * 2 * 8)
                    else:
                        dsp.write_wav(path, sent["challenge"])
                    data = path.read_bytes()
                observed_ids.append(sent["challenge"])
                return {"wavBase64": base64.b64encode(data).decode(), "sha256": hashlib.sha256(data).hexdigest(), "version": "device-test-version"}
            return {"ok": True, "muted": values.get("muted", True)}
        ticks = itertools.count()
        with patch.object(MODULE, "peer", side_effect=peer), patch.object(MODULE, "exchange", side_effect=exchange), patch.object(MODULE, "assert_process"), patch.object(MODULE, "write_json", side_effect=lambda _, evidence: legs.append(json.loads(json.dumps(evidence)))), patch.object(MODULE.time, "monotonic", side_effect=lambda: next(ticks) * 0.5), patch.object(MODULE.time, "sleep", side_effect=lambda _: event.wait(0.001)):
            evidence = MODULE.run_roundtrip(Path("unused"), "process", "domain")
        return evidence, observed_ids

    def test_all_four_legs_require_received_pcm_and_unique_challenges(self):
        evidence, challenges = self.exercise()
        self.assertEqual(len(evidence["legs"]), 4)
        self.assertEqual(len(set(challenges)), 4)
        self.assertEqual([(leg["direction"], leg["muted"]) for leg in evidence["legs"]],
                         [("pc-to-device", False), ("device-to-pc", False), ("pc-to-device", True), ("device-to-pc", True)])

    def test_acknowledged_send_with_silent_receiver_fails(self):
        with self.assertRaisesRegex(MODULE.fail.__globals__["AssertionFailure"], "received PCM"):
            self.exercise(corrupt=True)

    def test_wrong_domain_and_echo_enabled_are_infrastructure_errors(self):
        for client in ({"domainId": "other"}, {"domainId": "domain", "serverEcho": True}):
            status = {"snapshotFresh": True, "audioRouted": True,
                      "client": {"connected": True, "mixerReady": True, **client}}
            with patch.object(MODULE, "peer", return_value=status), self.assertRaises(MODULE.InfrastructureError):
                MODULE.require_peer(Path("unused"), "domain")


@unittest.skipUnless(sys.platform == "linux", "PC fixture ownership is Linux-only")
class OwnedFixtureTests(unittest.TestCase):
    def test_fixture_stops_its_owned_peer_and_releases_global_audio_lock(self):
        with tempfile.TemporaryDirectory() as private:
            root = Path(private)
            config = root / "launch.json"
            config.write_text("{}")
            config.chmod(0o600)
            processes = []
            def popen(arguments, **_):
                state = Path(arguments[arguments.index("--state-dir") + 1])
                (state / "session.json").write_text("{}")
                process = Mock()
                process.poll.return_value = None
                process.terminate.side_effect = lambda: (state / "session.json").unlink()
                processes.append(process)
                return process
            samples = itertools.count(1)
            ticks = itertools.count()
            def status(*_, **__):
                return {"snapshotFresh": True, "audioRouted": True, "snapshotAgeSeconds": 0.1,
                        "client": {"connected": True, "mixerReady": True, "sequence": next(samples)}}
            with patch.dict(os.environ, {"XDG_STATE_HOME": str(root)}), patch("voice_peer.fixture.invoke", side_effect=status), patch("voice_peer.fixture.subprocess.Popen", side_effect=popen), patch("voice_peer.fixture.time.monotonic", side_effect=lambda: next(ticks) * 0.25), patch("voice_peer.fixture.time.sleep"):
                first = VoicePeerFixture(config, "hifi://localhost:40102")
                environment = first.start()
                second = VoicePeerFixture(config, "hifi://localhost:40102")
                with self.assertRaisesRegex(RuntimeError, "already reserved"):
                    second.start()
                state = Path(environment["OVERTE_E2E_VOICE_PEER_STATE"])
                first.close()
                self.assertFalse(state.exists())
                processes[0].terminate.assert_called_once()
                processes[0].wait.assert_called_once_with(timeout=25)
                third = VoicePeerFixture(config, "hifi://localhost:40102")
                third.start()
                third.close()


if __name__ == "__main__":
    unittest.main()
