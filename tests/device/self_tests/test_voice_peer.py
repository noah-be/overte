"""PCM evidence and ownership regressions for the PC voice-test partner."""

from __future__ import annotations

import array
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

PEER = Path(__file__).resolve().parents[1] / "voice_peer"
sys.path.insert(0, str(PEER.parent))
from voice_peer import runtime, voice_signal as dsp

CHALLENGE = "0123456789abcdef0123456789abcdef"
OTHER = "abcdef0123456789abcdef0123456789"


class VoiceSignalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="overte-pc-voice-test-")
        self.root = Path(self.temporary.name)
        self.wav = self.root / "capture.wav"
        self.addCleanup(self.temporary.cleanup)

    def write(self, data, rate=24000, channels=1):
        pcm = array.array("h", data)
        if sys.byteorder != "little":
            pcm.byteswap()
        with wave.open(str(self.wav), "wb") as output:
            output.setparams((channels, 2, rate, 0, "NONE", "not compressed"))
            output.writeframes(pcm.tobytes())

    def test_real_challenge_at_voice_and_os_sample_rates(self):
        for rate in (8000, 24000, 44100, 48000):
            with self.subTest(rate=rate):
                self.write(dsp.samples(CHALLENGE, rate), rate)
                result = dsp.analyze(self.wav, CHALLENGE)
                self.assertTrue(result["passed"], result)
                self.assertTrue(result["patternDetected"])

    def test_delayed_attenuated_noisy_signal(self):
        rng = random.Random(12)
        signal = dsp.samples(CHALLENGE, amplitude=0.025)
        pcm = [0] * 19200 + [max(-32768, min(32767, value + rng.randrange(-80, 81))) for value in signal]
        self.write(pcm)
        result = dsp.analyze(self.wav, CHALLENGE)
        self.assertTrue(result["passed"], result)
        self.assertAlmostEqual(result["firstToneOffsetSeconds"], 1.3, delta=0.08)

    def test_wrong_challenge_and_reversed_sequence_fail(self):
        self.write(dsp.samples(OTHER))
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])
        self.write(reversed(dsp.samples(CHALLENGE)))
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])

    def test_silence_requires_a_complete_capture(self):
        self.write([0] * round(dsp.DURATION * 24000))
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])
        self.assertTrue(dsp.analyze(self.wav, CHALLENGE, "absent")["passed"])
        self.write([0] * 24000)
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE, "absent")["passed"])

    def test_constant_tone_and_broadband_noise_do_not_count(self):
        signal = dsp.samples(CHALLENGE)
        start = round(dsp.LEAD * 24000)
        tone = signal[start:start + round(dsp.TONE * 24000)]
        self.write((tone * (len(signal) // len(tone) + 1))[:len(signal)])
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])
        rng = random.Random(42)
        self.write([rng.randrange(-4000, 4001) for _ in signal])
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE, "absent")["passed"])

    def test_inverted_stereo_is_detected_without_downmix_cancellation(self):
        signal = dsp.samples(CHALLENGE)
        self.write([value for sample in signal for value in (sample, -sample)], channels=2)
        result = dsp.analyze(self.wav, CHALLENGE)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["channelCount"], 2)

    def test_missing_symbol_and_cropped_tail_fail(self):
        signal = dsp.samples(CHALLENGE)
        start = round((dsp.LEAD + 5 * dsp.CELL) * 24000)
        signal[start:start + round(dsp.TONE * 24000)] = array.array("h", [0]) * round(dsp.TONE * 24000)
        self.write(signal)
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])
        self.write(dsp.samples(CHALLENGE)[:-24000])
        self.assertFalse(dsp.analyze(self.wav, CHALLENGE)["passed"])

    def test_truncated_pcm_payload_is_rejected(self):
        dsp.write_wav(self.wav, CHALLENGE)
        self.wav.write_bytes(self.wav.read_bytes()[:-2])
        with self.assertRaisesRegex(ValueError, "truncated"):
            dsp.analyze(self.wav, CHALLENGE)

    def test_cli_return_codes_and_no_overwrite(self):
        cli = [sys.executable, str(PEER / "voice_peer.py")]
        result = subprocess.run(cli + ["challenge", "--challenge", CHALLENGE,
                                      "--output", str(self.wav)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["challenge"], CHALLENGE)
        original = self.wav.read_bytes()
        result = subprocess.run(cli + ["challenge", "--output", str(self.wav)], capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.wav.read_bytes(), original)
        result = subprocess.run(cli + ["analyze", "--challenge", OTHER, "--wav", str(self.wav)], capture_output=True)
        self.assertEqual(result.returncode, 1)


class AudioOwnershipTests(unittest.TestCase):
    def test_domain_comparison_normalizes_uuid_without_exporting_it(self):
        peer = runtime.Peer(Path("unused"), Path("unused"), "hifi://test", {})
        identity = "01234567-89ab-cdef-0123-456789abcdef"
        peer.snapshot = {"domainId": "{" + identity + "}"}
        with patch.object(peer, "ready", return_value={}):
            observed = peer.run({"action": "domain-check", "domainId": identity})
            self.assertEqual(observed, {"schemaVersion": 1, "sameDomain": True})
            self.assertNotIn(identity, json.dumps(observed))
            self.assertEqual(peer.run({"action": "domain-check", "domainId": "00000000-0000-0000-0000-000000000000"})["sameDomain"], False)
        self.assertNotIn("domainId", peer.status()["client"])

    def test_module_inventory_skips_pipewire_builtins_without_handles(self):
        inventory = ("\tlibpipewire-module-protocol-native\t{}\n"
                     "123\tmodule-null-sink\tsink_name=overte_voice_test_tx rate=24000\t\n")
        with patch.object(runtime, "command", return_value=inventory):
            self.assertEqual(runtime.pulse_modules(), [
                {"index": 123, "name": "module-null-sink",
                 "argument": "sink_name=overte_voice_test_tx rate=24000"}])

    def test_routes_only_owned_pid_and_preserves_other_applications(self):
        routes = runtime.AudioRoutes("test")
        routes.ids = {"tx": 10, "rx": 20}
        routes.sources = {"tx": 11, "rx": 21}
        streams = [{"index": 1, "source": 0, "sink": 0,
                    "properties": {"application.process.id": "100"}},
                   {"index": 2, "source": 0, "sink": 0,
                    "properties": {"application.process.id": "200"}}]
        with patch.object(runtime, "pulse_list", return_value=streams), patch.object(runtime, "command") as execute:
            self.assertEqual(routes.route_client(100), {"input": 1, "output": 1})
        self.assertEqual([call.args[0][2] for call in execute.call_args_list], ["1", "1"])

    def test_wrong_route_or_missing_stream_cannot_be_ready(self):
        routes = runtime.AudioRoutes("test")
        routes.ids = {"tx": 10, "rx": 20}
        routes.sources = {"tx": 11, "rx": 21}
        for streams in ([], [{"source": 999, "properties": {"application.process.id": "100"}}]):
            with patch.object(runtime, "pulse_list", return_value=streams):
                with self.assertRaises(runtime.InfrastructureError):
                    routes.verify_client(100)

    def test_cleanup_does_not_unload_a_reused_module_id(self):
        routes = runtime.AudioRoutes("test")
        routes.modules = [(1, "overte_voice_test_tx"), (2, "overte_voice_test_rx")]
        modules = [{"index": 1, "name": "module-null-sink", "argument": "sink_name=somebody_else"},
                   {"index": 2, "name": "module-null-sink", "argument": "sink_name=overte_voice_test_rx rate=24000"}]
        with patch.object(runtime, "pulse_modules", return_value=modules), patch.object(runtime, "command") as execute:
            routes.close()
        execute.assert_called_once_with(["pactl", "unload-module", "2"])

    def test_stale_snapshots_are_rejected(self):
        peer = runtime.Peer(Path("unused"), Path("unused"), "hifi://test", {})
        snapshot = {"session": peer.session, "sequence": 1, "muted": True, "mixerReady": False}
        peer.observe(snapshot)
        with self.assertRaisesRegex(ValueError, "stale"):
            peer.observe(snapshot)
        with self.assertRaisesRegex(ValueError, "invalid"):
            peer.observe(dict(snapshot, session="wrong", sequence=2))


if __name__ == "__main__":
    unittest.main()
