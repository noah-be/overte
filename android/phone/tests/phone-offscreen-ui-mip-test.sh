#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly repo_root="$(cd -- "$script_dir/../../.." && pwd)"

grep -q 'offscreenUi->setGenerateMips(false)' "$repo_root/interface/src/Application_Graphics.cpp"
grep -q 'FILTER_MIN_MAG_LINEAR' "$repo_root/interface/src/ui/ApplicationOverlay.cpp"
grep -q 'if (generateMips)' "$repo_root/libraries/qml/src/qml/impl/RenderEventHandler.cpp"
grep -q 'glGenerateMipmap' "$repo_root/libraries/qml/src/qml/impl/RenderEventHandler.cpp"
grep -q 'bool generateMips = true' "$repo_root/libraries/qml/src/qml/impl/TextureCache.h"
grep -q 'uvec2ToUint64(info.size, info.generateMips)' "$repo_root/libraries/qml/src/qml/impl/TextureCache.cpp"
grep -q 'generateMips ? GL_LINEAR_MIPMAP_LINEAR : GL_LINEAR' "$repo_root/libraries/qml/src/qml/impl/TextureCache.cpp"

echo 'Phone Offscreen UI mip checks passed.'
