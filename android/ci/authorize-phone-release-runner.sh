#!/usr/bin/env bash

# Install a root-owned copy outside the Actions runner application directory and
# set ACTIONS_RUNNER_HOOK_JOB_STARTED to that absolute path. GitHub runs this
# before any checkout or job step; a non-zero exit prevents the job from running.
set -euo pipefail

require_value() {
    local variable="$1" expected="$2" actual
    actual="${!variable:-}"
    if [[ "$actual" != "$expected" ]]; then
        printf 'ERROR: Android Phone release runner rejected %s\n' "$variable" >&2
        exit 70
    fi
}

require_value GITHUB_REPOSITORY noah-be/overte
require_value GITHUB_EVENT_NAME workflow_dispatch
require_value GITHUB_WORKFLOW 'Android Phone release candidate'
require_value GITHUB_ACTOR noah-be
require_value GITHUB_TRIGGERING_ACTOR noah-be
