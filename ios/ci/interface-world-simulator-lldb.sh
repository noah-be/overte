#!/usr/bin/env bash
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0

# Capture the first Full Client simulator SIGSEGV with the exact dSYM that was
# shipped beside the preserved candidate.  This runner is diagnostic-only: a
# complete backtrace is useful evidence, but an app crash always remains a
# failing result.

set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly timeout_runner="$script_dir/../tools/run-with-timeout.py"
readonly simulator_selector="$script_dir/../tools/select-simulator.py"

app_path="${1:-}"
symbol_bundle="${2:-}"
bundle_id="${3:-}"
family="${4:-}"
source_revision="${5:-}"
candidate_sha256="${6:-}"
output_dir="${7:-}"
lldb_timeout="${OVERTE_IOS_LLDB_TIMEOUT_SECONDS:-240}"
attach_delay="${OVERTE_IOS_LLDB_ATTACH_DELAY_SECONDS:-1}"
attach_attempts="${OVERTE_IOS_LLDB_ATTACH_ATTEMPTS:-3}"
startup_trace="${OVERTE_IOS_LLDB_STARTUP_TRACE:-0}"
wait_for_debugger="${OVERTE_IOS_LLDB_WAIT_FOR_DEBUGGER:-0}"

[[ -d "$app_path" && "$app_path" == *.app && -x "$app_path/Overte" ]] || {
    echo "usage: $0 APP_PATH DSYM_BUNDLE BUNDLE_ID iphone SOURCE_REVISION CANDIDATE_SHA256 OUTPUT_DIR" >&2
    exit 2
}
[[ -d "$symbol_bundle" && "$symbol_bundle" == *.dSYM ]] || {
    echo "a matching dSYM bundle is required" >&2
    exit 2
}
[[ "$bundle_id" =~ ^[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9][A-Za-z0-9-]*)+$ ]] || {
    echo "invalid bundle identifier" >&2
    exit 2
}
[[ "$family" == iphone ]] || { echo "the focused LLDB run requires the iPhone simulator" >&2; exit 2; }
[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]] || { echo "invalid source revision" >&2; exit 2; }
[[ "$candidate_sha256" =~ ^[0-9a-f]{64}$ ]] || { echo "invalid candidate SHA-256" >&2; exit 2; }
[[ -n "$output_dir" ]] || { echo "output directory is required" >&2; exit 2; }
[[ "$lldb_timeout" =~ ^[1-9][0-9]*$ ]] && ((10#$lldb_timeout <= 600)) || {
    echo "OVERTE_IOS_LLDB_TIMEOUT_SECONDS must be an integer from 1 through 600" >&2
    exit 2
}
[[ "$attach_delay" =~ ^[0-9]+$ ]] && ((10#$attach_delay <= 20)) || {
    echo "OVERTE_IOS_LLDB_ATTACH_DELAY_SECONDS must be an integer from 0 through 20" >&2
    exit 2
}
[[ "$attach_attempts" =~ ^[1-5]$ ]] || {
    echo "OVERTE_IOS_LLDB_ATTACH_ATTEMPTS must be an integer from 1 through 5" >&2
    exit 2
}
[[ "$startup_trace" =~ ^[01]$ ]] || {
    echo "OVERTE_IOS_LLDB_STARTUP_TRACE must be 0 or 1" >&2
    exit 2
}
[[ "$wait_for_debugger" =~ ^[01]$ ]] || {
    echo "OVERTE_IOS_LLDB_WAIT_FOR_DEBUGGER must be 0 or 1" >&2
    exit 2
}
for helper in "$timeout_runner" "$simulator_selector"; do
    [[ -f "$helper" ]] || { echo "iOS LLDB helper is unavailable" >&2; exit 2; }
done

readonly symbol_binary="$symbol_bundle/Contents/Resources/DWARF/Overte"
[[ -f "$symbol_binary" ]] || { echo "dSYM does not contain the Overte symbol binary" >&2; exit 2; }

# These paths are interpolated into one LLDB command.  They originate from a
# fixed private workspace, but reject metacharacters explicitly rather than
# relying on that deployment detail.
for diagnostic_path in "$app_path" "$symbol_bundle" "$output_dir"; do
    case "$diagnostic_path" in
        *$'\n'*|*$'\r'*|*'"'*|*'\\'*)
            echo "diagnostic path cannot be represented safely in LLDB" >&2
            exit 2
            ;;
    esac
done

mkdir -p "$output_dir"
readonly lldb_log="$output_dir/iphone-serverless-lldb.log"
readonly application_log="$output_dir/iphone-serverless-lldb-application.log"
readonly result_log="$output_dir/iphone-serverless-lldb-result.log"
for destination in "$lldb_log" "$application_log" "$result_log"; do
    [[ ! -e "$destination" ]] || { echo "LLDB diagnostic destination already exists" >&2; exit 2; }
done

temp_root="$(mktemp -d "${TMPDIR:-/tmp}/overte-ios-lldb.XXXXXX")"
[[ -d "$temp_root" && "$temp_root" == */overte-ios-lldb.* ]] || {
    echo "could not create bounded LLDB workspace" >&2
    exit 2
}
readonly temp_root
readonly device_list="$temp_root/devices.json"
readonly command_stderr="$temp_root/command.stderr"
readonly app_stdout="$temp_root/application.stdout"
readonly app_stderr="$temp_root/application.stderr"
readonly crash_commands="$temp_root/on-crash.lldb"
readonly startup_commands="$temp_root/startup-trace.lldb"

: > "$app_stdout"
: > "$app_stderr"
: > "$lldb_log"
chmod 0600 "$lldb_log"

active_udid=""
boot_requested=0
app_installed=0
app_launched=0
lldb_status="not_run"
attach_attempts_used=0
capture_status="not_captured"
resume_trace="not_observed"
sandbox_trace="not_observed"
exit_trace="not_observed"
xcode_build="unknown"

run_bounded() {
    local label="$1" seconds="$2" status=0
    shift 2
    : > "$command_stderr"
    "$timeout_runner" "$seconds" "$@" 2>"$command_stderr" || status=$?
    if ((status != 0)); then
        echo "$label failed with status $status" >&2
    fi
    return "$status"
}

uuid_identity() {
    xcrun dwarfdump --uuid "$1" | awk '
        /^UUID: [0-9A-Fa-f-]+ \([^)]*\)/ { print tolower($2) ":" $3 }
    ' | LC_ALL=C sort -u
}

