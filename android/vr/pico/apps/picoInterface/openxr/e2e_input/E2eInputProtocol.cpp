// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "E2eInputProtocol.h"

#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonParseError>
#include <QString>
#include <QStringList>

#include <android/log.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <set>
#include <utility>

namespace overte::e2e::openxr {
namespace {

constexpr std::size_t MAX_FILE_BYTES = 64 * 1024;
constexpr int MAX_COMMANDS = 32;
constexpr std::int64_t MAX_GRANT_LIFETIME_MS = 5 * 60 * 1000;
constexpr std::int64_t INTER_COMMAND_GAP_MS = 100;
constexpr std::int64_t INITIAL_NEUTRAL_MS = 100;
constexpr double PI = 3.14159265358979323846;

struct FileIdentity {
    std::uint64_t device { 0 };
    std::uint64_t inode { 0 };
    std::int64_t mtimeNanoseconds { 0 };
    std::int64_t size { 0 };
};

void logWarning(const char* message) {
    __android_log_print(ANDROID_LOG_WARN, "OverteE2eOpenXR", "%s", message);
}

bool validIdentifier(const QString& value) {
    if (value.isEmpty() || value.size() > 64 || !value.front().isLower()) {
        return false;
    }
    for (const QChar character : value) {
        if (!(character.isLower() || character.isDigit() || character == QLatin1Char('-'))) {
            return false;
        }
    }
    return true;
}

bool validNonce(const QString& value) {
    if (value.size() < 32 || value.size() > 128) {
        return false;
    }
    for (const QChar character : value) {
        if (!(character.isDigit() ||
              (character >= QLatin1Char('a') && character <= QLatin1Char('f')))) {
            return false;
        }
    }
    return true;
}

bool exactKeys(const QJsonObject& object, const QStringList& required,
               const QStringList& optional = {}) {
    std::set<QString> expected;
    for (const QString& key : required) {
        expected.insert(key);
        if (!object.contains(key)) {
            return false;
        }
    }
    expected.insert(optional.begin(), optional.end());
    for (auto iterator = object.begin(); iterator != object.end(); ++iterator) {
        if (expected.find(iterator.key()) == expected.end()) {
            return false;
        }
    }
    return true;
}

bool finiteNumber(const QJsonValue& value, double minimum, double maximum, double& result) {
    if (!value.isDouble()) {
        return false;
    }
    result = value.toDouble();
    return std::isfinite(result) && result >= minimum && result <= maximum;
}

bool integerValue(const QJsonValue& value, std::uint64_t minimum,
                  std::uint64_t maximum, std::uint64_t& result) {
    double number { 0.0 };
    if (!finiteNumber(value, static_cast<double>(minimum),
                      static_cast<double>(maximum), number) || std::floor(number) != number) {
        return false;
    }
    result = static_cast<std::uint64_t>(number);
    return true;
}

bool statRegularPrivateFile(const char* path, FileIdentity& identity) {
    struct stat info {};
    if (lstat(path, &info) != 0 || !S_ISREG(info.st_mode) || info.st_uid != getuid() ||
            (info.st_mode & 0077) != 0 || info.st_size <= 0 ||
            static_cast<std::size_t>(info.st_size) > MAX_FILE_BYTES) {
        return false;
    }
    identity.device = static_cast<std::uint64_t>(info.st_dev);
    identity.inode = static_cast<std::uint64_t>(info.st_ino);
#if defined(__ANDROID__)
    identity.mtimeNanoseconds =
        static_cast<std::int64_t>(info.st_mtim.tv_sec) * 1000000000LL + info.st_mtim.tv_nsec;
#else
    identity.mtimeNanoseconds = static_cast<std::int64_t>(info.st_mtime) * 1000000000LL;
#endif
    identity.size = static_cast<std::int64_t>(info.st_size);
    return true;
}

bool secureRead(const char* path, QByteArray& contents, FileIdentity* identity = nullptr) {
    const int descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (descriptor < 0) {
        return false;
    }
    struct stat info {};
    bool valid = fstat(descriptor, &info) == 0 && S_ISREG(info.st_mode) &&
        info.st_uid == getuid() && (info.st_mode & 0077) == 0 && info.st_size > 0 &&
        static_cast<std::size_t>(info.st_size) <= MAX_FILE_BYTES;
    if (valid) {
        contents.resize(static_cast<int>(info.st_size));
        std::size_t offset = 0;
        while (offset < static_cast<std::size_t>(info.st_size)) {
            const ssize_t count = read(descriptor, contents.data() + offset,
                                       static_cast<std::size_t>(info.st_size) - offset);
            if (count <= 0) {
                valid = false;
                break;
            }
            offset += static_cast<std::size_t>(count);
        }
        if (valid && identity) {
            identity->device = static_cast<std::uint64_t>(info.st_dev);
            identity->inode = static_cast<std::uint64_t>(info.st_ino);
#if defined(__ANDROID__)
            identity->mtimeNanoseconds =
                static_cast<std::int64_t>(info.st_mtim.tv_sec) * 1000000000LL + info.st_mtim.tv_nsec;
#else
            identity->mtimeNanoseconds = static_cast<std::int64_t>(info.st_mtime) * 1000000000LL;
#endif
            identity->size = static_cast<std::int64_t>(info.st_size);
        }
    }
    close(descriptor);
    return valid;
}

bool parseObject(const QByteArray& contents, QJsonObject& object) {
    QJsonParseError error {};
    const QJsonDocument document = QJsonDocument::fromJson(contents, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject()) {
        return false;
    }
    object = document.object();
    return true;
}

Snapshot neutralOverride() {
    Snapshot snapshot;
    snapshot.overrideEnabled = true;
    return snapshot;
}

XrQuaternionf lookQuaternion(double yawDegrees, double pitchDegrees) {
    const double yaw = yawDegrees * PI / 180.0 / 2.0;
    const double pitch = pitchDegrees * PI / 180.0 / 2.0;
    const double sy = std::sin(yaw);
    const double cy = std::cos(yaw);
    const double sp = std::sin(pitch);
    const double cp = std::cos(pitch);
    return {
        static_cast<float>(cy * sp),
        static_cast<float>(sy * cp),
        static_cast<float>(-sy * sp),
        static_cast<float>(cy * cp),
    };
}

bool readVector(const QJsonValue& value, int count, double minimum, double maximum,
                std::vector<double>& result) {
    if (!value.isArray()) {
        return false;
    }
    const QJsonArray array = value.toArray();
    if (array.size() != count) {
        return false;
    }
    result.clear();
    for (const QJsonValue& item : array) {
        double number { 0.0 };
        if (!finiteNumber(item, minimum, maximum, number)) {
            return false;
        }
        result.push_back(number);
    }
    return true;
}

bool sameIdentity(const FileIdentity& identity, std::uint64_t device,
                  std::uint64_t inode, std::int64_t mtimeNanoseconds,
                  std::int64_t size) {
    return identity.device == device && identity.inode == inode &&
        identity.mtimeNanoseconds == mtimeNanoseconds && identity.size == size;
}

bool writeAll(int descriptor, const QByteArray& contents) {
    std::size_t offset = 0;
    while (offset < static_cast<std::size_t>(contents.size())) {
        const ssize_t count = write(descriptor, contents.constData() + offset,
                                    static_cast<std::size_t>(contents.size()) - offset);
        if (count <= 0) {
            return false;
        }
        offset += static_cast<std::size_t>(count);
    }
    return fsync(descriptor) == 0;
}

}  // namespace

bool booleanChannelForAction(const char* name, XrActionType type, BooleanChannel& channel) {
    if (!name || type != XR_ACTION_TYPE_BOOLEAN_INPUT) {
        return false;
    }
    static constexpr std::pair<const char*, BooleanChannel> bindings[] = {
        { "menu_click", BooleanChannel::LeftMenu },
        { "left_primary_click", BooleanChannel::LeftPrimary },
        { "left_secondary_click", BooleanChannel::LeftSecondary },
        { "left_thumbstick_click", BooleanChannel::LeftThumbstick },
        { "left_trigger_click", BooleanChannel::LeftTrigger },
        { "right_primary_click", BooleanChannel::RightPrimary },
        { "right_secondary_click", BooleanChannel::RightSecondary },
        { "right_thumbstick_click", BooleanChannel::RightThumbstick },
        { "right_trigger_click", BooleanChannel::RightTrigger },
    };
    for (const auto& [candidate, value] : bindings) {
        if (std::strcmp(candidate, name) == 0) {
            channel = value;
            return true;
        }
    }
    return false;
}

bool floatChannelForAction(const char* name, XrActionType type, FloatChannel& channel) {
    if (!name || type != XR_ACTION_TYPE_FLOAT_INPUT) {
        return false;
    }
    static constexpr std::pair<const char*, FloatChannel> bindings[] = {
        { "left_squeeze_value", FloatChannel::LeftGrip },
        { "left_trigger_value", FloatChannel::LeftTrigger },
        { "right_squeeze_value", FloatChannel::RightGrip },
        { "right_trigger_value", FloatChannel::RightTrigger },
    };
    for (const auto& [candidate, value] : bindings) {
        if (std::strcmp(candidate, name) == 0) {
            channel = value;
            return true;
        }
    }
    return false;
}

bool vectorChannelForAction(const char* name, XrActionType type, VectorChannel& channel) {
    if (!name || type != XR_ACTION_TYPE_VECTOR2F_INPUT) {
        return false;
    }
    if (std::strcmp(name, "left_thumbstick") == 0) {
        channel = VectorChannel::LeftThumbstick;
        return true;
    }
    if (std::strcmp(name, "right_thumbstick") == 0) {
        channel = VectorChannel::RightThumbstick;
        return true;
    }
    return false;
}

bool poseChannelForAction(const char* name, XrActionType type, PoseChannel& channel) {
    if (!name || type != XR_ACTION_TYPE_POSE_INPUT) {
        return false;
    }
    if (std::strcmp(name, "left_grip_pose") == 0) {
        channel = PoseChannel::LeftGrip;
        return true;
    }
    if (std::strcmp(name, "right_grip_pose") == 0) {
        channel = PoseChannel::RightGrip;
        return true;
    }
    return false;
}

Protocol::Protocol() :
    _createdEpochMilliseconds(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::system_clock::now().time_since_epoch()).count()) {
}

