#!/usr/bin/env bash

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"
readonly source_file="$repo_root/interface/src/Application.cpp"
readonly avatar_file="$repo_root/interface/src/avatar/MyAvatar.cpp"
readonly controller_file="$repo_root/libraries/physics/src/CharacterController.h"

grep -Fq '#if defined(ANDROID_APP_PHONE_INTERFACE)' "$source_file"
grep -Fq 'QTimer::singleShot(0, this, [viewpoint]' "$source_file"
grep -Fq 'goToViewpointForPath(' "$source_file"
grep -Fq 'QUrlQuery(domainURL).hasQueryItem(QStringLiteral("location"))' "$source_file"
grep -Fq 'schedulePhoneServerlessRootViewpoint(namedPaths);' "$source_file"
grep -Fq 'PHONE_SERVERLESS_TRACE rootViewpointApplied' "$source_file"
grep -Eq 'Q_OS_IOS.*ANDROID_APP_PHONE_INTERFACE' "$avatar_file"
grep -Fq 'canFinalizeGoTo' "$avatar_file"
grep -Fq '_rigidBody && _inWorld' "$controller_file"

printf 'phone serverless viewpoint test passed\n'
