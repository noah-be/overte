// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <openxr/openxr.h>

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace overte::e2e::openxr {

inline constexpr char BUILD_MARKER[] = "OVERTE_E2E_OPENXR_INPUT_V1";
inline constexpr char LAYER_NAME[] = "XR_APILAYER_OVERTE_e2e_input";
inline constexpr char PROFILE_ID[] = "overte-pico4-controller-v1";
inline constexpr char PROFILE_SHA256[] =
    "922e091c38f5cb1ec6c3e55c80b81de0a876524d951318c61e7feb4821eab481";
inline constexpr char INPUT_DIRECTORY[] =
    "/data/user/0/org.overte.pico/files/overte-e2e/openxr-input";

enum class BooleanChannel : std::size_t {
    LeftMenu,
    LeftPrimary,
    LeftSecondary,
    LeftThumbstick,
    LeftTrigger,
    RightPrimary,
    RightSecondary,
    RightThumbstick,
    RightTrigger,
    Count,
};

enum class FloatChannel : std::size_t {
    LeftGrip,
    LeftTrigger,
    RightGrip,
    RightTrigger,
    Count,
};

enum class VectorChannel : std::size_t {
    LeftThumbstick,
    RightThumbstick,
    Count,
};

enum class PoseChannel : std::size_t {
    LeftGrip,
    RightGrip,
    Count,
};

struct PoseOverride {
    bool active { false };
    XrPosef pose {
        { 0.0f, 0.0f, 0.0f, 1.0f },
        { 0.0f, 0.0f, 0.0f },
    };
};

struct Snapshot {
    bool overrideEnabled { false };
    std::array<bool, static_cast<std::size_t>(BooleanChannel::Count)> booleans {};
    std::array<float, static_cast<std::size_t>(FloatChannel::Count)> floats {};
    std::array<XrVector2f, static_cast<std::size_t>(VectorChannel::Count)> vectors {};
    std::array<PoseOverride, static_cast<std::size_t>(PoseChannel::Count)> poses {};
    bool viewActive { false };
    XrQuaternionf viewOrientation { 0.0f, 0.0f, 0.0f, 1.0f };
    float viewYawDegrees { 0.0f };
    float viewPitchDegrees { 0.0f };
};

struct TimedSnapshot {
    std::int64_t atMilliseconds { 0 };
    Snapshot state;
    std::string commandId;
};

bool booleanChannelForAction(const char* name, XrActionType type, BooleanChannel& channel);
bool floatChannelForAction(const char* name, XrActionType type, FloatChannel& channel);
bool vectorChannelForAction(const char* name, XrActionType type, VectorChannel& channel);
bool poseChannelForAction(const char* name, XrActionType type, PoseChannel& channel);

class Protocol {
public:
    Protocol();

    // Called exactly once after the downstream xrSyncActions succeeds. State
    // published here remains immutable until the next call.
    void sync(std::int64_t epochMilliseconds, std::int64_t monotonicMilliseconds);
    void failClosed(const char* reason, std::int64_t epochMilliseconds);
    void recordViewApplication(std::int64_t epochMilliseconds);
    void recordVectorApplication(VectorChannel channel, const XrVector2f& value,
                                 std::int64_t epochMilliseconds);
    void recordBooleanApplication(BooleanChannel channel, bool value,
                                  std::int64_t epochMilliseconds);

    const Snapshot& current() const { return _current; }
    const Snapshot& previous() const { return _previous; }
    std::uint64_t generation() const { return _generation; }
    std::uint64_t acceptedSequence() const { return _acceptedSequence; }
    const std::string& acceptedNonce() const { return _acceptedNonce; }
    const std::string& activeCommandId() const { return _activeCommandId; }

private:
    bool tryAccept(std::int64_t epochMilliseconds, std::int64_t monotonicMilliseconds,
                   std::uint64_t& grantDevice, std::uint64_t& grantInode,
                   std::int64_t& grantMtimeNanoseconds, std::int64_t& grantSize);
    void advance(std::int64_t epochMilliseconds, std::int64_t monotonicMilliseconds);
    void neutralize(const char* state, const char* detail, std::int64_t epochMilliseconds);
    void publishStatus(const char* state, const char* detail,
                       std::int64_t epochMilliseconds) const;

    Snapshot _current;
    Snapshot _previous;
    std::vector<TimedSnapshot> _events;
    std::size_t _eventIndex { 0 };
    std::int64_t _startedMonotonicMilliseconds { 0 };
    std::int64_t _expiresEpochMilliseconds { 0 };
    std::int64_t _watchdogMilliseconds { 0 };
    std::int64_t _createdEpochMilliseconds { 0 };
    std::uint64_t _generation { 0 };
    std::uint64_t _acceptedSequence { 0 };
    std::uint64_t _viewAppliedSequence { 0 };
    double _viewAppliedYawDegrees { 0.0 };
    double _viewAppliedPitchDegrees { 0.0 };
    std::uint64_t _vectorAppliedSequence { 0 };
    double _leftThumbstickAppliedX { 0.0 };
    double _leftThumbstickAppliedY { 0.0 };
    std::uint64_t _booleanAppliedSequence { 0 };
    bool _leftSecondaryApplied { false };
    bool _rightSecondaryApplied { false };
    std::string _acceptedNonce;
    std::string _activeCommandId;
    std::uint64_t _seenGrantDevice { 0 };
    std::uint64_t _seenGrantInode { 0 };
    std::int64_t _seenGrantMtimeNanoseconds { -1 };
    std::int64_t _seenGrantSize { -1 };
    bool _grantWasPresent { false };
};

}  // namespace overte::e2e::openxr