void Protocol::sync(std::int64_t epochMilliseconds, std::int64_t monotonicMilliseconds) {
    _previous = _current;
    FileIdentity grantIdentity;
    const std::string grantPath = std::string(INPUT_DIRECTORY) + "/grant.json";
    const bool grantPresent = statRegularPrivateFile(grantPath.c_str(), grantIdentity);
    if (!grantPresent) {
        if (_grantWasPresent || _current.overrideEnabled) {
            _grantWasPresent = false;
            neutralize("neutral", "grant-removed", epochMilliseconds);
        }
        return;
    }
    _grantWasPresent = true;
    if (!sameIdentity(grantIdentity, _seenGrantDevice, _seenGrantInode,
                      _seenGrantMtimeNanoseconds, _seenGrantSize)) {
        FileIdentity consumedIdentity = grantIdentity;
        const bool accepted = tryAccept(
            epochMilliseconds, monotonicMilliseconds,
            consumedIdentity.device, consumedIdentity.inode,
            consumedIdentity.mtimeNanoseconds, consumedIdentity.size);
        // Record the file descriptor identity actually read, not the earlier
        // lstat result. If the host atomically replaces the grant between the
        // two calls, the replacement remains a new commit on the next sync.
        _seenGrantDevice = consumedIdentity.device;
        _seenGrantInode = consumedIdentity.inode;
        _seenGrantMtimeNanoseconds = consumedIdentity.mtimeNanoseconds;
        _seenGrantSize = consumedIdentity.size;
        if (!accepted) {
            neutralize("error", "rejected-command", epochMilliseconds);
            return;
        }
    }
    advance(epochMilliseconds, monotonicMilliseconds);
}

