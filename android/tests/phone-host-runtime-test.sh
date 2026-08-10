#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly checker="$script_dir/../ci/check-phone-host-runtime.sh"
readonly fixture_dir="$(mktemp -d "${TMPDIR:-/tmp}/phone-host-runtime.XXXXXX")"
trap 'rm -rf -- "$fixture_dir"' EXIT

write_node() {
    local version="$1"
    printf '#!/usr/bin/env bash\nprintf "%%s\\n" %q\n' "$version" > "$fixture_dir/node"
    chmod +x "$fixture_dir/node"
}

expect_pass() {
    local version="$1"
    write_node "$version"
    PATH="$fixture_dir:/usr/bin:/bin" PHONE_NODE_COMMAND="$fixture_dir/node" \
        "$checker" >/dev/null
}

expect_fail() {
    local description="$1"
    shift
    if "$@" >/dev/null 2>&1; then
        printf 'FAIL: %s\n' "$description" >&2
        exit 1
    fi
}

expect_pass v18.0.0
expect_pass v22.22.3

write_node v17.9.1
expect_fail 'Node.js 17 must be rejected' env \
    PATH="$fixture_dir:/usr/bin:/bin" PHONE_NODE_COMMAND="$fixture_dir/node" "$checker"

write_node unknown
expect_fail 'an unparseable Node.js version must be rejected' env \
    PATH="$fixture_dir:/usr/bin:/bin" PHONE_NODE_COMMAND="$fixture_dir/node" "$checker"

expect_fail 'a missing Node.js command must be rejected' env \
    PATH="$fixture_dir:/usr/bin:/bin" PHONE_NODE_COMMAND="$fixture_dir/missing-node" "$checker"

printf 'Phone host-runtime fail-closed tests passed.\n'