finish() {
    local status=$?
    trap - EXIT
    if ((app_launched)) && [[ -n "$active_udid" ]]; then
        run_bounded "application cleanup" 30 xcrun simctl terminate \
            "$active_udid" "$bundle_id" >/dev/null || true
    fi
    if ((app_installed)) && [[ -n "$active_udid" ]]; then
        run_bounded "installed application cleanup" 60 xcrun simctl uninstall \
            "$active_udid" "$bundle_id" >/dev/null || true
    fi
    if ((boot_requested)) && [[ -n "$active_udid" ]]; then
        run_bounded "simulator cleanup" 60 xcrun simctl shutdown "$active_udid" >/dev/null || true
    fi
    {
        printf '%s\n' '=== application stdout ==='
        cat "$app_stdout"
        printf '%s\n' '=== application stderr ==='
        cat "$app_stderr"
    } > "$application_log"
    chmod 0600 "$application_log"
    {
        printf 'schema=overte-ios-lldb-result-v1\n'
        printf 'mode=simulator-serverless\n'
        printf 'source_revision=%s\n' "$source_revision"
        printf 'candidate_sha256=%s\n' "$candidate_sha256"
        printf 'xcode_build=%s\n' "$xcode_build"
        printf 'attach_delay_seconds=%s\n' "$attach_delay"
        printf 'attach_attempts_requested=%s\n' "$attach_attempts"
        printf 'attach_attempts_used=%s\n' "$attach_attempts_used"
        printf 'wait_for_debugger=%s\n' "$wait_for_debugger"
        printf 'startup_trace=%s\n' "$startup_trace"
        printf 'lldb_status=%s\n' "$lldb_status"
        printf 'capture_status=%s\n' "$capture_status"
        printf 'resume_trace=%s\n' "$resume_trace"
        printf 'sandbox_trace=%s\n' "$sandbox_trace"
        printf 'exit_trace=%s\n' "$exit_trace"
        printf 'runner_status=%s\n' "$status"
    } > "$result_log"
    chmod 0600 "$result_log"
    rm -rf "$temp_root"
    exit "$status"
}
trap finish EXIT

