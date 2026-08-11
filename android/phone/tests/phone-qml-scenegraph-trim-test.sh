#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly qml_dir="$script_dir/../../../interface/resources/qml/hifi/+android_interface"

for name in ActionBar AudioBar; do
    file="$qml_dir/$name.qml"

    grep -Eq '^import QtQuick 2\.5$' "$file" || {
        echo "FAIL: $name lost its required QtQuick import" >&2
        exit 1
    }

    if grep -Eq '^[[:space:]]*Rectangle[[:space:]]*\{' "$file"; then
        echo "FAIL: $name still has a transparent full-size scenegraph wrapper" >&2
        exit 1
    fi

    for property in \
        'id:[[:space:]]*flowMain' \
        'spacing:[[:space:]]*10' \
        'flow:[[:space:]]*Flow\.TopToBottom' \
        'layoutDirection:[[:space:]]*Flow\.TopToBottom' \
        'anchors\.fill:[[:space:]]*parent' \
        'anchors\.margins:[[:space:]]*4'; do
        grep -Eq "$property" "$file" || {
            echo "FAIL: $name Flow layout changed ($property)" >&2
            exit 1
        }
    done

    grep -Eq 'component\.createObject\(flowMain\)' "$file" || {
        echo "FAIL: $name buttons are no longer parented to flowMain" >&2
        exit 1
    }
done

for name in ActionBar AudioBar; do
    [[ $(grep -Ec '^import ' "$qml_dir/$name.qml") -eq 1 ]] || {
        echo "FAIL: $name retains unused QML imports" >&2
        exit 1
    }
done

grep -Eq 'Window\.geometryChanged\.connect' "$qml_dir/AudioBar.qml"
grep -Eq 'Window\.geometryChanged\.disconnect' "$qml_dir/AudioBar.qml"

button_file="$qml_dir/button.qml"
[[ $(grep -Ec '^import ' "$button_file") -eq 1 ]] || {
    echo 'FAIL: Android touch button retains unused QML imports' >&2
    exit 1
}
if grep -Eq 'FontLoader|FiraSans-Regular\.ttf' "$button_file"; then
    echo 'FAIL: Android touch buttons redundantly load the globally registered font' >&2
    exit 1
fi
grep -Eq 'font\.family:[[:space:]]*button\.fontFamily' "$button_file" || {
    echo 'FAIL: Android touch button no longer uses its configured font family' >&2
    exit 1
}

echo 'Phone QML scenegraph trim checks passed.'
