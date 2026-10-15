#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
hook="$script_dir/../ci/authorize-phone-release-runner.sh"

run_hook() {
    env -i PATH=/usr/bin:/bin \
        GITHUB_REPOSITORY="${GITHUB_REPOSITORY_VALUE-noah-l-frank/overte}" \
        GITHUB_EVENT_NAME="${GITHUB_EVENT_NAME_VALUE-workflow_dispatch}" \
        GITHUB_WORKFLOW="${GITHUB_WORKFLOW_VALUE-Android Phone release candidate}" \
        GITHUB_ACTOR="${GITHUB_ACTOR_VALUE-noah-l-frank}" \
        GITHUB_TRIGGERING_ACTOR="${GITHUB_TRIGGERING_ACTOR_VALUE-noah-l-frank}" \
        bash "$hook"
}

expect_rejected() {
    local label="$1" rejected_variable="$2" hook_output hook_status=0
    hook_output="$(run_hook 2>&1)" || hook_status=$?
    if [[ "$hook_status" != 70 ||
          "$hook_output" != "ERROR: Android Phone release runner rejected $rejected_variable" ]]; then
        printf 'FAIL: runner hook did not reject %s at %s with exit 70\n' \
            "$label" "$rejected_variable" >&2
        exit 1
    fi
}

run_hook

GITHUB_EVENT_NAME_VALUE=pull_request expect_rejected 'pull request code' GITHUB_EVENT_NAME
GITHUB_EVENT_NAME_VALUE=pull_request_target expect_rejected 'pull request target code' GITHUB_EVENT_NAME
GITHUB_EVENT_NAME_VALUE=push expect_rejected 'push code' GITHUB_EVENT_NAME
GITHUB_REPOSITORY_VALUE=attacker/fork expect_rejected 'another repository' GITHUB_REPOSITORY
GITHUB_WORKFLOW_VALUE='Impostor workflow' expect_rejected 'another workflow' GITHUB_WORKFLOW
GITHUB_ACTOR_VALUE=external-user expect_rejected 'another actor' GITHUB_ACTOR
GITHUB_TRIGGERING_ACTOR_VALUE=external-user expect_rejected 'external rerun actor' GITHUB_TRIGGERING_ACTOR

# Each stale identity is rejected while the other tuple fields remain current.
GITHUB_REPOSITORY_VALUE=noah-be/overte expect_rejected 'former repository name' GITHUB_REPOSITORY
GITHUB_ACTOR_VALUE=noah-be expect_rejected 'former actor name' GITHUB_ACTOR
GITHUB_TRIGGERING_ACTOR_VALUE=noah-be expect_rejected 'former rerun actor name' GITHUB_TRIGGERING_ACTOR

GITHUB_REPOSITORY_VALUE='' expect_rejected 'empty repository' GITHUB_REPOSITORY
GITHUB_EVENT_NAME_VALUE='' expect_rejected 'empty event' GITHUB_EVENT_NAME
GITHUB_WORKFLOW_VALUE='' expect_rejected 'empty workflow' GITHUB_WORKFLOW
GITHUB_ACTOR_VALUE='' expect_rejected 'empty actor' GITHUB_ACTOR
GITHUB_TRIGGERING_ACTOR_VALUE='' expect_rejected 'empty rerun actor' GITHUB_TRIGGERING_ACTOR

printf 'Android Phone release runner authorization checks passed (1 accepted, 15 rejected).\n'