bool Protocol::tryAccept(std::int64_t epochMilliseconds,
                         std::int64_t monotonicMilliseconds,
                         std::uint64_t& grantDevice, std::uint64_t& grantInode,
                         std::int64_t& grantMtimeNanoseconds,
                         std::int64_t& grantSize) {
    const std::string grantPath = std::string(INPUT_DIRECTORY) + "/grant.json";
    const std::string commandPath = std::string(INPUT_DIRECTORY) + "/commands.json";
    QByteArray grantBytes;
    QByteArray commandBytes;
    FileIdentity grantIdentity;
    if (!secureRead(grantPath.c_str(), grantBytes, &grantIdentity) ||
            !secureRead(commandPath.c_str(), commandBytes)) {
        return false;
    }
    grantDevice = grantIdentity.device;
    grantInode = grantIdentity.inode;
    grantMtimeNanoseconds = grantIdentity.mtimeNanoseconds;
    grantSize = grantIdentity.size;
    // A grant that survived an app/OpenXR-instance restart must never resume
    // an old input stream. The host must atomically commit a fresh sequence.
    if (grantIdentity.mtimeNanoseconds / 1000000LL < _createdEpochMilliseconds) {
        return false;
    }
    QJsonObject grant;
    QJsonObject envelope;
    if (!parseObject(grantBytes, grant) || !parseObject(commandBytes, envelope)) {
        return false;
    }
    if (!exactKeys(grant, {
            "schemaVersion", "buildMarker", "testBuild", "runtimeOptIn", "channel",
            "consumer", "bindingProfileSha256", "sessionNonce", "sequence",
            "expiresEpochMs",
        }) || !exactKeys(envelope, {
            "schemaVersion", "sessionNonce", "sequence", "commands",
        })) {
        return false;
    }
    if (grant.value("schemaVersion").toInt(-1) != 1 ||
            grant.value("buildMarker").toString() != QLatin1String(BUILD_MARKER) ||
            grant.value("testBuild") != QJsonValue(true) ||
            grant.value("runtimeOptIn") != QJsonValue(true) ||
            grant.value("channel").toString() != QLatin1String("app-private-file") ||
            grant.value("consumer").toString() != QLatin1String(LAYER_NAME) ||
            grant.value("bindingProfileSha256").toString() != QLatin1String(PROFILE_SHA256) ||
            envelope.value("schemaVersion").toInt(-1) != 1) {
        return false;
    }
    const QString nonce = grant.value("sessionNonce").toString();
    if (!validNonce(nonce) || envelope.value("sessionNonce").toString() != nonce) {
        return false;
    }
    std::uint64_t sequence { 0 };
    std::uint64_t envelopeSequence { 0 };
    std::uint64_t expires { 0 };
    if (!integerValue(grant.value("sequence"), 1,
                      std::numeric_limits<std::uint32_t>::max(), sequence) ||
            !integerValue(envelope.value("sequence"), 1,
                          std::numeric_limits<std::uint32_t>::max(), envelopeSequence) ||
            !integerValue(grant.value("expiresEpochMs"), 1,
                          9007199254740991ULL, expires) || sequence != envelopeSequence ||
            sequence <= _acceptedSequence ||
            (!_acceptedNonce.empty() && nonce.toStdString() != _acceptedNonce) ||
            expires <= static_cast<std::uint64_t>(epochMilliseconds) ||
            expires - static_cast<std::uint64_t>(epochMilliseconds) > MAX_GRANT_LIFETIME_MS) {
        return false;
    }
    const QJsonValue commandsValue = envelope.value("commands");
    if (!commandsValue.isArray()) {
        return false;
    }
    const QJsonArray commands = commandsValue.toArray();
    if (commands.isEmpty() || commands.size() > MAX_COMMANDS) {
        return false;
    }

    std::vector<TimedSnapshot> compiled;
    compiled.push_back({ 0, neutralOverride(), {} });
    std::set<QString> identifiers;
    std::int64_t cursor = INITIAL_NEUTRAL_MS;
    for (const QJsonValue& commandValue : commands) {
        if (!commandValue.isObject()) {
            return false;
        }
        const QJsonObject command = commandValue.toObject();
        if (!exactKeys(command, { "id", "operation", "arguments" }) ||
                !command.value("arguments").isObject()) {
            return false;
        }
        const QString identifier = command.value("id").toString();
        if (!validIdentifier(identifier) ||
                identifiers.find(identifier) != identifiers.end()) {
            return false;
        }
        identifiers.insert(identifier);
        const QString operation = command.value("operation").toString();
        const QJsonObject arguments = command.value("arguments").toObject();
        Snapshot active = neutralOverride();
        std::int64_t duration = 0;

        if (operation == QLatin1String("controller.button")) {
            if (!exactKeys(arguments, { "hand", "control" }, { "holdMilliseconds" })) {
                return false;
            }
            const QString hand = arguments.value("hand").toString();
            const QString control = arguments.value("control").toString();
            std::uint64_t hold { 120 };
            if (arguments.contains("holdMilliseconds") &&
                    !integerValue(arguments.value("holdMilliseconds"), 40, 500, hold)) {
                return false;
            }
            BooleanChannel channel;
            bool found = false;
            if (hand == QLatin1String("left") && control == QLatin1String("menu")) {
                channel = BooleanChannel::LeftMenu; found = true;
            } else if (hand == QLatin1String("left") && control == QLatin1String("primary")) {
                channel = BooleanChannel::LeftPrimary; found = true;
            } else if (hand == QLatin1String("left") && control == QLatin1String("secondary")) {
                channel = BooleanChannel::LeftSecondary; found = true;
            } else if (hand == QLatin1String("left") && control == QLatin1String("thumbstick")) {
                channel = BooleanChannel::LeftThumbstick; found = true;
            } else if (hand == QLatin1String("left") && control == QLatin1String("trigger")) {
                channel = BooleanChannel::LeftTrigger; found = true;
            } else if (hand == QLatin1String("right") && control == QLatin1String("primary")) {
                channel = BooleanChannel::RightPrimary; found = true;
            } else if (hand == QLatin1String("right") && control == QLatin1String("secondary")) {
                channel = BooleanChannel::RightSecondary; found = true;
            } else if (hand == QLatin1String("right") && control == QLatin1String("thumbstick")) {
                channel = BooleanChannel::RightThumbstick; found = true;
            } else if (hand == QLatin1String("right") && control == QLatin1String("trigger")) {
                channel = BooleanChannel::RightTrigger; found = true;
            }
            if (!found) {
                return false;
            }
            active.booleans[static_cast<std::size_t>(channel)] = true;
            duration = static_cast<std::int64_t>(hold);
        } else if (operation == QLatin1String("controller.trigger") ||
                   operation == QLatin1String("controller.grip")) {
            if (!exactKeys(arguments, { "hand", "value" }, { "holdMilliseconds" })) {
                return false;
            }
            const QString hand = arguments.value("hand").toString();
            double value { 0.0 };
            std::uint64_t hold { 250 };
            if (!finiteNumber(arguments.value("value"), 0.05, 1.0, value) ||
                    (arguments.contains("holdMilliseconds") &&
                     !integerValue(arguments.value("holdMilliseconds"), 100, 3000, hold))) {
                return false;
            }
            FloatChannel channel;
            if (hand == QLatin1String("left")) {
                channel = operation == QLatin1String("controller.trigger")
                    ? FloatChannel::LeftTrigger : FloatChannel::LeftGrip;
            } else if (hand == QLatin1String("right")) {
                channel = operation == QLatin1String("controller.trigger")
                    ? FloatChannel::RightTrigger : FloatChannel::RightGrip;
            } else {
                return false;
            }
            active.floats[static_cast<std::size_t>(channel)] = static_cast<float>(value);
            duration = static_cast<std::int64_t>(hold);
        } else if (operation == QLatin1String("controller.thumbstick")) {
            if (!exactKeys(arguments, { "hand", "x", "y" }, { "holdMilliseconds" })) {
                return false;
            }
            double x { 0.0 };
            double y { 0.0 };
            std::uint64_t hold { 250 };
            if (!finiteNumber(arguments.value("x"), -1.0, 1.0, x) ||
                    !finiteNumber(arguments.value("y"), -1.0, 1.0, y) ||
                    (std::abs(x) < 0.01 && std::abs(y) < 0.01) ||
                    (arguments.contains("holdMilliseconds") &&
                     !integerValue(arguments.value("holdMilliseconds"), 100, 3000, hold))) {
                return false;
            }
            VectorChannel channel;
            if (arguments.value("hand").toString() == QLatin1String("left")) {
                channel = VectorChannel::LeftThumbstick;
            } else if (arguments.value("hand").toString() == QLatin1String("right")) {
                channel = VectorChannel::RightThumbstick;
            } else {
                return false;
            }
            active.vectors[static_cast<std::size_t>(channel)] = {
                static_cast<float>(x), static_cast<float>(y),
            };
            duration = static_cast<std::int64_t>(hold);
        } else if (operation == QLatin1String("controller.pose")) {
            if (!exactKeys(arguments, { "hand", "positionMeters", "orientation" },
                           { "holdMilliseconds" })) {
                return false;
            }
            std::vector<double> position;
            std::vector<double> orientation;
            std::uint64_t hold { 500 };
            if (!readVector(arguments.value("positionMeters"), 3, -3.0, 3.0, position) ||
                    !readVector(arguments.value("orientation"), 4, -1.0, 1.0, orientation) ||
                    (arguments.contains("holdMilliseconds") &&
                     !integerValue(arguments.value("holdMilliseconds"), 100, 3000, hold))) {
                return false;
            }
            const double norm = std::sqrt(
                orientation[0] * orientation[0] + orientation[1] * orientation[1] +
                orientation[2] * orientation[2] + orientation[3] * orientation[3]);
            if (std::abs(norm - 1.0) > 1e-4) {
                return false;
            }
            PoseChannel channel;
            if (arguments.value("hand").toString() == QLatin1String("left")) {
                channel = PoseChannel::LeftGrip;
            } else if (arguments.value("hand").toString() == QLatin1String("right")) {
                channel = PoseChannel::RightGrip;
            } else {
                return false;
            }
            PoseOverride& pose = active.poses[static_cast<std::size_t>(channel)];
            pose.active = true;
            pose.pose.orientation = {
                static_cast<float>(orientation[0]), static_cast<float>(orientation[1]),
                static_cast<float>(orientation[2]), static_cast<float>(orientation[3]),
            };
            pose.pose.position = {
                static_cast<float>(position[0]), static_cast<float>(position[1]),
                static_cast<float>(position[2]),
            };
            duration = static_cast<std::int64_t>(hold);
        } else if (operation == QLatin1String("input.look")) {
            if (!exactKeys(arguments, { "horizontal" }, { "vertical", "durationSeconds" })) {
                return false;
            }
            double horizontal { 0.0 };
            double vertical { 0.0 };
            double seconds { 0.35 };
            if (!finiteNumber(arguments.value("horizontal"), -0.45, 0.45, horizontal) ||
                    (arguments.contains("vertical") &&
                     !finiteNumber(arguments.value("vertical"), -0.45, 0.45, vertical)) ||
                    (arguments.contains("durationSeconds") &&
                     !finiteNumber(arguments.value("durationSeconds"), 0.1, 8.0, seconds)) ||
                    (std::abs(horizontal) < 0.01 && std::abs(vertical) < 0.01)) {
                return false;
            }
            active.viewActive = true;
            active.viewYawDegrees = static_cast<float>(horizontal / 0.45 * 45.0);
            active.viewPitchDegrees = static_cast<float>(vertical / 0.45 * 30.0);
            active.viewOrientation = lookQuaternion(active.viewYawDegrees,
                                                     active.viewPitchDegrees);
            duration = static_cast<std::int64_t>(std::llround(seconds * 1000.0));
        } else if (operation == QLatin1String("input.move")) {
            if (!exactKeys(arguments, { "direction", "durationSeconds" }, { "strength" })) {
                return false;
            }
            const QString direction = arguments.value("direction").toString();
            double seconds { 0.0 };
            double strength { 0.8 };
            if ((direction != QLatin1String("forward") &&
                 direction != QLatin1String("backward")) ||
                    !finiteNumber(arguments.value("durationSeconds"), 0.1, 8.0, seconds) ||
                    (arguments.contains("strength") &&
                     !finiteNumber(arguments.value("strength"), 0.2, 1.0, strength))) {
                return false;
            }
            active.vectors[static_cast<std::size_t>(VectorChannel::LeftThumbstick)] = {
                0.0f,
                static_cast<float>(direction == QLatin1String("forward") ? strength : -strength),
            };
            duration = static_cast<std::int64_t>(std::llround(seconds * 1000.0));
        } else if (operation == QLatin1String("input.jump")) {
            if (!exactKeys(arguments, {})) {
                return false;
            }
            active.booleans[static_cast<std::size_t>(BooleanChannel::RightSecondary)] = true;
            duration = 120;
        } else if (operation == QLatin1String("input.fly")) {
            if (!exactKeys(arguments, { "durationSeconds" })) {
                return false;
            }
            double seconds { 0.0 };
            if (!finiteNumber(arguments.value("durationSeconds"), 0.5, 8.0, seconds)) {
                return false;
            }
            active.booleans[static_cast<std::size_t>(BooleanChannel::RightSecondary)] = true;
            duration = static_cast<std::int64_t>(std::llround(seconds * 1000.0));
        } else if (operation == QLatin1String("tablet.open") ||
                   operation == QLatin1String("tablet.close")) {
            if (!exactKeys(arguments, {}, { "holdMilliseconds" })) {
                return false;
            }
            std::uint64_t hold { 120 };
            if (arguments.contains("holdMilliseconds") &&
                    !integerValue(arguments.value("holdMilliseconds"), 100, 8000, hold)) {
                return false;
            }
            // PICO OS commonly reserves the physical Menu button. Overte maps
            // left Y as its user-realistic tablet fallback.
            active.booleans[static_cast<std::size_t>(BooleanChannel::LeftSecondary)] = true;
            duration = static_cast<std::int64_t>(hold);
        } else {
            return false;
        }

        compiled.push_back({ cursor, active, identifier.toStdString() });
        cursor += duration;
        compiled.push_back({ cursor, neutralOverride(), {} });
        cursor += INTER_COMMAND_GAP_MS;
        if (cursor > 30000) {
            return false;
        }
    }
    cursor += INITIAL_NEUTRAL_MS;
    Snapshot disabled;
    compiled.push_back({ cursor, disabled, {} });

    _events = std::move(compiled);
    _eventIndex = 0;
    _startedMonotonicMilliseconds = monotonicMilliseconds;
    _expiresEpochMilliseconds = static_cast<std::int64_t>(expires);
    _watchdogMilliseconds = cursor;
    _acceptedSequence = sequence;
    _viewAppliedSequence = 0;
    _viewAppliedYawDegrees = 0.0;
    _viewAppliedPitchDegrees = 0.0;
    _vectorAppliedSequence = 0;
    _leftThumbstickAppliedY = 0.0;
    _booleanAppliedSequence = 0;
    _leftSecondaryApplied = false;
    _rightSecondaryApplied = false;
    _acceptedNonce = nonce.toStdString();
    _current = _events.front().state;
    _activeCommandId.clear();
    ++_generation;
    publishStatus("accepted", "command-stream", epochMilliseconds);
    return true;
}

