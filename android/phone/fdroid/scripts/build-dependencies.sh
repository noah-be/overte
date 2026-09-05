#!/bin/sh
set -eu

usage() {
  echo "usage: $0 --preflight" >&2
  echo "The qualified cold build stays unavailable until this preflight passes." >&2
  exit 2
}

[ "${1:-}" = "--preflight" ] || usage
[ "$#" -eq 1 ] || usage

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo_root=$(CDPATH= cd -- "$script_dir/../../../.." && pwd)
manifest="$script_dir/../manifests/recipe-source.lock.json"

python3 -m unittest "$script_dir/../conan/test_reproducible_graph.py"

minimum_bytes=$(python3 -c \
  'import json,sys; print(json.load(open(sys.argv[1]))["cold_build"]["minimum_free_bytes"])' \
  "$manifest")
available_bytes=$(df -B1 --output=avail "$repo_root" | awk 'NR == 2 {print $1}')

if [ "$available_bytes" -lt "$minimum_bytes" ]; then
  echo "cold-build preflight: FAIL (insufficient disk)" >&2
  echo "available_bytes=$available_bytes minimum_free_bytes=$minimum_bytes" >&2
  exit 1
fi

command -v conan >/dev/null 2>&1 || {
  echo "cold-build preflight: FAIL (conan unavailable)" >&2
  exit 1
}
command -v bwrap >/dev/null 2>&1 || {
  echo "cold-build preflight: FAIL (bwrap unavailable)" >&2
  exit 1
}

bwrap --unshare-net --ro-bind / / --dev /dev --proc /proc \
  /bin/sh -c 'test "$(wc -l < /proc/net/route)" -le 1'

echo "cold-build preflight: PASS"
echo "The operator may now provision an empty Conan home and start the single recorded build."
