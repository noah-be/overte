#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
git_common_dir="$(git -C "$SCRIPT_DIR" rev-parse --git-common-dir 2>/dev/null)" || {
    echo "error: Phone device lock must run from an Overte Git worktree" >&2
    exit 2
}
if [[ "$git_common_dir" != /* ]]; then
    git_common_dir="$(cd -- "$SCRIPT_DIR/$git_common_dir" && pwd)"
fi

LOCK_FILE="${PHONE_DEVICE_LOCK_FILE:-$git_common_dir/phone-device.lock}"
OWNER_FILE="${LOCK_FILE}.owner"
readonly RELEASE_DELAY_SECONDS=5
COMMAND="${1:-status}"
shift || true

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

open_lock() {
    local lock_directory
    lock_directory="$(dirname -- "$LOCK_FILE")"
    [[ -d "$lock_directory" && -w "$lock_directory" ]] || {
        echo "error: Phone lock directory is not writable: $lock_directory" >&2
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
            echo "Android phone is available"
        else
            printf 'Android phone is in use: %s\n' "$(describe_owner)"
            exit 1
        fi
        ;;
    wait)
        (( $# == 0 )) || { usage >&2; exit 2; }
        open_lock
        if ! flock -n "$LOCK_FD"; then
            printf 'Android phone is in use; waiting: %s\n' "$(describe_owner)" >&2
            flock "$LOCK_FD"
        fi
        echo "Android phone is available"
        ;;
    run)
        [[ "${1:-}" == -- ]] || { usage >&2; exit 2; }
        shift
        (( $# > 0 )) || { usage >&2; exit 2; }
        open_lock
        if ! flock -n "$LOCK_FD"; then
            printf 'Android phone is in use; waiting: %s\n' "$(describe_owner)" >&2
            flock "$LOCK_FD"
        fi

        caller_worktree="$PWD"
        if ! git -C "$caller_worktree" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            caller_worktree="$SCRIPT_DIR"
        fi
        branch="$(git -C "$caller_worktree" symbolic-ref --quiet --short HEAD 2>/dev/null || printf detached)"
        started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        owns_metadata=1
        release_lock_metadata() {
            if (( owns_metadata )); then
                printf 'pid=%s since=%s branch=%s phase=cooldown\n' \
                    "$$" "$started" "$branch" >"$OWNER_FILE"
                sleep "$RELEASE_DELAY_SECONDS"
                rm -f -- "$OWNER_FILE"
                owns_metadata=0
            fi
        }
        trap release_lock_metadata EXIT
        trap 'exit 130' INT
        trap 'exit 143' TERM
        trap 'exit 129' HUP
        printf 'pid=%s since=%s branch=%s phase=active\n' \
            "$$" "$started" "$branch" >"$OWNER_FILE"
        export PHONE_DEVICE_LOCK_HELD=1

        set +e
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
