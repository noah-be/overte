#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
android_dir="$(cd -- "$script_dir/../.." && pwd)"
source_file="$android_dir/../interface/src/Application_Setup.cpp"
benchmark="$script_dir/phone-graphics-benchmark.sh"

grep -q 'const float gpuFrameTime.*getFrameTimerGPUAverage' "$source_file"
grep -q 'const float batchFrameTime.*getFrameTimerBatchAverage' "$source_file"
grep -q '#if defined(ANDROID_APP_PHONE_INTERFACE)' "$source_file"
grep -q '"render_gpu_ms=%.2f render_batch_ms=%.2f"' "$source_file"
grep -q 'static_cast<double>(gpuFrameTime)' "$source_file"
grep -q 'static_cast<double>(batchFrameTime)' "$source_file"
grep -q 'render_timing_metrics_valid' "$benchmark"
grep -q 'valid_finite_decimal "$render_gpu_ms"' "$benchmark"

printf 'Phone render timing telemetry static checks passed.\n'
