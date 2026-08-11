#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command_name="${1:-help}"
shift || true

fail() {
    echo "error: $*" >&2
    exit 2
}

usage() {
    cat <<'EOF'
Usage: ./pico4-power-test.sh <command> [options]

Commands:
  doctor                 Check ADB, the device, and available battery sensors
  record [options]       Record a power-test run to CSV
  analyze <csv> [...]    Summarize and compare one or more recorded runs

Record options:
  --label NAME           Scenario name stored in every row (required)
  --duration SECONDS     Measured duration after warm-up (default: 1800)
  --warmup SECONDS       Warm-up period before recording (default: 300)
  --interval SECONDS     Sampling interval (default: 1)
  --output FILE          CSV path (default: power-results/<timestamp>-<label>.csv)
  --expected-world NAME  Required for Overte runs; abort unless this place stays connected
  --expected-position X,Y,Z
                        Abort if the avatar leaves this world position
  --position-tolerance M Maximum position error in metres (default: 2)
  --fan-speed PERCENT    Hold the fan at 0-100% during this run, then restore auto
  --brightness PERCENT   Hold MCU display brightness at 0-100%, then restore it
  --max-cpu-temp C       Abort a fixed-fan run at this CPU temperature (default: 95)
  --max-skin-temp C      Abort a fixed-fan run at this skin temperature (default: 70)
  --max-battery-temp C   Abort at this battery temperature (default: 45)
  --min-battery PERCENT  Abort below this battery level (default: 21)
  --allow-charging       Record even if USB/external power is detected
  --no-app-check         Do not require org.overte.pico to be running

Environment:
  ANDROID_SERIAL         Select a device when more than one is connected
  PICO_ADB               Override the adb executable
  ANDROID_SDK_ROOT       Android SDK containing platform-tools/adb

Examples:
  ./pico4-power-test.sh doctor
  ./pico4-power-test.sh record --label idle --duration 1800
  ./pico4-power-test.sh record --label overte-simple --expected-world overte_hub --duration 1800
  ./pico4-power-test.sh record --label fan-50 --expected-world overte_hub --fan-speed 50 --duration 300
  ./pico4-power-test.sh record --label display-50 --fan-speed 50 --brightness 50
  ./pico4-power-test.sh analyze power-results/*.csv
EOF
}

find_adb() {
    local candidate
    for candidate in \
        "${PICO_ADB:-}" \
        "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
        "${HOME}/Android/Sdk/platform-tools/adb" \
        "$(command -v adb 2>/dev/null || true)"; do
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

select_device() {
    local adb_path="$1" serial
    local -a devices

    if [[ -n "${ANDROID_SERIAL:-}" ]]; then
        serial="$ANDROID_SERIAL"
        "$adb_path" -s "$serial" get-state >/dev/null 2>&1 \
            || fail "ADB device is not available: $serial"
    else
        mapfile -t devices < <("$adb_path" devices | awk '$2 == "device" { print $1 }')
        [[ "${#devices[@]}" -gt 0 ]] \
            || fail "no authorized ADB device found; connect the Pico and allow USB debugging"
        [[ "${#devices[@]}" -eq 1 ]] \
            || fail "multiple ADB devices found; select one with ANDROID_SERIAL=<serial>"
        serial="${devices[0]}"
    fi
    printf '%s\n' "$serial"
}

adb_shell() {
    "$adb" -s "$serial" shell "$@" | tr -d '\r'
}

find_battery_dir() {
    adb_shell 'for d in /sys/class/power_supply/*; do
        [ -r "$d/type" ] || continue
        type=$(cat "$d/type" 2>/dev/null)
        if [ "$type" = "Battery" ]; then printf "%s\n" "$d"; exit 0; fi
    done
    exit 1' 2>/dev/null || true
}

read_device_info() {
    manufacturer="$(adb_shell getprop ro.product.manufacturer 2>/dev/null || true)"
    model="$(adb_shell getprop ro.product.model 2>/dev/null || true)"
    android_version="$(adb_shell getprop ro.build.version.release 2>/dev/null || true)"
    build_fingerprint="$(adb_shell getprop ro.build.fingerprint 2>/dev/null || true)"
}

read_battery_dump() {
    adb_shell dumpsys battery 2>/dev/null || true
}

battery_property() {
    local property="$1" result status low high
    result="$(adb_shell service call batteryproperties 1 i32 "$property" 2>/dev/null || true)"
    status="$(awk '$1 == "0x00000000:" { print $3; exit }' <<<"$result")"
    [[ "$status" == "00000000" ]] || return 0
    low="$(awk '$1 == "0x00000000:" { print $5; exit }' <<<"$result")"
    high="$(awk '$1 == "0x00000010:" { print $2; exit }' <<<"$result")"
    [[ "$low" =~ ^[0-9a-fA-F]{8}$ && "$high" =~ ^[0-9a-fA-F]{8}$ ]] || return 0
    if [[ "$high" == "ffffffff" || "$high" == "FFFFFFFF" ]]; then
        printf '%d\n' "$((0x$low - 0x100000000))"
    elif [[ "$high" == "00000000" ]]; then
        printf '%d\n' "$((0x$low))"
    fi
}

dump_value() {
    local dump="$1" key="$2"
    awk -F: -v key="$key" '$1 ~ "^[[:space:]]*" key "$" {
        sub(/^[[:space:]]+/, "", $2); print $2; exit
    }' <<<"$dump"
}

sysfs_value() {
    local name="$1"
    [[ -n "$battery_dir" ]] || return 0
    adb_shell "if [ -r '$battery_dir/$name' ]; then cat '$battery_dir/$name'; fi" \
        2>/dev/null || true
}

print_sensor() {
    local name="$1" value="$2" unit="$3"
    if [[ -n "$value" ]]; then
        printf '  [OK]   %-18s %s%s\n' "$name" "$value" "$unit"
    else
        printf '  [MISS] %-18s unavailable\n' "$name"
    fi
}

fan_test_active=0
brightness_test_active=0
original_brightness=""

restore_brightness_control() {
    local output actual
    if [[ "$brightness_test_active" -eq 1 ]]; then
        echo "Restoring display brightness to $original_brightness%..." >&2
        output="$(adb_shell gd32ipdclient_test setbrightness "$original_brightness" 2>&1 || true)"
        printf '%s\n' "$output" >&2
        sleep 1
        actual="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null \
            | sed -n 's/.*GetBrightness = //p' | head -n 1)"
        brightness_test_active=0
        if [[ "$actual" != "$original_brightness" ]]; then
            echo "error: display-brightness restore failed (expected $original_brightness, got $actual)" >&2
            return 1
        fi
        echo "Display brightness restored and verified at $actual%" >&2
    fi
}

restore_fan_control() {
    local output auto_state actual_state attempt
    if [[ "$fan_test_active" -eq 1 ]]; then
        echo "Restoring automatic fan control..." >&2
        output="$(adb_shell gd32ipdclient_test setfantestmode 0 2>&1 || true)"
        printf '%s\n' "$output" >&2
        for attempt in {1..10}; do
            auto_state="$(adb_shell dumpsys pxrfanservice 2>/dev/null \
                | sed -n 's/^mFanState=//p' | head -n 1)"
            actual_state="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null \
                | sed -n 's/.*GetFanSpeed = //p' | head -n 1)"
            if [[ -n "$auto_state" && "$actual_state" == "$auto_state" ]]; then
                echo "Automatic fan control verified at duty $actual_state" >&2
                fan_test_active=0
                return 0
            fi
            if [[ "$auto_state" =~ ^([0-9]|[1-9][0-9]|100)$ ]]; then
                adb_shell gd32ipdclient_test setfanspeed "$auto_state" >/dev/null 2>&1 || true
            fi
            sleep 1
        done
        fan_test_active=0
        echo "error: automatic fan control could not be verified after 10 seconds" >&2
        return 1
    fi
}

restore_test_controls() {
    local status=0
    restore_brightness_control || status=1
    restore_fan_control || status=1
    return "$status"
}

set_test_brightness() {
    local brightness="$1" output actual
    original_brightness="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null \
        | sed -n 's/.*GetBrightness = //p' | head -n 1)"
    [[ "$original_brightness" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
        || fail "could not read the current Pico display brightness"
    output="$(adb_shell gd32ipdclient_test setbrightness "$brightness" 2>&1)"
    [[ "$output" == *success* ]] || fail "could not set Pico display brightness: $output"
    brightness_test_active=1
    trap restore_test_controls EXIT
    trap 'exit 130' INT TERM HUP
    sleep 1
    actual="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null \
        | sed -n 's/.*GetBrightness = //p' | head -n 1)"
    [[ "$actual" == "$brightness" ]] \
        || fail "display-brightness verification failed (requested $brightness, got $actual)"
    echo "Display brightness fixed at $brightness% for this run"
}

set_test_fan_speed() {
    local speed="$1" output actual
    adb_shell 'command -v gd32ipdclient_test >/dev/null' \
        || fail "Pico fan-control utility is unavailable"
    output="$(adb_shell gd32ipdclient_test setfantestmode 1 2>&1)"
    [[ "$output" == *success* ]] || fail "could not enter Pico fan test mode: $output"
    fan_test_active=1
    trap restore_test_controls EXIT
    trap 'exit 130' INT TERM HUP
    output="$(adb_shell gd32ipdclient_test setfantestspeed "$speed" 2>&1)"
    [[ "$output" == *success* ]] || fail "could not set Pico fan speed: $output"
    sleep 2
    output="$(adb_shell gd32ipdclient_test getfanspeed 2>&1)"
    actual="$(sed -n 's/.*GetFanSpeed = \([0-9][0-9]*\).*/\1/p' <<<"$output")"
    [[ "$actual" == "$speed" ]] \
        || fail "fan-speed verification failed (requested $speed, response: $output)"
    echo "Fan fixed at $speed% for this run"
    adb_shell gd32ipdclient_test getfaninfo
}

