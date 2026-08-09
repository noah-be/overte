<!--
Copyright 2026 Overte e.V.
SPDX-License-Identifier: Apache-2.0
-->

# Qt 6 migration boundary

The iOS target selects Qt 6 centrally through `cmake/QtCompat.cmake`. Existing
desktop and Android targets remain on Qt 5 while shared source is migrated.

## Transitional compatibility

Qt Core5Compat is linked to Qt 6 targets as a temporary bridge for QRegExp and
QTextCodec. New iOS code must use QRegularExpression and current text APIs.
Core5Compat is not a reason to add new Qt 5 API use.

The first source audit identified these compile boundaries:

- legacy QRegExp use spread across application and shared libraries;
- Qt 5 multimedia format and device APIs in `libraries/audio-client`;
- desktop WebEngine profiles, now excluded in favor of the iOS WebView adapter;
- desktop/HMD window and OpenGL paths that must not enter the iOS target; and
- remaining Qt-5-specific deployment helpers used only by desktop packaging.

## Audio migration rule

Qt 6 replaced the legacy QAudioDeviceInfo/QAudioInput/QAudioOutput and sample
format APIs. The migration must be implemented behind the audio-client device
boundary and verified against the existing 48 kHz signed-16-bit network format.
Platform-native AVAudioSession policy remains in the iOS shell and must not be
duplicated by desktop code.

The audio gate requires device enumeration, route change, microphone consent,
interruption recovery, Bluetooth behavior, mono input, stereo output, and
resampling tests on physical hardware.

## Enforcement

The iOS build is not allowed to restore Qt WebEngine, QDesktopWidget, QGLWidget,
or a desktop Qt installation to work around a migration error. A temporary
compatibility use must be centralized, documented here, and covered by a host
contract.

