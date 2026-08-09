#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
git_common_dir="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null)" || {
    echo "error: Pico device lock must run from an Overte Git worktree" >&2
    exit 2
}
if [[ "$git_common_dir" != /* ]]; then
    git_common_dir="$(cd -- "$SCRIPT_DIR/$git_common_dir" && pwd)"
fi

usage() {
    cat <<'EOF'
Usage: ./pico-device-lock.sh status
       ./pico-device-lock.sh wait
       ./pico-device-lock.sh run -- COMMAND [ARG ...]

Coordinate exclusive Pico headset access across Codex sessions and Git
worktrees. The default lock lives in their shared Git common directory.

  status  Report whether the headset is available (exit 0) or in use (exit 1).
  wait    Wait until the current headset operation finishes, then return.
  run     Wait for exclusive access and hold it while COMMAND runs.
EOF
}

readonly DEVICE_LOCK_SCRIPT_DIR="$SCRIPT_DIR"
readonly DEVICE_LOCK_FILE="${PICO_DEVICE_LOCK_FILE:-$git_common_dir/pico-device.lock}"
readonly DEVICE_LOCK_OWNER_FILE="${DEVICE_LOCK_FILE}.owner"
readonly DEVICE_LOCK_LABEL="Pico headset"
readonly DEVICE_LOCK_HELD_VARIABLE="PICO_DEVICE_LOCK_HELD"
readonly DEVICE_LOCK_RELEASE_DELAY_SECONDS=0
readonly DEVICE_LOCK_PHASE_METADATA=0
readonly DEVICE_LOCK_BRANCH_MODE=script

source "$SCRIPT_DIR/device-lock-core.sh"
device_lock_main "$@"
