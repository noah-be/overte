#!/usr/bin/env bash

# Run a command with a patch applied to a Git work tree, then restore the
# original tree even when the command fails. The caller remains responsible
# for ensuring exclusive access to the work tree.
with_temporary_git_patch() {
    local patch_file="$1"
    local work_tree="$2"
    shift 2

    [[ "$patch_file" == /* && -f "$patch_file" ]] || {
        echo "error: temporary patch must be an absolute regular file: $patch_file" >&2
        return 2
    }
    [[ -d "$work_tree/.git" || -f "$work_tree/.git" ]] || {
        echo "error: temporary patch target is not a Git work tree: $work_tree" >&2
        return 2
    }
    (($# > 0)) || {
        echo "error: temporary patch command is missing" >&2
        return 2
    }

    (
        local patch_applied=0 status

        cleanup_temporary_patch() {
            ((patch_applied == 1)) || return 0
            git -C "$work_tree" apply --reverse "$patch_file"
            patch_applied=0
        }
        trap cleanup_temporary_patch EXIT INT TERM

        if git -C "$work_tree" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
            echo "Removing a temporary patch left by an interrupted earlier run"
            git -C "$work_tree" apply --reverse "$patch_file"
        fi
        git -C "$work_tree" apply --check "$patch_file"
        git -C "$work_tree" apply "$patch_file"
        patch_applied=1

        if "$@"; then
            status=0
        else
            status=$?
        fi

        if ! git -C "$work_tree" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
            echo "error: command changed the temporary patch footprint" >&2
            return 2
        fi
        cleanup_temporary_patch
        trap - EXIT INT TERM
        return "$status"
    )
}
