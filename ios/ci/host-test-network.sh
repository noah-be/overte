#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Ubuntu's hosted image restricts unprivileged user namespaces. Create only a
# network namespace using its passwordless runner sudo, then drop to the runner
# UID/GID before executing the test. Never request authentication on local hosts.
[[ "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted && "$(uname -s)" == Linux ]] || {
    echo "This network test launcher requires a GitHub-hosted Linux runner" >&2
    exit 64
}
(( $# > 0 )) || exit 64
exec sudo -n unshare --net --setgid "$(id -g)" --setuid "$(id -u)" -- "$@"