void Protocol::advance(std::int64_t epochMilliseconds,
                       std::int64_t monotonicMilliseconds) {
    if (_events.empty() || !_current.overrideEnabled) {
        return;
    }
    if (epochMilliseconds >= _expiresEpochMilliseconds ||
            monotonicMilliseconds < _startedMonotonicMilliseconds) {
        neutralize("neutral", "expired-or-clock", epochMilliseconds);
        return;
    }
    const std::int64_t offset = monotonicMilliseconds - _startedMonotonicMilliseconds;
    if (offset >= _watchdogMilliseconds) {
        neutralize("neutral", "watchdog", epochMilliseconds);
        return;
    }
    while (_eventIndex + 1 < _events.size() &&
           _events[_eventIndex + 1].atMilliseconds <= offset) {
        ++_eventIndex;
        _current = _events[_eventIndex].state;
        _activeCommandId = _events[_eventIndex].commandId;
        ++_generation;
        publishStatus(_current.overrideEnabled ? "active" : "neutral",
                      _activeCommandId.empty() ? "neutral-window" : "command-window",
                      epochMilliseconds);
    }
}

void Protocol::failClosed(const char* reason, std::int64_t epochMilliseconds) {
    neutralize("error", reason ? reason : "runtime-error", epochMilliseconds);
}

