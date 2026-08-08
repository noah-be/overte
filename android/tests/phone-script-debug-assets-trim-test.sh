#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/.." && pwd)"
gradle_file="$android_dir/apps/phoneInterface/build.gradle"

copy_block="$(awk '
    /from new File\(projectDir, '\''\.\.\/\.\.\/\.\.\/scripts'\''\)/ { inside=1 }
    inside { print }
    inside && /assetList\.add\("scripts\/\$\{details\.path\}"\)/ { found=1 }
    inside && found && /^[[:space:]]*}[[:space:]]*$/ { exit }
' "$gradle_file")"

grep -Fq "exclude '**/*.map'" <<<"$copy_block"
grep -Fq "exclude '**/web-types.json'" <<<"$copy_block"
grep -Fq 'assetList.add("scripts/${details.path}")' <<<"$copy_block"

if grep -Eq "exclude ['\"]\*\*/\*\.(js|qml|json|png|jpg|jpeg|svg|fbx|wav)['\"]" <<<"$copy_block"; then
    echo 'phone script trim must not exclude runtime script or media classes' >&2
    exit 1
fi

apk="$android_dir/apps/phoneInterface/build/outputs/apk/debug/phoneInterface-debug.apk"
if [[ -f "$apk" ]]; then
    if unzip -Z1 "$apk" | awk '
        /^assets\/scripts\/(.*[.]map|.*\/web-types[.]json)$/ { found=1 }
        END { exit !found }
    '; then
        echo 'phone APK still contains script debug metadata' >&2
        exit 1
    fi
fi

printf 'Phone script debug-asset trim checks passed.\n'
