// SPDX-License-Identifier: Apache-2.0
#include "IOSAudioPermission.h"
#include <atomic>
#include <mutex>

namespace {
std::shared_ptr<overte::audio::IOSAudioSessionAdapter> adapter;
std::mutex installationMutex;
}

bool overte::audio::installIOSAudioSessionAdapter(std::shared_ptr<IOSAudioSessionAdapter> value) {
    std::lock_guard<std::mutex> lock(installationMutex);
    if (!value || std::atomic_load(&adapter)) { return false; }
    std::atomic_store(&adapter, std::move(value));
    return true;
}

bool overteIOSMicrophonePermissionGranted() {
    auto value = std::atomic_load(&adapter);
    return value && value->microphonePermissionGranted();
}
void overteIOSRequestMicrophonePermission() {
    auto value = std::atomic_load(&adapter);
    if (value) { value->requestMicrophonePermission(); }
}
bool overteIOSActivateAudioSession() {
    auto value = std::atomic_load(&adapter);
    return value && value->activate();
}
bool overteIOSDeactivateAudioSession() {
    auto value = std::atomic_load(&adapter);
    return value && value->deactivate();
}
