#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/check-phone-apk-padding.py"
readonly fixture_dir="$(mktemp -d --tmpdir phone-apk-padding-test.XXXXXX)"
trap 'rm -rf -- "$fixture_dir"' EXIT

python3 - "$fixture_dir" <<'PY'
import pathlib
import struct
import sys
import zipfile

root = pathlib.Path(sys.argv[1])
normal = root / "normal.apk"
with zipfile.ZipFile(normal, "w", zipfile.ZIP_DEFLATED) as archive:
    archive.writestr("first", b"first payload")
    archive.writestr("second", b"second payload")

data = bytearray(normal.read_bytes())
with zipfile.ZipFile(normal) as archive:
    second_offset = archive.getinfo("second").header_offset
    central_offset = archive.start_dir

padding = b"\0" * (128 * 1024)
data[second_offset:second_offset] = padding

central_offset += len(padding)
cursor = central_offset
while data[cursor:cursor + 4] == b"PK\x01\x02":
    name_length, extra_length, comment_length = struct.unpack_from("<HHH", data, cursor + 28)
    local_offset = struct.unpack_from("<I", data, cursor + 42)[0]
    if local_offset >= second_offset:
        struct.pack_into("<I", data, cursor + 42, local_offset + len(padding))
    cursor += 46 + name_length + extra_length + comment_length

if data[cursor:cursor + 4] != b"PK\x05\x06":
    raise RuntimeError("fixture EOCD not found")
struct.pack_into("<I", data, cursor + 16, central_offset)
(root / "padded.apk").write_bytes(data)
PY

"$checker" "$fixture_dir/normal.apk" >/dev/null
if "$checker" "$fixture_dir/padded.apk" >"$fixture_dir/out" 2>&1; then
    echo "FAIL: excessive internal padding was accepted" >&2
    exit 1
fi
grep -q '131072 bytes of internal padding' "$fixture_dir/out"

echo "Phone APK padding checks passed."
