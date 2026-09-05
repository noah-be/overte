#!/bin/sh
set -eu

: "${OVERTE_SOURCE_STORE:?OVERTE_SOURCE_STORE must be an explicit absolute path}"
: "${OVERTE_QT_SOURCE_ROOT:?OVERTE_QT_SOURCE_ROOT must be an explicit absolute path}"

case "$OVERTE_SOURCE_STORE:$OVERTE_QT_SOURCE_ROOT" in
  /*:/*) ;;
  *) echo "source store and output must be absolute paths" >&2; exit 2 ;;
esac

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$script_dir/../conan/qt_source_store.py" \
  --manifest "$script_dir/../manifests/qt-source.lock.json" \
  --source-store "$OVERTE_SOURCE_STORE" \
  --output "$OVERTE_QT_SOURCE_ROOT"
