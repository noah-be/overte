#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Adapter for a prepared AppImage or Fedora development Interface tree, with isolated
# profile/audio environment supplied by the gateway. No credentials are loaded.
set -euo pipefail
native_root="${OVERTE_PUBLIC_NATIVE_ROOT:?Set OVERTE_PUBLIC_NATIVE_ROOT to the prepared compatible Interface tree}"
if [[ -x "$native_root/AppRun" ]]; then
    exec "$native_root/AppRun" --disableDisplayPlugins OpenXR,OpenVR --suppress-settings-reset --no-login-suggestion "$@"
fi
export LD_LIBRARY_PATH="$native_root/systemlibs:$native_root/conanlibs/RelWithDebInfo${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$native_root/systemqt/plugins"
export QML2_IMPORT_PATH="$native_root/systemqt/qml"
export QTWEBENGINEPROCESS_PATH="$native_root/systemqt/libexec/QtWebEngineProcess"
# The development build uses a different QSettings organization name.
# Keep the gateway-provisioned private muted audio preferences effective.
if [[ -n "${XDG_CONFIG_HOME:-}" && -f "$XDG_CONFIG_HOME/Overte/Interface.json" ]]; then
    mkdir -p -- "$XDG_CONFIG_HOME/Overte - Dev"
    cp -- "$XDG_CONFIG_HOME/Overte/Interface.json" "$XDG_CONFIG_HOME/Overte - Dev/Interface.json"
fi
exec "$native_root/interface/RelWithDebInfo/interface" --display=Desktop --suppress-settings-reset --no-login-suggestion "$@"
