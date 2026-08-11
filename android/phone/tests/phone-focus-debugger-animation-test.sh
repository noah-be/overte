#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../../interface/resources/qml/desktop/Desktop.qml"

focus_debugger_block="$({
    awk '
        /id:[[:space:]]*focusDebugger[[:space:]]*;/ { found = 1 }
        found { print }
        found && /^    }[[:space:]]*$/ { exit }
    ' "$source_file"
})"

[[ -n "$focus_debugger_block" ]] || {
    echo 'FAIL: focusDebugger rectangle is missing' >&2
    exit 1
}

animation_block="$({
    awk '
        /ColorAnimation[[:space:]]+on[[:space:]]+color[[:space:]]*\{/ { found = 1 }
        found { print }
        found && /^        }[[:space:]]*$/ { exit }
    ' <<< "$focus_debugger_block"
})"

[[ -n "$animation_block" ]] || {
    echo 'FAIL: focusDebugger color animation is missing' >&2
    exit 1
}

for property in \
        'from:[[:space:]]*"#7fffff00"' \
        'to:[[:space:]]*"#7f0000ff"' \
        'duration:[[:space:]]*1000([^0-9]|$)' \
        'loops:[[:space:]]*9999([^0-9]|$)'; do
    grep -Eq "$property" <<< "$animation_block" || {
        echo "FAIL: focusDebugger color animation changed ($property)" >&2
        exit 1
    }
done

grep -Eq 'running:[[:space:]]*focusDebugger\.visible([^[:alnum:]_.]|$)' <<< "$animation_block" || {
    echo 'FAIL: focusDebugger color animation runs while the debugger is hidden' >&2
    exit 1
}

echo 'Phone focus debugger animation checks passed.'
