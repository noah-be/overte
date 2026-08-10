#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../libraries/audio-client/src/AudioClient.cpp"

python3 - "$source_file" <<'PY'
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(
    r"qint64 AudioClient::AudioOutputIODevice::readData\([^}]+?"
    r"Lock deviceLock\(_deviceMutex, std::try_to_lock\);"
    r"(?P<body>.*?)int deviceChannelCount",
    source,
    re.S,
)
if not match:
    raise SystemExit("FAIL: audio callback does not try-lock the device lifetime mutex")
body = match.group("body")
if "!deviceLock.owns_lock()" not in body or "_audioOutputInitialized.load" not in body:
    raise SystemExit("FAIL: audio callback does not fail safely during device switching")
if "memset(data, 0, maxSize);" not in body or "return maxSize;" not in body:
    raise SystemExit("FAIL: unavailable audio device does not return a silence buffer")

switch = re.search(
    r"bool AudioClient::switchOutputToAudioDevice\(.*?\n}\n",
    source,
    re.S,
)
if not switch or "Lock lock(_deviceMutex);" not in switch.group(0):
    raise SystemExit("FAIL: output switching no longer shares the callback lifetime mutex")

print("Phone audio output lifetime race checks passed.")
PY
