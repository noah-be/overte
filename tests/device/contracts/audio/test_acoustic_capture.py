#!/usr/bin/env python3
"""Execute the bounded production capture and actual audio-thread capture methods."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]


def run():
    source = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text()
    begin = source.index("bool AudioClient::startAcousticCapture(int seconds) {")
    methods = source[begin:source.index("\n#endif\n\nvoid AudioClient::processMicAudioInput", begin)]
    begin = source.index("void AudioClient::processMicAudioInput(QByteArray& inputByteArray) {")
    wiring = source[begin:source.index("    // input samples required", begin)] + "}\n"
    api = (ROOT / "interface/src/scripting/TestScriptingInterface.cpp").read_text()
    begin = api.index("QVariantMap TestScriptingInterface::acousticTest(")
    api = api[begin:api.index("\n#endif\n\nvoid TestScriptingInterface::quit", begin)]
    fixture = Path(__file__).with_name("acoustic-capture-fixture.cpp").read_text()
    fixture = fixture.replace("CAPTURE_METHODS", methods).replace("PHYSICAL_INPUT_WIRING", wiring).replace("ACOUSTIC_API", api)
    flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
    with tempfile.TemporaryDirectory(prefix="overte-acoustic-native-") as private:
        p = Path(private)
        (p / "capture.cpp").write_text(fixture)
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC",
                        "-DOVERTE_E2E_VOICE_TESTS=1", "-I" + str(ROOT / "libraries/audio-client/src"),
                        str(p / "capture.cpp"), "-o", str(p / "capture"), *flags], check=True, timeout=45)
        subprocess.run([str(p / "capture"), "--testScript", "fixture.js"], check=True, timeout=15)
    print("PASS bounded real-input capture, actual input wiring, format/route/lifecycle invalidation and synthetic-input refusal; OS input is a fixture")


if __name__ == "__main__":
    run()
