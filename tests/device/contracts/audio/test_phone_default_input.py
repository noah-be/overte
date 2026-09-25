"""Run the actual AudioClient name-selection entry point against device fixtures."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class DefaultInputTest(unittest.TestCase):
    def test_default_and_explicit_device_selection(self):
        source = (ROOT / 'libraries/audio-client/src/AudioClient.cpp').read_text()
        start = source.index('bool AudioClient::switchAudioDevice(QAudio::Mode mode, const QString&')
        end = source.index('\nvoid AudioClient::configureReverb()', start)
        actual = source[start:end]
        fixture = r'''
#include <QString>
#include <QReadWriteLock>
#include <cassert>
namespace QAudio { enum Mode { AudioInput, AudioOutput }; }
struct HifiAudioDeviceInfo {
    QString name;
    static inline const QString DEFAULT_DEVICE_NAME = "default ";
};
int defaultLookups = 0;
HifiAudioDeviceInfo defaultAudioDeviceForMode(QAudio::Mode, const QString&) {
    ++defaultLookups;
    return {"voicecommunication"};
}
HifiAudioDeviceInfo getNamedAudioDeviceForMode(QAudio::Mode, const QString& name,
                                              const QString&, bool) {
    // Android deviceName() exposes real source names, including default entries.
    if (name == "mic" || name == "voicecommunication" || name == "speaker") return {name};
    return {};
}
struct AudioClient {
    QReadWriteLock _hmdNameLock;
    QString _hmdInputName, _hmdOutputName, selected;
    bool switchAudioDevice(QAudio::Mode, const QString&, bool);
    bool switchAudioDevice(QAudio::Mode, const HifiAudioDeviceInfo& info) {
        selected = info.name;
        return !selected.isEmpty();
    }
};
'''
        main = r'''
int main() {
    AudioClient client;
#ifdef ANDROID_APP_PHONE_INTERFACE
    for (const QString name : {QString("default "), QString("default"), QString(" default "), QString(""), QString("   ")}) {
        assert(client.switchAudioDevice(QAudio::AudioInput, name, false));
        assert(client.selected == "voicecommunication");
    }
    assert(defaultLookups == 5);
#else
    assert(!client.switchAudioDevice(QAudio::AudioInput, "default ", false));
    assert(defaultLookups == 0);
#endif
    assert(client.switchAudioDevice(QAudio::AudioInput, "mic", false));
    assert(client.selected == "mic");
    assert(!client.switchAudioDevice(QAudio::AudioInput, "missing", false));
#ifndef ANDROID_APP_PHONE_INTERFACE
    assert(!client.switchAudioDevice(QAudio::AudioInput, "", false));
#endif
    assert(client.switchAudioDevice(QAudio::AudioOutput, "speaker", false));
    assert(!client.switchAudioDevice(QAudio::AudioOutput, "default ", false));
}
'''
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='phone-default-input-') as directory:
            path = Path(directory)
            (path / 'test.cpp').write_text(fixture + actual + main)
            for target in ('PHONE', 'PICO', 'OTHER'):
                binary = path / target
                defines = [f'-DANDROID_APP_{target}_INTERFACE'] if target != 'OTHER' else []
                subprocess.run(['c++', '-std=c++17', '-fPIC', *defines,
                                str(path / 'test.cpp'), '-o', str(binary), *flags],
                               check=True, timeout=30)
                subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == '__main__':
    unittest.main()
