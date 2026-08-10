#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/../.." && pwd)"

tests=(
    phone-app-lifecycle-test.sh
    phone-tablet-core-contract-test.sh
    phone-tablet-presenter-test.sh
    phone-tablet-privacy-test.sh
    phone-tablet-routing-test.sh
    phone-tablet-app-router-test.sh
    phone-tablet-general-preferences-test.sh
    phone-tablet-settings-scale-test.sh
    phone-tablet-security-test.sh
    phone-tablet-touch-qml-test.sh
    phone-tablet-audio-test.sh
    phone-tablet-emote-test.sh
    phone-tablet-avatar-test.sh
    phone-tablet-places-test.sh
    phone-tablet-portal-lifecycle-test.sh
    phone-tablet-places-directory-test.sh
    phone-tablet-people-menu-test.sh
    phone-tablet-quick-goto-test.sh
    phone-tablet-shield-test.sh
    phone-tablet-create-contract-test.sh
    phone-dialog-routing-test.sh
    phone-actionbar-qml-lifetime-test.sh
    phone-script-payload-test.sh
    phone-modern-android-api-test.sh
    phone-jni-boundary-test.sh
)

for test_name in "${tests[@]}"; do
    printf '\n[%s]\n' "$test_name"
    "$script_dir/$test_name"
done

for script in \
        scripts/system/pal.js \
        scripts/system/quickGoto.js \
        scripts/system/avatarapp.js \
        scripts/system/places/places.js \
        scripts/system/places/portal.js \
        scripts/system/bubble.js; do
    node --check "$repo_root/$script"
done

"$script_dir/phone-host-regression-test.sh"
git -C "$repo_root" diff --check

printf '\nAndroid phone tablet static gate passed.\n'