doctor() {
    local dump level voltage current charge temperature status plugged telemetry
    local -a telemetry_fields

    adb="$(find_adb)" || fail "ADB not found; set PICO_ADB or ANDROID_SDK_ROOT"
    serial="$(select_device "$adb")"
    battery_dir="$(find_battery_dir)"
    read_device_info
    dump="$(read_battery_dump)"

    level="$(sysfs_value capacity)"
    [[ -n "$level" ]] || level="$(dump_value "$dump" level)"
    voltage="$(sysfs_value voltage_now)"
    [[ -n "$voltage" ]] || voltage="$(dump_value "$dump" voltage)"
    current="$(sysfs_value current_now)"
    [[ -n "$current" ]] || current="$(battery_property 2)"
    charge="$(sysfs_value charge_counter)"
    [[ -n "$charge" ]] || charge="$(sysfs_value charge_now)"
    [[ -n "$charge" ]] || charge="$(battery_property 1)"
    [[ -n "$charge" ]] || charge="$(dump_value "$dump" 'Charge counter')"
    temperature="$(sysfs_value temp)"
    [[ -n "$temperature" ]] || temperature="$(dump_value "$dump" temperature)"
    status="$(sysfs_value status)"
    [[ -n "$status" ]] || status="$(dump_value "$dump" status)"
    if grep -Eq '^[[:space:]]*(AC|USB|Wireless) powered:[[:space:]]*true' <<<"$dump"; then
        plugged=1
    else
        plugged=0
    fi

    echo "Pico 4 power measurement environment"
    echo
    echo "Host:"
    echo "  [OK]   ADB                $adb"
    echo "  [OK]   Python             $(python3 --version 2>&1)"
    echo
    echo "Device:"
    echo "  [OK]   Serial             $serial"
    echo "  [INFO] Product            ${manufacturer:-unknown} ${model:-unknown}"
    echo "  [INFO] Android            ${android_version:-unknown}"
    echo "  [INFO] Battery sysfs      ${battery_dir:-not exposed}"
    echo
    echo "Sensors (raw Android values):"
    print_sensor "level" "$level" " %"
    print_sensor "voltage" "$voltage" ""
    print_sensor "current_now" "$current" " uA"
    print_sensor "charge_counter" "$charge" " uAh"
    print_sensor "temperature" "$temperature" " (0.1 C)"
    print_sensor "status" "$status" ""
    print_sensor "plugged" "$plugged" ""
    echo
    if [[ -n "$voltage" && -n "$current" ]]; then
        echo "Instantaneous power can be estimated from voltage_now and current_now."
    elif [[ -n "$voltage" && -n "$charge" ]]; then
        echo "Average energy can be estimated from voltage and charge-counter change."
    else
        echo "Only a coarse battery-level discharge test is available on this firmware."
    fi

    telemetry="$(sample_device)"
    IFS=',' read -r -a telemetry_fields <<<"$telemetry"
    echo
    echo "Display and performance telemetry:"
    print_sensor "VR brightness" "${telemetry_fields[9]:-}" " / 255"
    print_sensor "panel brightness" "${telemetry_fields[10]:-}" " / 255"
    print_sensor "auto brightness" "${telemetry_fields[11]:-}" ""
    print_sensor "refresh rate" "${telemetry_fields[12]:-}" " Hz"
    print_sensor "fan state" "${telemetry_fields[13]:-}" " (vendor control value; not RPM)"
    print_sensor "max CPU temp" "${telemetry_fields[14]:-}" " mC"
    print_sensor "max GPU temp" "${telemetry_fields[15]:-}" " mC"
    print_sensor "skin temp" "${telemetry_fields[16]:-}" " C"
    print_sensor "thermal status" "${telemetry_fields[17]:-}" ""
    print_sensor "CPU policy0" "${telemetry_fields[18]:-}" " kHz"
    print_sensor "CPU policy4" "${telemetry_fields[19]:-}" " kHz"
    print_sensor "CPU policy7" "${telemetry_fields[20]:-}" " kHz"
    print_sensor "GPU clock" "${telemetry_fields[21]:-}" " Hz"
    print_sensor "fan speed" "${telemetry_fields[22]:-}" " RPM"
    print_sensor "fan duty" "${telemetry_fields[23]:-}" " / 100"
    print_sensor "MCU brightness" "${telemetry_fields[24]:-}" " / 100"
}