# A dSYM mismatch must fail before boot, install, or launch.  The comparison
# intentionally ignores file paths and binds both UUID and architecture.
app_uuid="$(uuid_identity "$app_path/Overte")"
symbol_uuid="$(uuid_identity "$symbol_binary")"
[[ -n "$app_uuid" && "$app_uuid" == "$symbol_uuid" ]] || {
    echo "app and dSYM UUIDs do not match" >&2
    exit 2
}

xcode_build="$(xcodebuild -version | awk '/Build version/{print $3; exit}')"
[[ -n "$xcode_build" ]] || { echo "Xcode build identity is unavailable" >&2; exit 2; }

run_bounded "simulator discovery" 60 xcrun simctl list devices available --json > "$device_list"
active_udid="$(python3 "$simulator_selector" "$family" < "$device_list")"
[[ -n "$active_udid" ]] || { echo "simulator selection returned no device" >&2; exit 1; }

boot_requested=1
boot_status=0
run_bounded "simulator boot request" 60 xcrun simctl boot "$active_udid" >/dev/null || boot_status=$?
if ((boot_status == 124 || boot_status >= 128)); then
    exit "$boot_status"
fi
run_bounded "simulator boot" 360 xcrun simctl bootstatus "$active_udid" -b >/dev/null
run_bounded "stale application removal" 60 xcrun simctl uninstall \
    "$active_udid" "$bundle_id" >/dev/null || true
run_bounded "application install" 120 xcrun simctl install "$active_udid" "$app_path" >/dev/null
app_installed=1

data_container="$(run_bounded "application data container" 30 xcrun simctl get_app_container \
    "$active_udid" "$bundle_id" data)"
