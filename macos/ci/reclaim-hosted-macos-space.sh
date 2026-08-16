#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

dry_run=false
if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=true
elif [[ $# -ne 0 ]]; then
    echo "usage: $0 [--dry-run]" >&2
    exit 2
fi

if [[ "$dry_run" == false ]]; then
    [[ "$(uname -s)" == Darwin ]] || { echo "cleanup requires macOS" >&2; exit 1; }
    [[ "${GITHUB_ACTIONS:-}" == true ]] || { echo "cleanup requires GitHub Actions" >&2; exit 1; }
    [[ "${RUNNER_ENVIRONMENT:-}" == github-hosted ]] || {
        echo "cleanup is forbidden on self-hosted runners" >&2
        exit 1
    }
    [[ "${OVERTE_ALLOW_EPHEMERAL_RUNNER_CLEANUP:-}" == 1 ]] || {
        echo "cleanup requires explicit ephemeral-runner authorization" >&2
        exit 1
    }
    developer_dir="$(xcode-select -p)"
else
    developer_dir="${OVERTE_MACOS_TEST_DEVELOPER_DIR:-/Applications/Xcode_Test.app/Contents/Developer}"
fi

case "$developer_dir" in
    /Applications/Xcode*.app/Contents/Developer) ;;
    *) echo "refusing unexpected Xcode developer directory: $developer_dir" >&2; exit 1 ;;
esac

readonly -a targets=(
    "$developer_dir/Platforms/iPhoneOS.platform"
    "$developer_dir/Platforms/iPhoneSimulator.platform"
    "$developer_dir/Platforms/AppleTVOS.platform"
    "$developer_dir/Platforms/AppleTVSimulator.platform"
    "$developer_dir/Platforms/WatchOS.platform"
    "$developer_dir/Platforms/WatchSimulator.platform"
    "$developer_dir/Platforms/XROS.platform"
    "$developer_dir/Platforms/XRSimulator.platform"
    "$developer_dir/iOS DeviceSupport"
    "$developer_dir/tvOS DeviceSupport"
    "$developer_dir/watchOS DeviceSupport"
    "/Library/Developer/CoreSimulator/Caches"
    "/Library/Developer/CoreSimulator/Profiles/Runtimes"
)

validate_target() {
    local target="$1"
    case "$target" in
        "$developer_dir"/Platforms/iPhoneOS.platform|\
        "$developer_dir"/Platforms/iPhoneSimulator.platform|\
        "$developer_dir"/Platforms/AppleTVOS.platform|\
        "$developer_dir"/Platforms/AppleTVSimulator.platform|\
        "$developer_dir"/Platforms/WatchOS.platform|\
        "$developer_dir"/Platforms/WatchSimulator.platform|\
        "$developer_dir"/Platforms/XROS.platform|\
        "$developer_dir"/Platforms/XRSimulator.platform|\
        "$developer_dir"/iOS\ DeviceSupport|\
        "$developer_dir"/tvOS\ DeviceSupport|\
        "$developer_dir"/watchOS\ DeviceSupport|\
        /Library/Developer/CoreSimulator/Caches|\
        /Library/Developer/CoreSimulator/Profiles/Runtimes) ;;
        *) echo "refusing non-allowlisted cleanup target: $target" >&2; exit 1 ;;
    esac
}

if [[ "$dry_run" == false ]]; then
    df -hm .
fi
for target in "${targets[@]}"; do
    validate_target "$target"
    if [[ "$dry_run" == true ]]; then
        printf '%s\n' "$target"
    elif [[ -e "$target" ]]; then
        size_mib="$(du -sm "$target" 2>/dev/null | awk '{print $1}' || printf 'unknown')"
        printf 'Removing unused hosted-runner payload: %s (%s MiB)\n' "$target" "$size_mib"
        sudo rm -rf -- "$target"
    fi
done
if [[ "$dry_run" == false ]]; then
    df -hm .
fi
