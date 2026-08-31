// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

// Undetermined and denied record-permission states both fail closed.
bool overteIOSMicrophonePermissionGranted();
void overteIOSRequestMicrophonePermission();
bool overteIOSActivateAudioSession();
bool overteIOSDeactivateAudioSession();
