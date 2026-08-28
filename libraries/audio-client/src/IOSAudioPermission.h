// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <functional>

enum class OverteIOSMicrophonePermissionState {
    Undetermined,
    Denied,
    Granted,
};

enum class OverteIOSAudioSessionEvent {
    InterruptionBegan,
    InterruptionEnded,
    RouteChanged,
    MediaServicesReset,
};

using OverteIOSMicrophonePermissionHandler =
    std::function<void(OverteIOSMicrophonePermissionState)>;
using OverteIOSAudioSessionEventHandler =
    std::function<void(OverteIOSAudioSessionEvent, bool, unsigned long)>;

OverteIOSMicrophonePermissionState overteIOSMicrophonePermissionState();
bool overteIOSMicrophonePermissionGranted();
void overteIOSRequestMicrophonePermission(OverteIOSMicrophonePermissionHandler handler = {});
void overteIOSSetAudioSessionEventHandler(OverteIOSAudioSessionEventHandler handler);
bool overteIOSActivateAudioSession();
bool overteIOSDeactivateAudioSession();
