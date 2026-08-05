#!/usr/bin/env bash
set -euo pipefail

STATE_DIR="${MOCK_MIC_STATE_DIR:?MOCK_MIC_STATE_DIR is required}"
COMMAND_LOG="$STATE_DIR/commands.log"
printf '%s\n' "$*" >>"$COMMAND_LOG"

if [[ "${1:-}" == devices ]]; then
    printf 'List of devices attached\n'
    case "${MOCK_DEVICE_COUNT:-1}" in
        0) ;;
        1) printf 'mock-microphone-device\tdevice\n' ;;
        2) printf 'mock-microphone-device\tdevice\nmock-other-device\tdevice\n' ;;
        *) printf 'unsupported MOCK_DEVICE_COUNT\n' >&2; exit 2 ;;
    esac
    exit 0
fi

if [[ "${1:-}" == -s && $# -ge 3 ]]; then
    shift 2
fi

source_name="voicecommunication"
if [[ -s "$STATE_DIR/source" ]]; then
    source_name="$(<"$STATE_DIR/source")"
fi
case "$source_name" in
    voicecommunication)
        audio_source_id=7
        audio_source_label=VOICE_COMMUNICATION
        ;;
    voicerecognition)
        audio_source_id=6
        audio_source_label=VOICE_RECOGNITION
        ;;
    mic)
        audio_source_id=1
        audio_source_label=MIC
        ;;
    camcorder)
        audio_source_id=5
        audio_source_label=CAMCORDER
        ;;
    *)
        audio_source_id=1
        audio_source_label=MIC
        ;;
esac
if [[ "${MOCK_AUDIO_SOURCE_MISMATCH:-0}" == 1 ]]; then
    audio_source_id=1
    audio_source_label=MIC
fi

if [[ "${1:-}" == logcat ]]; then
    if [[ " $* " == *' -c '* ]]; then
        exit 0
    fi
    if [[ " $* " == *' -t 250 '* && " $* " != *' OverteMicTest '* ]]; then
        printf 'I/Interface: PICO_MIC_INPUT device "%s" rate 48000 channels 1 sampleBits 16\n' \
            "$source_name"
        printf 'I/Interface: PICO_MIC_CAPTURE_COMPLETE mock-cache/pico-mic-input.wav\n'
        exit 0
    fi
    start_marker="PICO_MIC_MEASUREMENT_START_${source_name}"
    end_marker="PICO_MIC_MEASUREMENT_END_${source_name}"
    printf 'I/OverteMicTest: %s\n' "$start_marker"
    printf 'I/Interface: PICO_MIC_LEVEL device "%s" frames 48000 mean 2 peak 5\n' "$source_name"
    printf 'I/Interface: PICO_MIC_GATE device "%s" blocks 100 openBlocks 30\n' "$source_name"
    printf 'I/Interface: PICO_MIC_TRANSPORT capturedFrames 48000 processedFrames 48000 droppedFrames 0 backlogFrames 0 peakBacklogFrames 960 drains 100\n'
    printf 'I/OverteMicTest: %s\n' "$end_marker"
    exit 0
fi

if [[ "${1:-}" == exec-out && "${2:-}" == run-as && \
      "${4:-}" == cat && "${5:-}" == cache/pico-mic-input.wav ]]; then
    printf 'RIFFmock-pico-microphone-wave-data'
    exit 0
fi

[[ "${1:-}" == shell ]] || { printf 'unexpected mock adb command\n' >&2; exit 2; }
shift
command_line="$*"

case "$command_line" in
    'dumpsys pxrfanservice')
        printf 'mFanState=45\n'
        printf 'Cpu Temperature sensor temp=65000, status=ok\n'
        printf 'Gpu Temperature sensor temp=60000, status=ok\n'
        ;;
    'dumpsys media.audio_flinger')
        printf 'Input thread mock\n'
        printf '  Audio source: %s (%s)\n' "$audio_source_id" "$audio_source_label"
        if [[ "$audio_source_id" == 7 ]]; then
            printf '    - name: Acoustic Echo Canceler\n'
            printf '    - name: Noise Suppression\n'
        fi
        ;;
    'gd32ipdclient_test getfanspeed')
        printf 'GetFanSpeed = 45\n'
        ;;
    'gd32ipdclient_test getfanrpm')
        printf 'GetFanRPM = 7000\n'
        ;;
    'gd32ipdclient_test setfantestmode '*|'gd32ipdclient_test setfantestspeed '*)
        printf 'success\n'
        ;;
    'run-as org.overte.pico ls cache/pico-mic-input.wav')
        exit 0
        ;;
    'run-as org.overte.pico rm -f cache/pico-mic-input.wav')
        exit 0
        ;;
    'setprop debug.overte.audio_input '*)
        printf '%s' "${command_line##* }" >"$STATE_DIR/source"
        ;;
    'log -t OverteMicTest '*)
        ;;
    setprop\ *|input\ *|am\ *)
        ;;
    *)
        printf 'unexpected mock adb shell command: %s\n' "$command_line" >&2
        exit 2
        ;;
esac
