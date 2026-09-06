#!/bin/sh
set -eu
: "${OVERTE_ATTEMPT_ROOT:?OVERTE_ATTEMPT_ROOT must be an explicit absolute path}"
: "${OVERTE_SOURCE_CLOSURE_STORE:?OVERTE_SOURCE_CLOSURE_STORE must be an explicit absolute path}"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$script_dir/build-dependencies.sh" --prepare
