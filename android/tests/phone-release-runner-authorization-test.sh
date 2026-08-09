#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
hook="$script_dir/../ci/authorize-phone-release-runner.sh"

run_hook() {
    env -i PATH=/usr/bin:/bin \
        GITHUB_REPOSITORY="${GITHUB_REPOSITORY_VALUE:-noah-be/overte}" \
        GITHUB_EVENT_NAME="${GITHUB_EVENT_NAME_VALUE:-workflow_dispatch}" \
        GITHUB_WORKFLOW="${GITHUB_WORKFLOW_VALUE:-Android Phone release candidate}" \
        GITHUB_ACTOR="${GITHUB_ACTOR_VALUE:-noah-be}" \
        GITHUB_TRIGGERING_ACTOR="${GITHUB_TRIGGERING_ACTOR_VALUE:-noah-be}" \
        bash "$hook"
}

expect_rejected() {
    local label="$1"
    if run_hook >/dev/null 2>&1; then
        printf 'FAIL: runner hook accepted %s\n' "$label" >&2
        exit 1
    fi
}

run_hook

GITHUB_EVENT_NAME_VALUE=pull_request expect_rejected 'pull request code'
GITHUB_EVENT_NAME_VALUE=pull_request_target expect_rejected 'pull request target code'
GITHUB_EVENT_NAME_VALUE=push expect_rejected 'push code'
GITHUB_REPOSITORY_VALUE=attacker/fork expect_rejected 'another repository'
GITHUB_WORKFLOW_VALUE='Impostor workflow' expect_rejected 'another workflow'
GITHUB_ACTOR_VALUE=external-user expect_rejected 'another actor'
GITHUB_TRIGGERING_ACTOR_VALUE=external-user expect_rejected 'external rerun actor'

printf 'Android Phone release runner authorization checks passed.\n'
