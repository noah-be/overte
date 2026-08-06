#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
git_common_dir="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null)" || {
    echo "error: Pico device lock must run from an Overte Git worktree" >&2
    exit 2
}
if [[ "$git_common_dir" != /* ]]; then
    git_common_dir="$(cd -- "$SCRIPT_DIR/$git_common_dir" && pwd)"
fi

LOCK_FILE="${PICO_DEVICE_LOCK_FILE:-$git_common_dir/pico-device.lock}"
OWNER_FILE="${LOCK_FILE}.owner"
COMMAND="${1:-status}"
shift || true

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

open_lock() {
    local lock_directory
    lock_directory="$(dirname -- "$LOCK_FILE")"
    [[ -d "$lock_directory" && -w "$lock_directory" ]] || {
        echo "error: Pico lock directory is not writable: $lock_directory" >&2
        exit 2
    }
    exec {LOCK_FD}>"$LOCK_FILE"
}

describe_owner() {
    if [[ -s "$OWNER_FILE" ]]; then
        tr '\n' ' ' <"$OWNER_FILE" | sed 's/[[:space:]]*$//'
    else
        printf 'owner details unavailable'
    fi
}

case "$COMMAND" in
    -h|--help|help)
        usage
        ;;
    status)
        (( $# == 0 )) || { usage >&2; exit 2; }
        open_lock
        if flock -n "$LOCK_FD"; then
            echo "Pico headset is available"
        else
            printf 'Pico headset is in use: %s\n' "$(describe_owner)"
            exit 1
        fi
        ;;
    wait)
        (( $# == 0 )) || { usage >&2; exit 2; }
        open_lock
        if ! flock -n "$LOCK_FD"; then
            printf 'Pico headset is in use; waiting: %s\n' "$(describe_owner)" >&2
            flock "$LOCK_FD"
        fi
        echo "Pico headset is available"
        ;;
    run)
        [[ "${1:-}" == -- ]] || { usage >&2; exit 2; }
        shift
        (( $# > 0 )) || { usage >&2; exit 2; }
        open_lock
        if ! flock -n "$LOCK_FD"; then
            printf 'Pico headset is in use; waiting: %s\n' "$(describe_owner)" >&2
            flock "$LOCK_FD"
        fi

        branch="$(git -C "$SCRIPT_DIR" symbolic-ref --quiet --short HEAD 2>/dev/null || printf detached)"
        started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        owns_metadata=1
        release_lock_metadata() {
            if (( owns_metadata )); then
                rm -f -- "$OWNER_FILE"
                owns_metadata=0
            fi
        }
        trap release_lock_metadata EXIT INT TERM HUP
        printf 'pid=%s since=%s branch=%s\n' "$$" "$started" "$branch" >"$OWNER_FILE"
        export PICO_DEVICE_LOCK_HELD=1

        set +e
        # The wrapper process keeps the flock while the command runs. Close its
        # duplicate in the child so long-lived helpers such as the ADB server
        # cannot inherit the descriptor and retain the headset lock forever.
        "$@" {LOCK_FD}>&-
        command_status=$?
        set -e
        exit "$command_status"
        ;;
    *)
        usage >&2
        exit 2
        ;;
esac
