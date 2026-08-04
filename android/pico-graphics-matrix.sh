#!/usr/bin/env bash
set -euo pipefail

ADB_BIN="${ADB_BIN:-${ANDROID_SDK_ROOT:-${HOME}/Android/Sdk}/platform-tools/adb}"
PICO_SERIAL="${PICO_SERIAL:-192.168.188.75:5555}"
WARMUP="${WARMUP:-30}"
DURATION="${DURATION:-90}"
TURN_RATE="${TURN_RATE:-0}"
RESULT_DIR="${RESULT_DIR:-power-results/graphics-matrix-$(date -u +%Y%m%dT%H%M%SZ)}"
VISUAL_REFERENCE="${VISUAL_REFERENCE:-power-results/visual-check/hub-reference.png}"
MAX_CPU_TEMP_MC="${MAX_CPU_TEMP_MC:-90000}"
MAX_SKIN_TEMP_C="${MAX_SKIN_TEMP_C:-65}"

mkdir -p "$RESULT_DIR"

adb_shell() { "$ADB_BIN" -s "$PICO_SERIAL" shell "$@"; }

ORIGINAL_BRIGHTNESS="$(adb_shell gd32ipdclient_test getbrightness 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
ORIGINAL_FAN_SPEED="$(adb_shell gd32ipdclient_test getfanspeed 2>/dev/null | sed -n 's/.*= //p' | tr -d '\r')"
cleanup() {
    adb_shell am force-stop org.overte.pico >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_FAN_SPEED" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setfantestspeed "$ORIGINAL_FAN_SPEED" >/dev/null 2>&1 || true
    fi
    adb_shell gd32ipdclient_test setfantestmode 0 >/dev/null 2>&1 || true
    if [[ "$ORIGINAL_BRIGHTNESS" =~ ^[0-9]+$ ]]; then
        adb_shell gd32ipdclient_test setbrightness "$ORIGINAL_BRIGHTNESS" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT INT TERM

apply_controls() {
    adb_shell gd32ipdclient_test setfantestmode 1 >/dev/null
    adb_shell gd32ipdclient_test setfantestspeed 100 >/dev/null
    # MCU level 0 disables the backlight on this Pico. Level 1 is the lowest
    # visible setting and keeps visual validation possible during benchmarks.
    adb_shell gd32ipdclient_test setbrightness 1 >/dev/null
}

capture_and_validate_scene() {
    local image="$1" metrics="$2"
    "$ADB_BIN" -s "$PICO_SERIAL" exec-out screencap -p > "$image"
    local width height mean std rmse
    read -r width height mean std < <(identify -format '%w %h %[fx:mean] %[fx:standard_deviation]\n' "$image")
    [[ "$width" == 4320 && "$height" == 2160 ]] || {
        echo "invalid XR screenshot dimensions: ${width}x${height}" >&2; return 1;
    }
    awk -v mean="$mean" -v std="$std" 'BEGIN { exit (mean > 0.03 && std > 0.05) ? 0 : 1 }' || {
        echo "XR screenshot is blank or nearly uniform (mean=$mean std=$std)" >&2; return 1;
    }
    rmse="$({ compare -metric RMSE "$VISUAL_REFERENCE" "$image" null: 2>&1 || true; } | sed -n 's/.*(\([^)]*\)).*/\1/p')"
    awk -v rmse="$rmse" 'BEGIN { exit (rmse >= 0 && rmse < 0.45) ? 0 : 1 }' || {
        echo "XR screenshot differs too far from Hub reference (RMSE=$rmse)" >&2; return 1;
    }
    printf 'width=%s height=%s mean=%s std=%s reference_rmse=%s\n' \
        "$width" "$height" "$mean" "$std" "$rmse" > "$metrics"
}

run_case() {
    local label="$1" scale="$2" profile="$3" foveation="$4"
    shift 4
    local output="$RESULT_DIR/$label"
    mkdir -p "$output"
    printf '%s\n' "case=$label scale=$scale profile=$profile foveation=$foveation" | tee "$output/config.txt"

    apply_controls
    adb_shell setprop debug.overte.render_scale "$scale"
    adb_shell setprop debug.overte.power_profile "$profile"
    adb_shell setprop debug.overte.foveation "$foveation"
    local feature
    for feature in shadows bloom ambient_occlusion haze local_lights procedural_materials mirror_views stats simulation_hz renderable_budget_us model_update_hz; do
        adb_shell setprop "debug.overte.$feature" default
    done
    while (( $# >= 2 )); do
        adb_shell setprop "debug.overte.$1" "$2"
        printf ' override_%s=%s' "$1" "$2" >> "$output/config.txt"
        shift 2
    done
    printf '\n' >> "$output/config.txt"
    adb_shell am force-stop org.overte.pico
    "$ADB_BIN" -s "$PICO_SERIAL" logcat -c
    local start_ok=0
    for attempt in 1 2 3; do
        if timeout 60 env PICO_SERIAL="$PICO_SERIAL" ./pico-unattended-test.sh start >/dev/null; then
            start_ok=1
            break
        fi
        adb_shell am force-stop org.overte.pico
        sleep 5
    done
    if (( start_ok == 0 )); then
        echo "unable to start Pico app for $label" >&2
        return 1
    fi
    sleep 25
    local hub_ok=0 attempt
    for attempt in 1 2 3; do
        if PICO_SERIAL="$PICO_SERIAL" ./pico-unattended-test.sh hub "$(date +%s)-$attempt"; then
            hub_ok=1
            break
        fi
        sleep 10
    done
    if (( hub_ok == 0 )); then
        echo "unable to establish stable Hub scene for $label" >&2
        return 1
    fi
    capture_and_validate_scene "$output/scene-start.png" "$output/scene-start.txt"
    if awk -v turn="$TURN_RATE" 'BEGIN { exit (turn != 0) ? 0 : 1 }'; then
        adb_shell setprop debug.overte.autowalk \
            "$(date +%s)r\\|0\\|0\\|${TURN_RATE}\\|$(((WARMUP + DURATION) * 1000))"
    fi
    sleep "$WARMUP"

    local pid elapsed=0
    pid="$(adb_shell pidof org.overte.pico | tr -d '\r')"
    local starting_battery last_battery
    starting_battery="$(adb_shell dumpsys battery | sed -n 's/^  level: //p' | tr -d '\r')"
    last_battery="$starting_battery"
    printf 'epoch,cpu_pct,rss_kb,cpu0_khz,cpu4_khz,cpu7_khz,gpu_hz,cpu_temp_mC,gpu_temp_mC,skin_temp_c,fan_rpm,fan_duty,brightness,battery_pct\n' > "$output/telemetry.csv"
    while (( elapsed < DURATION )); do
        local top_line cpu rss cpu0 cpu4 cpu7 gpu ct gt skin rpm duty brightness battery
        top_line="$(adb_shell top -b -n 1 -p "$pid" 2>/dev/null | tail -n 1 | tr -d '\r')"
        cpu="$(awk '{print $9}' <<<"$top_line" | tr -d '%')"
        rss="$(awk '{print $6}' <<<"$top_line")"
        cpu0="$(adb_shell cat /sys/devices/system/cpu/cpufreq/policy0/scaling_cur_freq 2>/dev/null | tr -d '\r')"
        cpu4="$(adb_shell cat /sys/devices/system/cpu/cpufreq/policy4/scaling_cur_freq 2>/dev/null | tr -d '\r')"
        cpu7="$(adb_shell cat /sys/devices/system/cpu/cpufreq/policy7/scaling_cur_freq 2>/dev/null | tr -d '\r')"
        gpu="$(adb_shell cat /sys/class/kgsl/kgsl-3d0/gpuclk 2>/dev/null | tr -d '\r')"
        # The Pico exposes a synthetic `soc` trip-point zone fixed at 274000,
        # which is not a temperature. Only actual per-core CPU sensors are
        # valid for the thermal cutoff.
        ct="$(adb_shell 'for z in /sys/class/thermal/thermal_zone*/type; do t=$(cat "$z"); case "$t" in cpu-*-usr) cat "${z%/type}/temp";; esac; done' 2>/dev/null | sort -nr | head -1 | tr -d '\r')"
        gt="$(adb_shell 'for z in /sys/class/thermal/thermal_zone*/type; do t=$(cat "$z"); case "$t" in gpu*) cat "${z%/type}/temp";; esac; done' 2>/dev/null | sort -nr | head -1 | tr -d '\r')"
        skin="$(adb_shell dumpsys thermalservice 2>/dev/null | sed -n 's/.*mValue=\([^,]*\), mType=3.*/\1/p' | sort -nr | head -1 | tr -d '\r')"
        rpm="$(adb_shell gd32ipdclient_test getfanrpm | sed -n 's/.*= //p' | tr -d '\r')"
        duty="$(adb_shell gd32ipdclient_test getfanspeed | sed -n 's/.*= //p' | tr -d '\r')"
        brightness="$(adb_shell gd32ipdclient_test getbrightness | sed -n 's/.*= //p' | tr -d '\r')"
        battery="$(adb_shell dumpsys battery | sed -n 's/^  level: //p' | tr -d '\r')"
        if [[ "$ct" =~ ^[0-9]+$ ]] && (( ct >= MAX_CPU_TEMP_MC )); then
            echo "thermal abort: CPU ${ct} mC reached limit ${MAX_CPU_TEMP_MC} mC" >&2
            return 1
        fi
        if [[ "$skin" =~ ^[0-9]+([.][0-9]+)?$ ]] &&
                awk -v value="$skin" -v limit="$MAX_SKIN_TEMP_C" 'BEGIN { exit value >= limit ? 0 : 1 }'; then
            echo "thermal abort: skin ${skin} C reached limit ${MAX_SKIN_TEMP_C} C" >&2
            return 1
        fi
        if [[ "$battery" =~ ^[0-9]+$ && "$last_battery" =~ ^[0-9]+$ ]] && (( battery < last_battery )); then
            echo "BATTERY_DROP case=$label previous=$last_battery current=$battery start=$starting_battery" >&2
        fi
        last_battery="$battery"
        printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' "$(date +%s)" "$cpu" "$rss" "$cpu0" "$cpu4" "$cpu7" "$gpu" "$ct" "$gt" "$skin" "$rpm" "$duty" "$brightness" "$battery" >> "$output/telemetry.csv"
        sleep 5
        elapsed=$((elapsed + 5))
    done
    if awk -v turn="$TURN_RATE" 'BEGIN { exit (turn != 0) ? 0 : 1 }'; then
        adb_shell setprop debug.overte.autowalk "$(date +%s)s\\|0\\|0\\|0\\|0"
        local end_hub_ok=0
        for attempt in 1 2 3; do
            if PICO_SERIAL="$PICO_SERIAL" ./pico-unattended-test.sh hub "$(date +%s)e-$attempt"; then
                end_hub_ok=1
                break
            fi
            sleep 10
        done
        if (( end_hub_ok == 0 )); then
            echo "unable to restore stable Hub scene after $label" >&2
            return 1
        fi
    fi
    capture_and_validate_scene "$output/scene-end.png" "$output/scene-end.txt"
    "$ADB_BIN" -s "$PICO_SERIAL" logcat -d -v brief > "$output/logcat.txt"
    grep 'PICO_GPU_BENCH' "$output/logcat.txt" > "$output/gpu-bench.txt" || true
    grep -E 'PICO_(RENDER_SCALE|FOVEATION_LEVEL|POWER_PROFILE|SIMULATION_HZ|RENDERABLE_BUDGET_US|MODEL_UPDATE_HZ)' "$output/logcat.txt" > "$output/verified-config.txt" || true
}

case "${1:-screen}" in
    screen)
        run_case baseline_100 1.00 0 off
        run_case scale_085 0.85 0 off
        run_case scale_070 0.70 0 off
        run_case profile_100 1.00 1 off
        run_case profile_scale_070 0.70 1 off
        run_case foveation_high_100 1.00 0 high
        ;;
    dynamic)
        run_case dynamic_baseline_100 1.00 0 off
        run_case dynamic_scale_085 0.85 0 off
        run_case dynamic_scale_070 0.70 0 off
        run_case dynamic_foveation_high_100 1.00 0 high
        ;;
    features)
        run_case features_baseline_085 0.85 0 off
        run_case haze_off_085 0.85 0 off haze off
        run_case local_lights_off_085 0.85 0 off local_lights off
        run_case procedural_off_085 0.85 0 off procedural_materials off
        run_case mirrors_off_085 0.85 0 off mirror_views off
        run_case shadows_on_085 0.85 0 off shadows on
        run_case bloom_on_085 0.85 0 off bloom on
        run_case ambient_occlusion_on_085 0.85 0 off ambient_occlusion on
        ;;
    quality)
        run_case quality_scale_090 0.90 0 off
        run_case quality_scale_080 0.80 0 off
        run_case quality_scale_075 0.75 0 off
        run_case quality_foveation_low_085 0.85 0 low
        run_case quality_foveation_medium_085 0.85 0 medium
        run_case quality_foveation_high_085 0.85 0 high
        run_case quality_recommended_080_high 0.80 0 high
        run_case quality_repeat_085 0.85 0 off
        ;;
    stats)
        run_case stats_on_080 0.80 0 off
        run_case stats_off_080 0.80 0 off stats off
        run_case stats_on_repeat_080 0.80 0 off
        ;;
    final)
        run_case final_baseline_100_r1 1.00 0 off stats off
        run_case final_recommended_080_r1 0.80 0 off stats off
        run_case final_recommended_080_r2 0.80 0 off stats off
        run_case final_baseline_100_r2 1.00 0 off stats off
        run_case final_recommended_080_r3 0.80 0 off stats off
        run_case final_baseline_100_r3 1.00 0 off stats off
        ;;
    cpu)
        run_case cpu_breakdown_080 0.80 0 off stats off
        ;;
    cpu_matrix)
        run_case cpu_full_rate_080 0.80 0 off stats off
        run_case cpu_simulation_36hz_080 0.80 0 off stats off simulation_hz 36
        run_case cpu_simulation_24hz_080 0.80 0 off stats off simulation_hz 24
        run_case cpu_full_rate_repeat_080 0.80 0 off stats off
        ;;
    cpu_dynamic)
        run_case cpu_dynamic_full_r1_080 0.80 0 off stats off
        run_case cpu_dynamic_24hz_r1_080 0.80 0 off stats off simulation_hz 24
        run_case cpu_dynamic_full_r2_080 0.80 0 off stats off
        run_case cpu_dynamic_24hz_r2_080 0.80 0 off stats off simulation_hz 24
        ;;
    renderable_budget)
        run_case renderable_budget_2000_r1_080 0.80 0 off stats off
        run_case renderable_budget_1000_r1_080 0.80 0 off stats off renderable_budget_us 1000
        run_case renderable_budget_0500_r1_080 0.80 0 off stats off renderable_budget_us 500
        run_case renderable_budget_2000_r2_080 0.80 0 off stats off
        run_case renderable_budget_1000_r2_080 0.80 0 off stats off renderable_budget_us 1000
        run_case renderable_budget_0500_r2_080 0.80 0 off stats off renderable_budget_us 500
        ;;
    renderable_budget_resume)
        run_case renderable_budget_2000_r2b_080 0.80 0 off stats off
        run_case renderable_budget_1000_r2_080 0.80 0 off stats off renderable_budget_us 1000
        run_case renderable_budget_0500_r2_080 0.80 0 off stats off renderable_budget_us 500
        ;;
    model_updates)
        run_case model_updates_full_r1_080 0.80 0 off stats off
        run_case model_updates_30hz_r1_080 0.80 0 off stats off model_update_hz 30
        run_case model_updates_24hz_r1_080 0.80 0 off stats off model_update_hz 24
        run_case model_updates_full_r2_080 0.80 0 off stats off
        run_case model_updates_30hz_r2_080 0.80 0 off stats off model_update_hz 30
        run_case model_updates_24hz_r2_080 0.80 0 off stats off model_update_hz 24
        ;;
    *) echo "usage: $0 [screen]" >&2; exit 2 ;;
esac

printf 'results=%s\n' "$RESULT_DIR"
