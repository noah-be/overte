#!/usr/bin/env python3
"""Execute production adapter with a held native queue; no UIKit acceptance."""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--baseline", help="Local commit whose adapter must reject this regression")
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix="overte-ios-permission-") as scratch:
    root = Path(scratch)
    paths = ["ios/audio/IOSAudioAdapter.h", "ios/audio/IOSAudioAdapter.cpp",
             "libraries/audio-client/src/IOSAudioPermission.h",
             "libraries/audio-client/src/IOSAudioPermission.mm",
             "libraries/audio-client/src/AudioLifecycleGate.h"]
    for path in paths + ["ios/tests/audio-permission-request-test.cpp"]:
        destination = root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.baseline and path in paths:
            destination.write_bytes(subprocess.check_output(
                ["git", "show", f"{args.baseline}:{path}"], cwd=ROOT, timeout=10))
        else:
            shutil.copyfile(ROOT / path, destination)
    binary = root / "permission-test"
    subprocess.run(["c++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread",
                    str(root / paths[1]), str(root / "ios/tests/audio-permission-request-test.cpp"),
                    "-x", "c++", str(root / paths[3]), "-o", str(binary)], check=True, timeout=60)
    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
    if args.baseline:
        assert result.returncode != 0 and "native->prompts == 0" in result.stderr, result
        print("EXPECTED_BASELINE_FAILURE: cancelled native request still prompts")
    else:
        assert result.returncode == 0, result.stderr
        # Source guard ties the tested predicate to the actual UIKit queue. This
        # supplements the behavioral test; it does not execute AVFoundation.
        source = (ROOT / "ios/audio/AVAudioSessionAdapter.mm").read_text()
        body = source.split("void requestPermission(", 1)[1].split("\nprivate:", 1)[0]
        assert body.index("dispatch_async(dispatch_get_main_queue()") < body.index("!stillCurrent()")
        assert body.index("!stillCurrent()") < body.index("requestRecordPermission:")
        assert "applicationState != UIApplicationStateActive" in body
        assert "completion(audio::Permission::Unknown);" in body
        print("PASS: cancellation/resume, duplicate/pending/stale callbacks, grant/deny, scheduler failure, destruction")
