#!/usr/bin/env python3
"""Compile actual preview/callback bodies with Qt and explicit audio OS boundaries."""
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
requested = os.environ.get("OVERTE_VOICE_TEST_QT_CORE")
if requested and requested not in ("Qt5Core", "Qt6Core"):
    raise SystemExit("OVERTE_VOICE_TEST_QT_CORE must be Qt5Core or Qt6Core")
modules = (requested,) if requested else ("Qt6Core", "Qt5Core")
module = next((name for name in modules if subprocess.run(
    ["pkg-config", "--exists", name], check=False).returncode == 0), None)
if module is None:
    raise SystemExit("Install Qt Core development files to run the native voice-preview host contract")
flags = shlex.split(subprocess.check_output(["pkg-config", "--cflags", "--libs", module], text=True))
source = (ROOT / "libraries/audio-client/src/AudioClient.cpp").read_text()
header = (ROOT / "libraries/audio-client/src/AudioClient.h").read_text()
names = ("recordedVoiceTestInputAvailable", "publishRecordedVoiceTestStatus", "finishRecordedVoiceTest",
         "cancelRecordedVoiceTest", "setLocalEcho", "startRecordedVoiceTest", "handleLocalEchoAndReverb")
methods = []
for name in names:
    match = re.search(r"^(?:void|bool) AudioClient::" + name + r"\([^\n]*\)(?: const)? \{.*?^\}",
                      source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise SystemExit(f"Production method missing: {name}")
    methods.append(match.group())
state = header[header.index("    PhoneVoiceTestBuffer _recordedVoiceTest;"):
               header.index("    AudioRingBuffer _inputRingBuffer")]
template = Path(__file__).with_name("recorded-voice-native-fixture.cpp").read_text()
fixture = template.replace("@STATE@", state).replace("@METHODS@", "\n\n".join(methods))
scripting_source = (ROOT / "libraries/audio/src/AudioScriptingInterface.cpp").read_text()
scripting_methods = []
for name in ("setLocalAudioInterface", "startRecordedVoiceTest", "cancelRecordedVoiceTest",
             "getRecordedVoiceTestStatus", "updateRecordedVoiceTestStatus"):
    match = re.search(r"^(?:void|QVariantMap) AudioScriptingInterface::" + name +
                      r"\([^\n]*\)(?: const)? \{.*?^\}", scripting_source, re.MULTILINE | re.DOTALL)
    if match is None:
        raise SystemExit(f"Production scripting method missing: {name}")
    scripting_methods.append(match.group())
fixture = fixture.replace("@SCRIPTING@", "\n\n".join(scripting_methods))
qt_tools = Path(subprocess.check_output(
    ["pkg-config", "--variable=" + ("libexecdir" if module == "Qt6Core" else "host_bins"), module],
    text=True).strip())
if not (qt_tools / "moc").is_file() and os.environ.get("PKG_CONFIG_SYSROOT_DIR"):
    qt_tools = Path(os.environ["PKG_CONFIG_SYSROOT_DIR"]) / str(qt_tools).lstrip("/")
moc = qt_tools / "moc"
if not moc.is_file():
    moc = Path(shutil.which("moc") or "")
if not moc.is_file():
    raise SystemExit("Install matching Qt moc for the recorded voice-test API host contract")
with tempfile.TemporaryDirectory(prefix="overte-recorded-voice-") as scratch:
    cpp = Path(scratch) / "voice.cpp"
    cpp.write_text(fixture)
    subprocess.run([str(moc), str(cpp), "-o", str(Path(scratch) / "voice.moc")], check=True, timeout=30)
    for define in (None, "ANDROID_APP_PHONE_INTERFACE", "ANDROID_APP_PICO_INTERFACE"):
        binary = Path(scratch) / (define or "other-client")
        subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-fPIC", "-pthread",
                        "-I", str(ROOT), *(["-D" + define] if define else []), str(cpp), "-o", str(binary),
                        *flags], check=True, timeout=90)
        subprocess.run([str(binary)], check=True, timeout=15)
        print(f"Native voice-preview callback contract passed: {define or 'other-client'} ({module})")