sample_device() {
    # Keep sampling overhead low: collect everything in one ADB shell round trip.
    adb_shell "battery_dir='$battery_dir';
        battery_dump=\"\$(dumpsys battery 2>/dev/null)\";
        sysfs_read() { [ -n \"\$battery_dir\" ] && [ -r \"\$battery_dir/\$1\" ] && cat \"\$battery_dir/\$1\"; };
        dump_read() { printf '%s\\n' \"\$battery_dump\" | sed -n \"s/^[[:space:]]*\$1:[[:space:]]*//p\" | head -n 1; };
        battery_property() {
            result=\"\$(service call batteryproperties 1 i32 \"\$1\" 2>/dev/null)\";
            status=\"\$(printf '%s\\n' \"\$result\" | awk '\$1 == \"0x00000000:\" { print \$3; exit }')\";
            [ \"\$status\" = 00000000 ] || return;
            low=\"\$(printf '%s\\n' \"\$result\" | awk '\$1 == \"0x00000000:\" { print \$5; exit }')\";
            high=\"\$(printf '%s\\n' \"\$result\" | awk '\$1 == \"0x00000010:\" { print \$2; exit }')\";
            case \"\$high\" in
                ffffffff|FFFFFFFF) echo \"\$((0x\$low - 0x100000000))\" ;;
                00000000) echo \"\$((0x\$low))\" ;;
            esac;
        };
        level=\"\$(sysfs_read capacity)\"; [ -n \"\$level\" ] || level=\"\$(dump_read level)\";
        voltage=\"\$(sysfs_read voltage_now)\"; [ -n \"\$voltage\" ] || voltage=\"\$(dump_read voltage)\";
        current=\"\$(sysfs_read current_now)\"; [ -n \"\$current\" ] || current=\"\$(battery_property 2)\";
        charge=\"\$(sysfs_read charge_counter)\"; [ -n \"\$charge\" ] || charge=\"\$(sysfs_read charge_now)\"; [ -n \"\$charge\" ] || charge=\"\$(battery_property 1)\"; [ -n \"\$charge\" ] || charge=\"\$(dump_read 'Charge counter')\";
        temperature=\"\$(sysfs_read temp)\"; [ -n \"\$temperature\" ] || temperature=\"\$(dump_read temperature)\";
        status=\"\$(sysfs_read status)\"; [ -n \"\$status\" ] || status=\"\$(dump_read status)\";
        if printf '%s\\n' \"\$battery_dump\" | grep -Eq '^[[:space:]]*(AC|USB|Wireless) powered:[[:space:]]*true'; then plugged=1; else plugged=0; fi;
        app_pid=\"\$(pidof org.overte.pico 2>/dev/null | awk '{ print \$1 }')\";
        power_dump=\"\$(dumpsys power 2>/dev/null)\";
        screen_state=\"\$(printf '%s\\n' \"\$power_dump\" | awk -F= '/mWakefulness=/{print \$2; exit} /Display Power: state=/{print \$2; exit}' | tr -d '[:space:]')\";
        brightness_vr=\"\$(settings get system screen_brightness_for_vr 2>/dev/null)\";
        auto_brightness=\"\$(settings get global pxr_auto_brightness_enable 2>/dev/null)\";
        [ \"\$auto_brightness\" != null ] || auto_brightness=\"\$(settings get system screen_brightness_mode 2>/dev/null)\";
        display_dump=\"\$(dumpsys display 2>/dev/null)\";
        brightness_actual=\"\$(printf '%s\\n' \"\$display_dump\" | sed -n 's/^[[:space:]]*mScreenBrightness=//p' | head -n 1)\";
        active_mode=\"\$(printf '%s\\n' \"\$display_dump\" | sed -n 's/^[[:space:]]*mActiveModeId=//p' | head -n 1)\";
        refresh_hz=\"\$(printf '%s\\n' \"\$display_dump\" | sed -n \"s/.*{id=\$active_mode, width=[^,]*, height=[^,]*, fps=\\([0-9.]*\\)}.*/\\1/p\" | head -n 1)\";
        fan_dump=\"\$(dumpsys pxrfanservice 2>/dev/null)\";
        fan_state=\"\$(printf '%s\\n' \"\$fan_dump\" | sed -n 's/^mFanState=//p' | head -n 1)\";
        cpu_temp_max=\"\$(printf '%s\\n' \"\$fan_dump\" | awk '/^Cpu Temperature/ { for (i=1; i<=NF; i++) if (\$i ~ /^temp=/) { sub(/^temp=/, \"\", \$i); sub(/,.*/, \"\", \$i); if (\$i+0 > max) max=\$i+0 } } END { if (max) print max }')\";
        gpu_temp_max=\"\$(printf '%s\\n' \"\$fan_dump\" | awk '/^Gpu Temperature/ { for (i=1; i<=NF; i++) if (\$i ~ /^temp=/) { sub(/^temp=/, \"\", \$i); sub(/,.*/, \"\", \$i); if (\$i+0 > max) max=\$i+0 } } END { if (max) print max }')\";
        thermal_dump=\"\$(dumpsys thermalservice 2>/dev/null)\";
        thermal_status=\"\$(printf '%s\\n' \"\$thermal_dump\" | sed -n 's/^[[:space:]]*Thermal Status:[[:space:]]*//p' | head -n 1)\";
        skin_temp=\"\$(printf '%s\\n' \"\$thermal_dump\" | sed -n 's/.*mValue=\\([^,]*\\).*mName=skin,.*/\\1/p' | tail -n 1)\";
        cpu0_khz=\"\$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null)\";
        cpu4_khz=\"\$(cat /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq 2>/dev/null)\";
        cpu7_khz=\"\$(cat /sys/devices/system/cpu/cpufreq/policy7/scaling_cur_freq 2>/dev/null)\";
        gpu_hz=\"\$(cat /sys/class/kgsl/kgsl-3d0/gpuclk 2>/dev/null)\";
        fan_rpm=\"\$(gd32ipdclient_test getfanrpm 2>/dev/null | sed -n 's/.*GetFanRPM = //p' | head -n 1)\";
        fan_duty=\"\$(gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*GetFanSpeed = //p' | head -n 1)\";
        mcu_brightness=\"\$(gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*GetBrightness = //p' | head -n 1)\";
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\\n' \\
            \"\$level\" \"\$voltage\" \"\$current\" \"\$charge\" \"\$temperature\" \"\$status\" \"\$plugged\" \"\$app_pid\" \"\$screen_state\" \\
            \"\$brightness_vr\" \"\$brightness_actual\" \"\$auto_brightness\" \"\$refresh_hz\" \"\$fan_state\" \"\$cpu_temp_max\" \"\$gpu_temp_max\" \\
            \"\$skin_temp\" \"\$thermal_status\" \"\$cpu0_khz\" \"\$cpu4_khz\" \"\$cpu7_khz\" \"\$gpu_hz\" \"\$fan_rpm\" \"\$fan_duty\" \"\$mcu_brightness\"" \
        2>/dev/null || true
}

csv_safe() {
    printf '%s' "$1" | tr ',\r\n' ';  '
}

foreground_package() {
    adb_shell dumpsys activity activities 2>/dev/null \
        | sed -n 's/.*mResumedActivity:.* u0 \([^/ ]*\).*/\1/p' \
        | head -n 1
}

validate_xr_focus() {
    local stage="$1" active_package boundary_ready guardian_vst
    active_package="$(foreground_package)"
    boundary_ready="$(adb_shell getprop sys.pxr.boundary.ready 2>/dev/null)"
    guardian_vst="$(adb_shell getprop sys.guardian.vst.status 2>/dev/null)"
    [[ "$active_package" == "org.overte.pico" ]] || {
        echo "error: Overte lost XR focus during $stage (active: ${active_package:-unknown})" >&2
        return 1
    }
    [[ "$boundary_ready" != "0" && "$guardian_vst" != "1" ]] || {
        echo "error: Pico Guardian/Seethrough is active during $stage" \
            "(boundary_ready=${boundary_ready:-unknown}, guardian_vst=${guardian_vst:-unknown})" >&2
        return 1
    }
}

validate_world() {
    local stage="$1" status status_epoch connected place domain_id x y z now
    status="$(adb_shell run-as org.overte.pico cat cache/world-status 2>/dev/null || true)"
    IFS='|' read -r status_epoch connected place domain_id x y z <<<"$status"
    now="$(date +%s)"
    if [[ ! "$status_epoch" =~ ^[0-9]+$ ]] || (( now - status_epoch < -5 || now - status_epoch > 5 )); then
        echo "error: Overte world status is missing or stale during $stage (status: ${status:-missing})" >&2
        return 1
    fi
    if [[ "$connected" != "1" ]]; then
        echo "error: Overte is not connected to a world during $stage (status: ${status:-missing})" >&2
        return 1
    fi
    if [[ "${place,,}" != "${expected_world,,}" ]]; then
        echo "error: wrong Overte world during $stage (expected '$expected_world', got '${place:-unknown}', domain ${domain_id:-unknown})" >&2
        return 1
    fi
    if [[ -n "$expected_position" ]]; then
        IFS=',' read -r expected_x expected_y expected_z <<<"$expected_position"
        if ! awk -v x="$x" -v y="$y" -v z="$z" \
            -v ex="$expected_x" -v ey="$expected_y" -v ez="$expected_z" \
            -v tolerance="$position_tolerance" 'BEGIN {
                if (x == "" || y == "" || z == "") exit 1;
                dx=x-ex; dy=y-ey; dz=z-ez;
                exit (dx*dx + dy*dy + dz*dz <= tolerance*tolerance) ? 0 : 1;
            }'; then
            echo "error: avatar left expected test position during $stage (expected $expected_position +/- ${position_tolerance}m, got ${x:-?},${y:-?},${z:-?})" >&2
            return 1
        fi
    fi
}

record() {
    local label="" duration=1800 warmup=300 interval=1 output=""
    local allow_charging=0 app_check=1 fan_speed="" brightness="" max_cpu_temp=95 max_skin_temp=70
    local max_battery_temp=45 min_battery=21 arg dump plugged start_epoch now_epoch elapsed next_sample
    local timestamp device_row cpu_temp_raw skin_temp_raw battery_temp_raw battery_level aborted=0
    local invalid_output
    local expected_pid="" current_pid
    local power_profile foveation
    local expected_world="" expected_position="" position_tolerance="2" expected_x expected_y expected_z
    local -a sample_fields

    while [[ "$#" -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --label) [[ "$#" -ge 2 ]] || fail "--label requires a value"; label="$2"; shift 2 ;;
            --duration) [[ "$#" -ge 2 ]] || fail "--duration requires a value"; duration="$2"; shift 2 ;;
            --warmup) [[ "$#" -ge 2 ]] || fail "--warmup requires a value"; warmup="$2"; shift 2 ;;
            --interval) [[ "$#" -ge 2 ]] || fail "--interval requires a value"; interval="$2"; shift 2 ;;
            --output) [[ "$#" -ge 2 ]] || fail "--output requires a value"; output="$2"; shift 2 ;;
            --expected-world) [[ "$#" -ge 2 ]] || fail "--expected-world requires a value"; expected_world="$2"; shift 2 ;;
            --expected-position) [[ "$#" -ge 2 ]] || fail "--expected-position requires a value"; expected_position="$2"; shift 2 ;;
            --position-tolerance) [[ "$#" -ge 2 ]] || fail "--position-tolerance requires a value"; position_tolerance="$2"; shift 2 ;;
            --fan-speed) [[ "$#" -ge 2 ]] || fail "--fan-speed requires a value"; fan_speed="$2"; shift 2 ;;
            --brightness) [[ "$#" -ge 2 ]] || fail "--brightness requires a value"; brightness="$2"; shift 2 ;;
            --max-cpu-temp) [[ "$#" -ge 2 ]] || fail "--max-cpu-temp requires a value"; max_cpu_temp="$2"; shift 2 ;;
            --max-skin-temp) [[ "$#" -ge 2 ]] || fail "--max-skin-temp requires a value"; max_skin_temp="$2"; shift 2 ;;
            --max-battery-temp) [[ "$#" -ge 2 ]] || fail "--max-battery-temp requires a value"; max_battery_temp="$2"; shift 2 ;;
            --min-battery) [[ "$#" -ge 2 ]] || fail "--min-battery requires a value"; min_battery="$2"; shift 2 ;;
            --allow-charging) allow_charging=1; shift ;;
            --no-app-check) app_check=0; shift ;;
            -h|--help) usage; return ;;
            *) fail "unknown record option: $arg" ;;
        esac
    done

    [[ -n "$label" ]] || fail "record requires --label NAME"
    [[ "$label" =~ ^[A-Za-z0-9._-]+$ ]] \
        || fail "label may only contain letters, numbers, dots, underscores, and hyphens"
    [[ "$duration" =~ ^[1-9][0-9]*$ ]] || fail "duration must be a positive integer"
    [[ "$warmup" =~ ^[0-9]+$ ]] || fail "warmup must be a non-negative integer"
    [[ "$interval" =~ ^[1-9][0-9]*$ ]] || fail "interval must be a positive integer"
    [[ -z "$fan_speed" || "$fan_speed" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
        || fail "fan speed must be an integer from 0 through 100"
    [[ -z "$brightness" || "$brightness" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
        || fail "brightness must be an integer from 0 through 100"
    [[ "$max_cpu_temp" =~ ^[1-9][0-9]*$ ]] || fail "max CPU temperature must be a positive integer"
    [[ "$max_skin_temp" =~ ^[1-9][0-9]*$ ]] || fail "max skin temperature must be a positive integer"
    [[ "$max_battery_temp" =~ ^[1-9][0-9]*$ ]] || fail "max battery temperature must be a positive integer"
    [[ "$min_battery" =~ ^([0-9]|[1-9][0-9]|100)$ ]] \
        || fail "minimum battery level must be an integer from 0 through 100"
    [[ "$position_tolerance" =~ ^[0-9]+([.][0-9]+)?$ ]] \
        || fail "position tolerance must be a non-negative number"
    if [[ -n "$expected_position" ]]; then
        [[ "$expected_position" =~ ^-?[0-9]+([.][0-9]+)?,-?[0-9]+([.][0-9]+)?,-?[0-9]+([.][0-9]+)?$ ]] \
            || fail "expected position must use X,Y,Z numeric form"
    fi

    adb="$(find_adb)" || fail "ADB not found; set PICO_ADB or ANDROID_SDK_ROOT"
    serial="$(select_device "$adb")"
    battery_dir="$(find_battery_dir)"
    read_device_info
    power_profile="$(adb_shell getprop debug.overte.power_profile 2>/dev/null || true)"
    foveation="$(adb_shell getprop debug.overte.foveation 2>/dev/null || true)"
    power_profile="$(csv_safe "${power_profile:-off}")"
    foveation="$(csv_safe "${foveation:-off}")"
    manufacturer="$(csv_safe "$manufacturer")"
    model="$(csv_safe "$model")"
    android_version="$(csv_safe "$android_version")"
    build_fingerprint="$(csv_safe "$build_fingerprint")"

    if [[ "$app_check" -eq 1 ]]; then
        expected_pid="$(adb_shell pidof org.overte.pico 2>/dev/null | awk '{ print $1 }')"
        [[ -n "$expected_pid" ]] \
            || fail "org.overte.pico is not running; start it or use --no-app-check for a baseline"
        [[ -n "$expected_world" ]] \
            || fail "Overte runs require --expected-world NAME to guard against testing the wrong world"
        validate_xr_focus "recording setup" || fail "Overte XR focus validation failed"
    fi

    dump="$(read_battery_dump)"
    if grep -Eq '^[[:space:]]*(AC|USB|Wireless) powered:[[:space:]]*true' <<<"$dump"; then
        plugged=1
    else
        plugged=0
    fi
    if [[ "$allow_charging" -eq 0 && -n "$plugged" && "$plugged" != "0" ]]; then
        fail "external power is detected (plugged=$plugged); disconnect it or use --allow-charging"
    fi

    if [[ -n "$fan_speed" ]]; then
        set_test_fan_speed "$fan_speed"
    fi
    if [[ -n "$brightness" ]]; then
        set_test_brightness "$brightness"
    fi

    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    if [[ -z "$output" ]]; then
        output="$script_dir/power-results/${timestamp}-${label}.csv"
    fi
    mkdir -p -- "$(dirname -- "$output")"
    [[ ! -e "$output" ]] || fail "output file already exists: $output"

    echo "Device: ${manufacturer:-unknown} ${model:-unknown}"
    echo "Scenario: $label"
    echo "Overte power profile: $power_profile"
    echo "OpenXR foveation: $foveation"
    echo "Battery sysfs: ${battery_dir:-not readable}; using Android battery properties and dumpsys fallbacks"
    if [[ "$warmup" -gt 0 ]]; then
        echo "Warming up for $warmup seconds; keep the test scene active..."
        elapsed=0
        while ((elapsed < warmup)); do
            sleep "$((warmup - elapsed < 5 ? warmup - elapsed : 5))"
            elapsed=$((elapsed + (warmup - elapsed < 5 ? warmup - elapsed : 5)))
            if [[ "$app_check" -eq 1 ]]; then
                current_pid="$(adb_shell pidof org.overte.pico 2>/dev/null | awk '{ print $1 }')"
                [[ "$current_pid" == "$expected_pid" ]] \
                    || fail "Overte restarted during warm-up (expected PID $expected_pid, active: ${current_pid:-none})"
                validate_xr_focus "warm-up" || fail "Overte XR focus validation failed"
                validate_world "warm-up" || fail "world validation failed"
            fi
        done
    fi

    printf '%s\n' \
        'timestamp_utc,epoch_s,elapsed_s,label,manufacturer,model,android_version,build_fingerprint,battery_dir,power_profile,foveation,level_pct,voltage_raw,current_raw,charge_raw,temp_raw,status,plugged,app_pid,screen_state,brightness_vr,brightness_actual,auto_brightness,refresh_hz,fan_state,cpu_temp_max_mC,gpu_temp_max_mC,skin_temp_c,thermal_status,cpu_policy0_khz,cpu_policy4_khz,cpu_policy7_khz,gpu_hz,fan_rpm,fan_duty,mcu_brightness' \
        >"$output"

    echo "Recording $duration seconds to $output"
    start_epoch="$(date +%s)"
    next_sample="$start_epoch"
    while true; do
        now_epoch="$(date +%s)"
        elapsed=$((now_epoch - start_epoch))
        [[ "$elapsed" -le "$duration" ]] || break
        device_row="$(sample_device)"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$now_epoch" "$elapsed" "$label" \
            "$manufacturer" "$model" "$android_version" \
            "$build_fingerprint" "$battery_dir" "$power_profile" "$foveation" "$device_row" >>"$output"
        IFS=',' read -r -a sample_fields <<<"$device_row"
        battery_level="${sample_fields[0]:-}"
        if [[ "$battery_level" =~ ^[0-9]+$ ]] && ((battery_level < min_battery)); then
            echo "error: battery validity threshold crossed (${battery_level}% < ${min_battery}%)" >&2
            aborted=1
        elif [[ "$app_check" -eq 1 ]]; then
            current_pid="${sample_fields[7]:-}"
            if [[ "$current_pid" != "$expected_pid" ]]; then
                echo "error: Overte restarted during measurement (expected PID $expected_pid, active: ${current_pid:-none})" >&2
                aborted=1
            elif ! validate_xr_focus "measurement at ${elapsed}s"; then
                aborted=1
            elif ! validate_world "measurement at ${elapsed}s"; then
                aborted=1
            fi
        fi
        if [[ -n "$fan_speed" ]]; then
            battery_temp_raw="${sample_fields[4]:-0}"
            cpu_temp_raw="${sample_fields[14]:-0}"
            skin_temp_raw="${sample_fields[16]:-0}"
            if [[ "$battery_temp_raw" =~ ^[0-9]+$ ]] \
                && ((battery_temp_raw >= max_battery_temp * 10)); then
                echo "error: battery temperature limit reached (${battery_temp_raw} tenths C)" >&2
                aborted=1
            elif [[ "$cpu_temp_raw" =~ ^[0-9]+$ ]] \
                && ((cpu_temp_raw >= max_cpu_temp * 1000)); then
                echo "error: CPU temperature limit reached (${cpu_temp_raw} mC)" >&2
                aborted=1
            elif [[ "${skin_temp_raw%%.*}" =~ ^[0-9]+$ ]] \
                && ((10#${skin_temp_raw%%.*} >= max_skin_temp)); then
                echo "error: skin temperature limit reached (${skin_temp_raw} C)" >&2
                aborted=1
            fi
        fi
        [[ "$aborted" -eq 0 ]] || break
        next_sample=$((next_sample + interval))
        now_epoch="$(date +%s)"
        if [[ "$next_sample" -gt "$now_epoch" ]]; then
            sleep "$((next_sample - now_epoch))"
        else
            next_sample="$now_epoch"
        fi
    done
    restore_test_controls
    trap - EXIT INT TERM HUP
    echo "Recorded $(($(wc -l <"$output") - 1)) samples"
    if [[ "$aborted" -ne 0 ]]; then
        invalid_output="${output}.invalid"
        [[ ! -e "$invalid_output" ]] \
            || invalid_output="${output}.$(date -u +%Y%m%dT%H%M%SZ).invalid"
        mv -- "$output" "$invalid_output"
        echo "Invalid partial recording retained at $invalid_output; analysis skipped" >&2
        return 3
    fi
    python3 "$script_dir/tools/analyze-pico4-power.py" "$output"
}

analyze() {
    [[ "$#" -gt 0 ]] || fail "analyze requires at least one CSV file"
    python3 "$script_dir/tools/analyze-pico4-power.py" "$@"
}

case "$command_name" in
    doctor)
        [[ "$#" -eq 0 ]] || fail "doctor does not accept options"
        if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
            exec "$script_dir/pico-device-lock.sh" run -- "$0" doctor
        fi
        doctor
        ;;
    record)
        if [[ "${PICO_DEVICE_LOCK_HELD:-0}" != 1 ]]; then
            exec "$script_dir/pico-device-lock.sh" run -- "$0" record "$@"
        fi
        record "$@"
        ;;
    analyze) analyze "$@" ;;
    help|-h|--help) usage ;;
    *) fail "unknown command: $command_name" ;;
esac
