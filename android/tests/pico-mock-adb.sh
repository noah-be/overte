#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" == "devices" ]]; then
    printf 'List of devices attached\n'
    case "${MOCK_DEVICE_COUNT:-1}" in
        0) ;;
        1) printf 'mock-device-1\tdevice\n' ;;
        2) printf 'mock-device-1\tdevice\nmock-device-2\tdevice\n' ;;
        *) echo "unsupported MOCK_DEVICE_COUNT" >&2; exit 2 ;;
    esac
    exit 0
fi

if [[ "${1:-}" == "-s" && $# -ge 3 ]]; then
    shift 2
fi
[[ "${1:-}" == "shell" ]] || { echo "unexpected mock adb command" >&2; exit 2; }
shift

if [[ "${1:-}" == "run-as" && "${3:-}" == "cat" && "${4:-}" == "cache/avatar-status" ]]; then
    printf '%s\n' "${MOCK_AVATAR_STATUS:-}"
    exit 0
fi

case "${1:-}" in
    setprop|input|am) exit 0 ;;
    *) echo "unexpected mock adb shell command" >&2; exit 2 ;;
esac
