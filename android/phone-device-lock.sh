#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_DIR
git_common_dir="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null)" || {
    echo "error: Phone device lock must run from an Overte Git worktree" >&2
    exit 2
}
if [[ "$git_common_dir" != /* ]]; then
    git_common_dir="$(cd -- "$SCRIPT_DIR/$git_common_dir" && pwd)"
fi

usage() {
    cat <<'EOF'
Usage: ./phone-device-lock.sh status
       ./phone-device-lock.sh wait
       ./phone-device-lock.sh run -- COMMAND [ARG ...]

Coordinate exclusive Android phone access across Codex sessions and Git
worktrees. The default lock lives in their shared Git common directory.

  status  Report whether the phone is available (exit 0) or in use (exit 1).
  wait    Wait until the current phone operation finishes, then return.
  run     Wait for exclusive access and hold it while COMMAND runs, then keep
          the phone reserved for a five-second cooldown before releasing it.

For a build that will be installed or tested on the phone, COMMAND must include
the complete build, install, test, diagnostic, and cleanup sequence. Do not run
the build outside the lock and acquire the phone only for the later ADB steps.

Example:
  ./phone-device-lock.sh run -- bash -c './build-phone.sh build && run-tests'
EOF
}

readonly DEVICE_LOCK_SCRIPT_DIR="$SCRIPT_DIR"
readonly DEVICE_LOCK_FILE="${PHONE_DEVICE_LOCK_FILE:-$git_common_dir/phone-device.lock}"
readonly DEVICE_LOCK_OWNER_FILE="${DEVICE_LOCK_FILE}.owner"
readonly DEVICE_LOCK_LABEL="Android phone"
readonly DEVICE_LOCK_HELD_VARIABLE="PHONE_DEVICE_LOCK_HELD"
readonly DEVICE_LOCK_RELEASE_DELAY_SECONDS="${PHONE_DEVICE_LOCK_RELEASE_DELAY_SECONDS:-5}"
readonly DEVICE_LOCK_PHASE_METADATA=1
readonly DEVICE_LOCK_BRANCH_MODE=caller
[[ "$DEVICE_LOCK_RELEASE_DELAY_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "error: Phone lock release delay must be a non-negative number" >&2
    exit 2
}

source "$SCRIPT_DIR/device-lock-core.sh"
device_lock_main "$@"
