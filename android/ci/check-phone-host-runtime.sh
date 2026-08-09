#!/usr/bin/env bash

set -euo pipefail

readonly node_command="${PHONE_NODE_COMMAND:-node}"

if ! command -v "$node_command" >/dev/null 2>&1; then
    printf 'Node.js 18 or newer is required for the device-free host tier.\n' >&2
    exit 1
fi

node_version="$($node_command --version 2>&1)"
if [[ ! "$node_version" =~ ^v([0-9]+)(\.|$) ]] || (( BASH_REMATCH[1] < 18 )); then
    printf 'Node.js 18 or newer is required; found: %s\n' "$node_version" >&2
    exit 1
fi

printf 'Node.js host-test runtime verified: %s\n' "$node_version"
