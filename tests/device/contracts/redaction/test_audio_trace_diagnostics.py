"""Real Qt execution of original Android AudioClient diagnostic statements only."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]
MARKERS = ('INPUT_REUSED', 'GATE', 'CAPTURE_STARTED', 'CAPTURE_FAILED',
           'CAPTURE_COMPLETE', 'LEVEL', 'INPUT', 'STATE_RESTART', 'WATCHDOG',
           'WATCHDOG_RESTART')


class AudioTraceDiagnostics(unittest.TestCase):
    def test_original_trace_sinks(self):
        baseline = os.environ.get('OVERTE_AUDIO_TRACE_BASELINE')
        path = 'libraries/audio-client/src/AudioClient.cpp'
        source = (subprocess.check_output(['git', '-C', str(ROOT), 'show', baseline + ':' + path], text=True)
                  if baseline else (ROOT / path).read_text())
        calls = re.findall(r'\bq(?:Info|Warning)\(\)\s*<<\s*"PICO_MIC_([^"\n]+)"[^;]*;', source)
        self.assertEqual(sum(marker in MARKERS for marker in calls), 11)
        statements = [m.group(0) for m in re.finditer(
            r'\bq(?:Info|Warning)\(\)\s*<<\s*"PICO_MIC_([^"\n]+)"[^;]*;', source)
            if m.group(1) in MARKERS]
        raw = [call for call in statements if re.search(r'\b(?:deviceName|path|picoMicCapturePath)\b', call)]
        self.assertEqual(raw, [], 'Raw device name or capture path remains in original trace sink')
        self.assertTrue(all(call.count('overte::security::diagnosticEvent(') == 1 for call in statements))
        flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='overte-audio-trace-') as temporary:
            scratch = Path(temporary)
            (scratch / 'trace-sinks.inc').write_text('\n'.join(statements))
            for pico in (False, True):
                binary = scratch / ('pico' if pico else 'android')
                subprocess.run(['c++', '-std=c++17', '-fPIC', '-I', str(ROOT), '-I', str(scratch),
                                *(['-DANDROID_APP_PICO_INTERFACE'] if pico else []),
                                str(Path(__file__).with_name('audio-trace-diagnostics-test.cpp')),
                                '-o', str(binary), *flags], check=True, timeout=30)
                subprocess.run(['unshare', '--user', '--map-root-user', '--net', str(binary)],
                               check=True, timeout=8)


if __name__ == '__main__':
    unittest.main()
