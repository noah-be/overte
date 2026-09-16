"""Exercise the shared bounded voice buffer with the original Phone regression."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


class PhoneVoiceBufferTest(unittest.TestCase):
    def test_capture_playback_isolation_and_bounded_gain(self):
        with tempfile.TemporaryDirectory(prefix="overte-voice-buffer-") as temporary:
            binary = Path(temporary) / "voice-buffer"
            subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                            "-I", str(ROOT), str(Path(__file__).with_name("phone-voice-buffer-test.cpp")),
                            "-o", str(binary)], check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
