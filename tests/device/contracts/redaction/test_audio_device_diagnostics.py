"""Original AudioClient Qt device-debug expressions, not native audio proof."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class AudioDeviceDiagnostics(unittest.TestCase):
    def test_original_device_debug_sinks_are_closed(self):
        baseline = os.environ.get('OVERTE_AUDIO_DEVICE_DIAGNOSTICS_BASELINE')
        path = 'libraries/audio-client/src/AudioClient.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + path], text=True)
                  if baseline else (ROOT / path).read_text())
        # These statements have no semicolon-bearing string literals. Inspect
        # every active source debug statement, including retained Windows guards.
        calls = re.findall(r'\bqCDebug\(audioclient\)\s*<<[^;]+;', source)
        raw = [call for call in calls if re.search(r'\b(?:deviceName|defDeviceName|szPname)\b', call)]
        self.assertEqual(raw, [], 'Unbounded OS/HMD device names remain in AudioClient debug sinks')
        closed = [call for call in calls if 'overte::security::diagnosticEvent(' in call]
        self.assertEqual(len(closed), 10)
        for call in closed:
            self.assertEqual(call, 'qCDebug(audioclient) << overte::security::diagnosticEvent('
                             'overte::security::DiagnosticEvent::Redacted);')
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-audio-device-diagnostics-') as temporary:
            scratch = Path(temporary)
            (scratch / 'audio-device-sinks.inc').write_text('\n'.join(closed))
            binary = scratch / 'test'
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                            str(Path(__file__).with_name('audio-device-diagnostics-test.cpp')),
                            '-o', str(binary), *flags], check=True, timeout=30)
            subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)], check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