[[ -n "$data_container" && "$data_container" == /* && -d "$data_container" ]] || {
    echo "application data container is unavailable" >&2
    exit 1
}
mvk_dump_root="$data_container/tmp/overte-mvk-shaders-iphone-serverless-lldb"
[[ ! -e "$mvk_dump_root" ]] || { echo "MoltenVK dump path already exists" >&2; exit 1; }
mkdir "$mvk_dump_root"
chmod 0700 "$mvk_dump_root"

run_bounded "simulator microphone permission" 60 xcrun simctl privacy \
    "$active_udid" grant microphone "$bundle_id" >/dev/null

launch_arguments=(xcrun simctl launch)
if ((wait_for_debugger)); then
    launch_arguments+=(--wait-for-debugger)
fi
launch_arguments+=(
    --stdout="$app_stdout" --stderr="$app_stderr"
    "$active_udid" "$bundle_id" --url 'file:///~/serverless/tutorial.json'
    --ios-world-evidence --no-login-suggestion
)
launch_output="$(run_bounded "application launch for LLDB" 60 env \
    SIMCTL_CHILD_MVK_CONFIG_LOG_LEVEL=4 \
    SIMCTL_CHILD_MVK_CONFIG_USE_METAL_ARGUMENT_BUFFERS=0 \
    SIMCTL_CHILD_MVK_CONFIG_TRACE_VULKAN_CALLS=6 \
    SIMCTL_CHILD_MVK_CONFIG_SHADER_DUMP_DIR="$mvk_dump_root" \
    "${launch_arguments[@]}")"
[[ "$launch_output" == *":"* ]] || { echo "application launch returned no process identifier" >&2; exit 1; }
launch_pid="${launch_output##*: }"
[[ "$launch_pid" =~ ^[1-9][0-9]*$ ]] || { echo "application launch returned an invalid process identifier" >&2; exit 1; }
app_launched=1

# Attaching at dyld start without --wait-for-debugger can race the simulator's
# task-port setup and fail with "could not pause execution".  A short bounded
# delay keeps normal startup ordering while attaching before an early crash.
if ((!wait_for_debugger && 10#$attach_delay > 0)); then
    sleep "$attach_delay"
fi

cat > "$crash_commands" <<'LLDB'
process status
thread list
thread backtrace all -c 48
thread backtrace -c 128
register read pc lr sp fp
image list -o -f Overte
script print("OVERTE_LLDB_CRASH_CAPTURE_COMPLETE")
LLDB
chmod 0600 "$crash_commands"

# Startup tracing is useful when diagnosing an early controlled exit, but its
# repeated breakpoints materially perturb thread scheduling.  Keep it opt-in
# so the default post-import crash capture follows normal startup timing.
if ((startup_trace)); then
    cat > "$startup_commands" <<'LLDB'
breakpoint set -r 'Application::resumeAfterLoginDialogActionTaken'
breakpoint command add 1 -o 'script print("OVERTE_LLDB_TRACE resume_entry")' -o 'thread backtrace -c 24' -o 'continue'
breakpoint set -r 'Application::handleSandboxStatus'
breakpoint command add 2 -o 'script print("OVERTE_LLDB_TRACE sandbox_entry")' -o 'thread backtrace -c 24' -o 'continue'
breakpoint set -r 'QCoreApplication::(exit|quit)'
breakpoint command add 3 -o 'script print("OVERTE_LLDB_TRACE qt_exit")' -o 'thread backtrace -c 32' -o 'continue'
breakpoint set -n exit
breakpoint command add 4 -o 'script print("OVERTE_LLDB_TRACE libc_exit")' -o 'thread backtrace -c 32' -o 'continue'
breakpoint set -n _exit
breakpoint command add 5 -o 'script print("OVERTE_LLDB_TRACE posix_exit")' -o 'thread backtrace -c 32' -o 'continue'
breakpoint set -n abort
breakpoint command add 6 -o 'script print("OVERTE_LLDB_TRACE abort")' -o 'thread backtrace -c 32' -o 'continue'
breakpoint set -r 'Application::~Application'
breakpoint command add 7 -o 'script print("OVERTE_LLDB_TRACE application_destructor")' -o 'thread backtrace -c 32' -o 'continue'
LLDB
    chmod 0600 "$startup_commands"
fi

lldb_status=0
lldb_arguments=(
    --no-lldbinit \
    --no-use-colors \
    --batch \
    --attach-pid "$launch_pid" \
    -o 'settings set auto-confirm true' \
    -o "target symbols add \"$symbol_bundle\"" \
    -o 'process handle -s true -n false -p false SIGSEGV'
)
if ((startup_trace)); then
    lldb_arguments+=(--source "$startup_commands")
fi
lldb_arguments+=(
    --source-on-crash "$crash_commands" \
    -o 'process continue' \
    -o 'script print("OVERTE_LLDB_STARTUP_TRACE_COMPLETE")'
)
for ((attach_attempt = 1; attach_attempt <= 10#$attach_attempts; attach_attempt++)); do
    attach_attempts_used="$attach_attempt"
    attempt_log="$temp_root/lldb-attempt-$attach_attempt.log"
    attempt_status=0
    "$timeout_runner" "$lldb_timeout" xcrun lldb \
        "${lldb_arguments[@]}" \
        > "$attempt_log" 2>&1 || attempt_status=$?
    {
        printf '=== LLDB attach attempt %d ===\n' "$attach_attempt"
        cat "$attempt_log"
    } >> "$lldb_log"
    lldb_status="$attempt_status"

    # Retry only the known transient CoreSimulator task-port race.  All other
    # failures, a completed process, a timeout, and a captured crash are final.
    if ((attempt_status == 0)) || \
            ! grep -Fq 'could not pause execution' "$attempt_log" || \
            ((attach_attempt == 10#$attach_attempts)); then
        break
    fi
    sleep 1
done

grep -Fxq 'OVERTE_LLDB_TRACE resume_entry' "$lldb_log" && resume_trace="observed" || true
grep -Fxq 'OVERTE_LLDB_TRACE sandbox_entry' "$lldb_log" && sandbox_trace="observed" || true
if grep -Exq 'OVERTE_LLDB_TRACE (qt_exit|libc_exit|posix_exit|abort|application_destructor)' "$lldb_log" || \
        grep -Eq 'Process [0-9]+ exited with status' "$lldb_log"; then
    exit_trace="observed"
fi

if grep -Fq 'OVERTE_LLDB_CRASH_CAPTURE_COMPLETE' "$lldb_log" && \
        grep -Eq 'stop reason = (EXC_BAD_ACCESS|signal SIGSEGV)' "$lldb_log" && \
        grep -Eq 'frame #[0-9]+:' "$lldb_log"; then
    capture_status="captured_sigsegv"
    # A captured crash is diagnostic success but runtime failure.  Keep the
    # workflow red so it can never be mistaken for world acceptance evidence.
    exit 1
fi

if [[ "$resume_trace" == observed && "$exit_trace" == observed ]]; then
    capture_status="traced_process_exit"
    exit 1
fi

capture_status="incomplete"
if [[ "$lldb_status" =~ ^[0-9]+$ ]] && ((10#$lldb_status != 0)); then
    exit "$lldb_status"
fi
exit 1
