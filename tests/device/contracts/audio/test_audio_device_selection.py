#!/usr/bin/env python3
"""Execute device-selection handlers against lifecycle and saved-setting events."""
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).parents[1] / "lifecycle"))
from test_login_dialog_domain_receiver import block


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = (ROOT / "interface/src/scripting/AudioDevices.cpp").read_text()
        methods = block(source, "static QString getTargetDevice(") + "\n" + block(
            source, "void AudioDevices::onDeviceChanged(")
        fixture = r'''
#include <QString>
#include <cassert>
enum class HifiAudioDeviceMode { Input, Output };
namespace QAudio {
    using Mode = HifiAudioDeviceMode;
    constexpr auto AudioInput = HifiAudioDeviceMode::Input;
    constexpr auto AudioOutput = HifiAudioDeviceMode::Output;
}
struct Device { int id; bool isNull() const { return id == 0; } };
struct HifiAudioDeviceInfo {
    int id { 0 };
    inline static const QString DEFAULT_DEVICE_NAME = "default ";
    Device getDevice() const { return {id}; }
    bool operator==(const HifiAudioDeviceInfo& other) const { return id == other.id; }
};
struct Setting {
    bool set { false }; QString value;
    bool isSet() const { return set; }
    QString get() const { return value; }
} inputSetting, outputSetting;
Setting& getSetting(bool, HifiAudioDeviceMode mode) {
    return mode == HifiAudioDeviceMode::Input ? inputSetting : outputSetting;
}
struct List {
    HifiAudioDeviceInfo _selectedHMDDevice, _selectedDesktopDevice;
    void onDeviceChanged(const HifiAudioDeviceInfo& device, bool hmd) {
        (hmd ? _selectedHMDDevice : _selectedDesktopDevice) = device;
    }
};
struct AudioDevices {
    bool _contextIsHMD { false }; int selections { 0 };
    HifiAudioDeviceInfo _requestedInputDevice, _requestedOutputDevice;
    List _inputs, _outputs;
    void onDeviceChanged(HifiAudioDeviceMode, const HifiAudioDeviceInfo&);
    void onDeviceSelected(HifiAudioDeviceMode mode, const HifiAudioDeviceInfo& device,
                          const HifiAudioDeviceInfo&, bool) {
        ++selections;
        auto& setting = getSetting(false, mode);
        setting.set = true;
        setting.value = device.getDevice().isNull() ? "" : "selected-device";
    }
};
METHODS
int main(int argc, char** argv) {
    assert(argc == 2);
    if (QString(argv[1]) == "settings") {
        assert(getTargetDevice(false, HifiAudioDeviceMode::Input) == "default ");
        inputSetting.set = true;
        for (const auto& blank : {QString(), QString(""), QString("  ")}) {
            inputSetting.value = blank;
            assert(getTargetDevice(false, HifiAudioDeviceMode::Input) == "default ");
            assert(inputSetting.value == blank); // reading does not overwrite preferences
        }
        inputSetting.value = "chosen-microphone";
        assert(getTargetDevice(false, HifiAudioDeviceMode::Input) == inputSetting.value);
        outputSetting.set = true; outputSetting.value = "";
        assert(getTargetDevice(false, HifiAudioDeviceMode::Output) == "default ");
    } else {
        AudioDevices devices;
        inputSetting = {true, "chosen-microphone"};
        outputSetting = {true, "chosen-speaker"};
        devices.onDeviceChanged(HifiAudioDeviceMode::Input, {});
        devices.onDeviceChanged(HifiAudioDeviceMode::Output, {});
        assert(devices.selections == 0);
        assert(inputSetting.value == "chosen-microphone");
        assert(outputSetting.value == "chosen-speaker");
        devices._requestedInputDevice = {1};
        devices.onDeviceChanged(HifiAudioDeviceMode::Input, {1});
        assert(devices.selections == 1 && inputSetting.value == "selected-device");
        assert(devices._requestedInputDevice.getDevice().isNull());
        devices.onDeviceChanged(HifiAudioDeviceMode::Input, {});
        assert(devices.selections == 1 && inputSetting.value == "selected-device");
        devices._requestedOutputDevice = {2};
        devices.onDeviceChanged(HifiAudioDeviceMode::Output, {2});
        assert(devices.selections == 2 && outputSetting.value == "selected-device");
        devices.onDeviceChanged(HifiAudioDeviceMode::Output, {});
        assert(devices.selections == 2 && outputSetting.value == "selected-device");
    }
}
'''.replace("METHODS", methods)
        cls.private = tempfile.TemporaryDirectory(prefix="overte-audio-selection-")
        cls.directory = Path(cls.private.name)
        source_path = cls.directory / "selection.cpp"
        source_path.write_text(fixture)
        flags = shlex.split(subprocess.check_output(
            ["pkg-config", "--cflags", "--libs", "Qt6Core"], text=True))
        cls.binary = cls.directory / "selection"
        subprocess.run(["c++", "-std=c++17", "-fPIC", str(source_path),
                        "-o", str(cls.binary), *flags], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.private.cleanup()

    def test_empty_saved_selection_uses_default(self):
        subprocess.run([str(self.binary), "settings"], check=True, timeout=5)

    def test_lifecycle_teardown_preserves_selection(self):
        subprocess.run([str(self.binary), "notifications"], check=True, timeout=5)


if __name__ == "__main__":
    unittest.main()