void Protocol::recordViewApplication(std::int64_t epochMilliseconds) {
    if (!_current.overrideEnabled || !_current.viewActive ||
            _activeCommandId.empty() || _viewAppliedSequence == _acceptedSequence) {
        return;
    }
    _viewAppliedSequence = _acceptedSequence;
    _viewAppliedYawDegrees = _current.viewYawDegrees;
    _viewAppliedPitchDegrees = _current.viewPitchDegrees;
    // Publish once per accepted sequence. This proves that an application
    // OpenXR view query consumed the bounded override without writing a status
    // file on every rendered frame.
    publishStatus("active", "view-consumed", epochMilliseconds);
}

void Protocol::recordVectorApplication(VectorChannel channel, const XrVector2f& value,
                                       std::int64_t epochMilliseconds) {
    if (!_current.overrideEnabled || _activeCommandId.empty() ||
            channel != VectorChannel::LeftThumbstick || std::abs(value.y) < 0.01f ||
            _vectorAppliedSequence == _acceptedSequence) {
        return;
    }
    _vectorAppliedSequence = _acceptedSequence;
    _leftThumbstickAppliedY = value.y;
    publishStatus("active", "vector-consumed", epochMilliseconds);
}

void Protocol::recordBooleanApplication(BooleanChannel channel, bool value,
                                        std::int64_t epochMilliseconds) {
    if (!_current.overrideEnabled || _activeCommandId.empty() || !value ||
            (channel != BooleanChannel::LeftSecondary &&
             channel != BooleanChannel::RightSecondary)) {
        return;
    }
    if ((channel == BooleanChannel::LeftSecondary && _leftSecondaryApplied) ||
            (channel == BooleanChannel::RightSecondary && _rightSecondaryApplied)) {
        return;
    }
    _booleanAppliedSequence = _acceptedSequence;
    if (channel == BooleanChannel::LeftSecondary) {
        _leftSecondaryApplied = true;
    } else {
        _rightSecondaryApplied = true;
    }
    publishStatus("active", "boolean-consumed", epochMilliseconds);
}

