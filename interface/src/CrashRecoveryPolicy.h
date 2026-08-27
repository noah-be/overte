//
//  CrashRecoveryPolicy.h
//  interface/src
//
//  Copyright 2026 Overte e.V.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef overte_CrashRecoveryPolicy_h
#define overte_CrashRecoveryPolicy_h

#include <QtGlobal>

class CrashRecoveryPolicy {
public:
    enum class Platform {
        IOS,
        OTHER
    };

    struct StartupDecision {
        bool previousSessionCrashed;
        bool recoveryEnabled;

        constexpr bool shouldEvaluateSettingsReset() const {
            return recoveryEnabled;
        }

        constexpr bool settingsResetAllowed() const {
            return recoveryEnabled;
        }
    };

    static constexpr StartupDecision evaluateStartup(Platform platform, bool runningMarkerExisted) {
        return { runningMarkerExisted, platform != Platform::IOS };
    }

    static constexpr Platform currentPlatform() {
#if defined(Q_OS_IOS)
        return Platform::IOS;
#else
        return Platform::OTHER;
#endif
    }
};

#endif // overte_CrashRecoveryPolicy_h
