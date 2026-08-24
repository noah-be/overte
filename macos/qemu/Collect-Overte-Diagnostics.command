#!/bin/bash

set -u

output_dir="$(cd "$(dirname "$0")" && pwd)"
output="$output_dir/Overte-QEMU-Diagnostics.txt"

{
    echo "Collected: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    echo
    echo "=== macOS ==="
    sw_vers
    uname -a
    echo
    echo "=== Displays and graphics ==="
    system_profiler SPDisplaysDataType
    echo
    echo "=== Overte processes ==="
    ps -axo pid,ppid,state,%cpu,%mem,etime,command | grep -i '[O]verte'
    echo
    echo "=== Overte unified log (last 30 minutes) ==="
    log show --style compact --last 30m \
        --predicate 'process == "Overte" OR eventMessage CONTAINS[c] "Overte"' \
        2>&1
    echo
    echo "=== Recent Overte-related files ==="
    find "$HOME/Library/Logs/Overte" \
        "$HOME/Library/Application Support/Overte" \
        "$HOME/Library/Application Support/Interface" \
        "$HOME/Library/Application Support/Overte - Dev" \
        -maxdepth 6 -type f \( -iname '*overte*' -o -iname '*interface*log*' \) \
        -mtime -1 -print 2>/dev/null
    echo
    echo "=== Recent Overte application logs ==="
    find "$HOME/Library/Application Support/Overte" \
        "$HOME/Library/Application Support/Overte - Dev" \
        -maxdepth 5 -type f -name 'overte-log*.txt' -mtime -1 -print0 \
        2>/dev/null | xargs -0 tail -n 500 2>/dev/null
} >"$output" 2>&1

open -R "$output"
