#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly audio_client="$repo_root/libraries/audio-client/src/AudioClient.cpp"

python3 - "$audio_client" <<'PY'
import pathlib
import re
import sys

source = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
match = re.search(
    r"void AudioClient::processMicAudioInput\(QByteArray& inputByteArray\) \{"
    r"(?P<body>.*?)"
    r"\n\}\n\nvoid AudioClient::handleDummyAudioInput",
    source,
    re.DOTALL,
)
if match is None:
    raise SystemExit("FAIL: processMicAudioInput implementation was not found")

body = match.group("body")
mute_guard = re.search(
    r"if \(!_isMuted\) \{(?P<live>.*?)\} else \{(?P<muted>.*?)\}",
    body,
    re.DOTALL,
)
if mute_guard is None:
    raise SystemExit("FAIL: muted microphone frames have no explicit fallback")
if "possibleResampling" not in mute_guard.group("live"):
    raise SystemExit("FAIL: live microphone frames no longer use the resampler")
if not re.search(
    r"memset\(networkAudioSamples,\s*0,\s*numNetworkBytes\)",
    mute_guard.group("muted"),
):
    raise SystemExit("FAIL: muted microphone frames can reuse previous network samples")

zero_position = body.find("memset(networkAudioSamples, 0, numNetworkBytes)")
send_position = body.find("handleAudioInput(audioBuffer)")
if zero_position < 0 or send_position < 0 or zero_position > send_position:
    raise SystemExit("FAIL: muted samples are not cleared before packet handling")

print("PASS: muted microphone frames clear the complete network buffer before packet handling")
PY

printf 'Android phone audio mute privacy checks passed.\n'
