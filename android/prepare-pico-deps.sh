#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
qt_source_dir="${PICO_QT_SOURCE_DIR:-}"
qt_build_dir="${PICO_QT_BUILD_DIR:-}"
tbb_package_dir="${PICO_TBB_PACKAGE_DIR:-}"
draco_package_dir="${PICO_DRACO_PACKAGE_DIR:-}"
runtime_dir="${script_dir}/shared/runtime-overrides/arm64-v8a"
host_tools_dir="${script_dir}/pico-host-tools"
precompiled_dir="${script_dir}/pico-precompiled-compat"
patch_file="${script_dir}/conan/patches/qt-pico-android-runtime.patch"
prebuilt_marker="${runtime_dir}/.prebuilt-runtime"

require_dir() {
    local variable_name="$1"
    local directory="$2"
    if [[ -z "$directory" || ! -d "$directory" ]]; then
        echo "${variable_name} must point to an existing directory" >&2
        exit 2
    fi
}

require_file() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "required file not found: ${file}" >&2
        exit 2
    fi
}

require_dir PICO_DRACO_PACKAGE_DIR "$draco_package_dir"

draco_include="$draco_package_dir/include"
draco_library="$draco_package_dir/lib/libdraco.a"

require_file "$draco_library"
require_dir PICO_DRACO_PACKAGE_DIR "$draco_include"

if [[ -f "$prebuilt_marker" ]]; then
    echo "Using downloaded Pico runtime libraries"
    for file in \
        "$runtime_dir/libQt5Core_arm64-v8a.so" \
        "$runtime_dir/libplugins_platforms_qtforandroid_arm64-v8a.so" \
        "$runtime_dir/libtbb.so"; do
        require_file "$file"
    done
else
    require_dir PICO_QT_SOURCE_DIR "$qt_source_dir"
    require_dir PICO_QT_BUILD_DIR "$qt_build_dir"
    require_dir PICO_TBB_PACKAGE_DIR "$tbb_package_dir"

    patch_applied=0
    if git -C "$qt_source_dir" apply --reverse --check "$patch_file" >/dev/null 2>&1; then
        echo "Qt Pico patch already applied"
    else
        git -C "$qt_source_dir" apply --check "$patch_file"
        git -C "$qt_source_dir" apply "$patch_file"
        patch_applied=1
        echo "Applied Qt Pico runtime patch"
    fi

    if [[ "$patch_applied" == "1" || "${PICO_REBUILD_QT:-0}" == "1" ]]; then
        echo "Building patched Qt runtime"
        make -C "$qt_build_dir/qtbase" -j"${PICO_BUILD_JOBS:-$(nproc)}"
    fi

    qt_core="$qt_build_dir/qtbase/lib/libQt5Core_arm64-v8a.so"
    qt_platform="$qt_build_dir/qtbase/plugins/platforms/libplugins_platforms_qtforandroid_arm64-v8a.so"
    tbb_runtime="$tbb_package_dir/lib/libtbb.so"
    for file in "$qt_core" "$qt_platform" "$tbb_runtime"; do
        require_file "$file"
    done
fi

install -d "$runtime_dir" "$host_tools_dir" \
    "$precompiled_dir/breakpad/lib" "$precompiled_dir/draco/include" \
    "$precompiled_dir/draco/lib"
if [[ ! -f "$prebuilt_marker" ]]; then
    install -m 0755 "$qt_core" "$runtime_dir/libQt5Core_arm64-v8a.so"
    install -m 0755 "$qt_platform" \
        "$runtime_dir/libplugins_platforms_qtforandroid_arm64-v8a.so"
    install -m 0755 "$tbb_runtime" "$runtime_dir/libtbb.so"
fi

for tool in glslangValidator scribe spirv-cross spirv-opt; do
    case "$tool" in
        glslangValidator) tool_path="${PICO_GLSLANG_VALIDATOR:-}" ;;
        scribe) tool_path="${PICO_SCRIBE:-}" ;;
        spirv-cross) tool_path="${PICO_SPIRV_CROSS:-}" ;;
        spirv-opt) tool_path="${PICO_SPIRV_OPT:-}" ;;
    esac
    if [[ -z "$tool_path" ]]; then
        tool_path="$(command -v "$tool" || true)"
    fi
    if [[ -z "$tool_path" ]]; then
        echo "required host tool not found in PATH: ${tool}" >&2
        exit 2
    fi
    tool_path="$(readlink -f "$tool_path")"
    if [[ ! -x "$tool_path" ]]; then
        echo "host tool is not executable: ${tool_path}" >&2
        exit 2
    fi
    ln -sfn "$tool_path" "$host_tools_dir/$tool"
done

ln -sfn "$draco_include" "$precompiled_dir/draco/include/include"
ln -sfn "$draco_include/draco" "$precompiled_dir/draco/include/draco"
ln -sfn "$draco_library" "$precompiled_dir/draco/lib/libdraco.a"

for archive in \
    "$precompiled_dir/breakpad/lib/libbreakpad_client.a" \
    "$precompiled_dir/draco/lib/libdracodec.a" \
    "$precompiled_dir/draco/lib/libdracoenc.a"; do
    rm -f "$archive"
    ar rcs "$archive"
done

echo "Prepared Pico runtime and compatibility dependencies"
sha256sum "$runtime_dir"/*.so
