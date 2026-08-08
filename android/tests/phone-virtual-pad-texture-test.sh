#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly source_file="$script_dir/../../libraries/display-plugins/src/display-plugins/Basic2DWindowOpenGLDisplayPlugin.cpp"

grep -Eq 'ANDROID_APP_PHONE_INTERFACE' "$source_file"
grep -Eq 'VIRTUAL_PAD_MIP_COUNT[^;]*gpu::Texture::SINGLE_MIP' "$source_file"
grep -Eq 'VIRTUAL_PAD_FILTER[^;]*Sampler::FILTER_MIN_MAG_LINEAR' "$source_file"

count=$(grep -c 'Sampler(VIRTUAL_PAD_FILTER)' "$source_file")
[[ $count -eq 3 ]] || {
    echo "FAIL: expected all three virtual-pad texture creation paths, found $count" >&2
    exit 1
}

awk '
    /#if !defined\(ANDROID_APP_PHONE_INTERFACE\)/ { guarded = 1 }
    guarded && /setAutoGenerateMips\(true\)/ { found++ }
    /#endif/ { guarded = 0 }
    END { exit !(found == 3) }
' "$source_file" || {
    echo 'FAIL: phone virtual-pad textures still generate unused mip chains' >&2
    exit 1
}

echo 'Phone virtual-pad texture checks passed.'