void Protocol::neutralize(const char* state, const char* detail,
                          std::int64_t epochMilliseconds) {
    _current = {};
    _events.clear();
    _eventIndex = 0;
    _activeCommandId.clear();
    ++_generation;
    publishStatus(state, detail, epochMilliseconds);
}

void Protocol::publishStatus(const char* state, const char* detail,
                             std::int64_t epochMilliseconds) const {
    QJsonObject object {
        { "schemaVersion", 1 },
        { "buildMarker", QLatin1String(BUILD_MARKER) },
        { "consumer", QLatin1String(LAYER_NAME) },
        { "profileId", QLatin1String(PROFILE_ID) },
        { "bindingProfileSha256", QLatin1String(PROFILE_SHA256) },
        { "enabled", _current.overrideEnabled },
        { "acceptedSequence", static_cast<double>(_acceptedSequence) },
        { "viewAppliedSequence", static_cast<double>(_viewAppliedSequence) },
        { "viewAppliedYawDegrees", _viewAppliedYawDegrees },
        { "viewAppliedPitchDegrees", _viewAppliedPitchDegrees },
        { "vectorAppliedSequence", static_cast<double>(_vectorAppliedSequence) },
        { "leftThumbstickAppliedY", _leftThumbstickAppliedY },
        { "booleanAppliedSequence", static_cast<double>(_booleanAppliedSequence) },
        { "leftSecondaryApplied", _leftSecondaryApplied },
        { "rightSecondaryApplied", _rightSecondaryApplied },
        { "acceptedNonce", QString::fromStdString(_acceptedNonce) },
        { "activeCommandId", QString::fromStdString(_activeCommandId) },
        { "state", QLatin1String(state) },
        { "detail", QLatin1String(detail) },
        { "updatedEpochMs", static_cast<double>(epochMilliseconds) },
    };
    const QByteArray rendered = QJsonDocument(object).toJson(QJsonDocument::Compact) + '\n';
    const std::string temporary = std::string(INPUT_DIRECTORY) + "/status.json.tmp";
    const std::string destination = std::string(INPUT_DIRECTORY) + "/status.json";
    const int descriptor = open(temporary.c_str(),
                                O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC | O_NOFOLLOW,
                                0600);
    if (descriptor < 0) {
        return;
    }
    const bool written = writeAll(descriptor, rendered);
    close(descriptor);
    if (!written || chmod(temporary.c_str(), 0600) != 0 ||
            rename(temporary.c_str(), destination.c_str()) != 0) {
        unlink(temporary.c_str());
        logWarning("could not commit E2E OpenXR status");
    }
}

}  // namespace overte::e2e::openxr
