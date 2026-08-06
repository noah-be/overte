#!/usr/bin/env bash
set -euo pipefail

RESULTS="${1:-}"
[[ -n "$RESULTS" && -f "$RESULTS" ]] || {
    echo "usage: $0 RESULTS.csv [ACTIVE_RESOURCES.csv]" >&2
    exit 2
}
ACTIVE="${2:-${RESULTS%.csv}-active-resources.csv}"
SAMPLES="${RESULTS%.csv}-samples.csv"
DIAGNOSTICS="${RESULTS%.csv}-diagnostics.log"

echo "Pico 4 world-loading report"
echo "results=$RESULTS"
echo

awk -F, '
NR == 1 { next }
{
    run = $1
    printf "run %s: playable=%sms release=%sms settled=%sms entities=%s domain_resets=%s\n",
        run, $9, $10, $12, $20, $27
    playable[run] = $9
    release[run] = $10
    settled[run] = $12
    n = run
}
END {
    if (n == 0) exit
    print ""
    printf "range: playable=%sms..%sms release=%sms..%sms settled=%sms..%sms\n",
        min(playable), max(playable), min(release), max(release), min(settled), max(settled)
}
function min(a, i, v) { v = -1; for (i in a) if (v < 0 || a[i] < v) v = a[i]; return v }
function max(a, i, v) { v = -1; for (i in a) if (v < 0 || a[i] > v) v = a[i]; return v }
' "$RESULTS"

if [[ -f "$SAMPLES" ]]; then
    echo
    echo "resource/entity deltas from sampled telemetry:"
    awk -F, '
    NR == 1 { next }
    {
        run = $1
        if (!(run in first)) {
            first[run] = 1
            http0[run] = $10; bytes0[run] = $16; packets0[run] = $17
            scripts0[run] = $29; preloads0[run] = $30
        }
        http[run] = $10; bytes[run] = $16; packets[run] = $17
        scripts[run] = $29; preloads[run] = $30
        if (run in previous_epoch && $2 - previous_epoch[run] > max_gap[run])
            max_gap[run] = $2 - previous_epoch[run]
        previous_epoch[run] = $2
    }
    END {
        for (run in first)
            printf "run %s: http_requests=%d http_bytes=%d entity_packets=%d script_loads=%d preload_callbacks=%d max_sample_gap=%dms\n",
                run, http[run] - http0[run], bytes[run] - bytes0[run], packets[run] - packets0[run],
                scripts[run] - scripts0[run], preloads[run] - preloads0[run], max_gap[run]
    }
    ' "$SAMPLES" | sort -t' ' -k2,2n
fi

if [[ -f "$DIAGNOSTICS" ]]; then
    echo
    echo "slow entity preloads (descending):"
    awk '
    /PICO_ENTITY_PRELOAD_SLOW/ {
        elapsed = ""; script = ""
        for (i = 1; i <= NF; ++i) {
            if ($i == "elapsedMs") elapsed = $(i + 1)
            if ($i == "script") script = $(i + 1)
        }
        gsub(/^"|"$/, "", script)
        if (elapsed != "" && script != "") print elapsed "\t" script
    }
    ' "$DIAGNOSTICS" | sort -rn | head -n 20 | awk -F'\t' '{printf "%6d ms  %s\n", $1, $2}'
    echo
    echo "slow entity preload totals by script URL:"
    awk '
    /PICO_ENTITY_PRELOAD_SLOW/ {
        elapsed = ""; script = ""
        for (i = 1; i <= NF; ++i) {
            if ($i == "elapsedMs") elapsed = $(i + 1)
            if ($i == "script") script = $(i + 1)
        }
        gsub(/^"|"$/, "", script)
        if (elapsed != "" && script != "") {
            count[script]++
            total[script] += elapsed
            if (elapsed > maximum[script]) maximum[script] = elapsed
        }
    }
    END {
        for (script in count)
            printf "%8d ms total  max=%6d ms  calls=%-3d %s\n", total[script], maximum[script], count[script], script
    }
    ' "$DIAGNOSTICS" | sort -rn | head -n 20
fi

if [[ ! -f "$ACTIVE" ]]; then
    echo
    echo "active_resources=missing ($ACTIVE)"
    exit 0
fi

echo
echo "longest-lived active resources (sample span >= 1 s):"
awk -F, '
NR == 1 { next }
{
    run = $1
    url = $8
    key = run SUBSEP url
    if (!(key in first)) { first[key] = $3; category[key] = $4; run_number[key] = run; display_url[key] = url }
    last[key] = $3
    count[key]++
}
END {
    for (key in count) {
        span = last[key] - first[key]
        if (span >= 1000) printf "run %-2s %8d ms  samples=%-3d %-8s %s\n", run_number[key], span, count[key], category[key], display_url[key]
    }
}
' "$ACTIVE" | sort -rn | head -n 20

echo
echo "largest advertised active resources (bytes_total):"
awk -F, '
NR == 1 { next }
{
    run = $1; total = $7; url = $8
    if (total ~ /^[0-9]+$/ && total > 0 && total > maximum[run SUBSEP url]) {
        maximum[run SUBSEP url] = total
        category[run SUBSEP url] = $4
        run_number[run SUBSEP url] = run
        display_url[run SUBSEP url] = url
    }
}
END {
    for (key in maximum)
        printf "run %-2s %12d bytes %-8s %s\n", run_number[key], maximum[key], category[key], display_url[key]
}
' "$ACTIVE" | sort -k3,3nr | head -n 20

echo
echo "resource snapshot counts by category:"
awk -F, 'NR > 1 { count[$4]++ } END { for (category in count) print category "," count[category] }' "$ACTIVE" | sort

echo
echo "optimization priorities (provisional thresholds):"
if [[ -f "$SAMPLES" ]]; then
    awk -F, '
    NR == 1 { next }
    {
        run = $1
        if (run in previous && $2 - previous[run] > maxGap[run]) maxGap[run] = $2 - previous[run]
        previous[run] = $2
    }
    END {
        for (run in maxGap)
            if (maxGap[run] >= 10000) printf "HIGH  run %s: interface telemetry gap %d ms\n", run, maxGap[run]
    }
    ' "$SAMPLES"
fi
if [[ -f "$DIAGNOSTICS" ]]; then
    awk '
    /PICO_ENTITY_PRELOAD_SLOW/ {
        elapsed = ""; script = ""
        for (i = 1; i <= NF; ++i) {
            if ($i == "elapsedMs") elapsed = $(i + 1)
            if ($i == "script") script = $(i + 1)
        }
        gsub(/^"|"$/, "", script)
        if (elapsed != "" && script != "") { total[script] += elapsed; count[script]++ }
    }
    END {
        for (script in total)
            if (total[script] >= 10000)
                printf "HIGH  script preload %s: %d ms across %d calls\n", script, total[script], count[script]
    }
    ' "$DIAGNOSTICS"
fi
awk -F, '
NR == 1 { next }
{
    run = $1; url = $8; key = run SUBSEP url
    if (!(key in first)) first[key] = $3
    last[key] = $3; category[key] = $4
}
END {
    for (key in last) {
        span = last[key] - first[key]
        if (span >= 10000) printf "HIGH  run/resource span %d ms (%s)\n", span, category[key]
    }
}
' "$ACTIVE"
