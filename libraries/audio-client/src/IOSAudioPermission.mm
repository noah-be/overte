// SPDX-License-Identifier: Apache-2.0
#include "IOSAudioPermission.h"
#include <atomic>
#include <mutex>

namespace {
std::shared_ptr<overte::audio::IOSAudioSessionAdapter> adapter;
std::mutex installationMutex;
std::mutex callbackMutex;
std::function<void()> stateCallback;
}

void overte::audio::setIOSAudioStateCallback(std::function<void()> callback) {
    std::lock_guard<std::mutex> lock(callbackMutex);
    stateCallback = std::move(callback);
}
void overte::audio::notifyIOSAudioStateChanged() {
    // Unregistration waits for in-flight enqueue to finish before AudioClient
    // teardown. The callback itself must not call back into this registry.
    std::lock_guard<std::mutex> lock(callbackMutex);
    if (stateCallback) { stateCallback(); }
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

void overteIOSSetAudioMuted(bool muted) {
    auto value = std::atomic_load(&adapter);
    if (value) { value->muted(muted); }
}
