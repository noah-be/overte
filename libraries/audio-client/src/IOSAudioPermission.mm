// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSAudioPermission.h"

#import <AVFoundation/AVFoundation.h>
#import <os/log.h>

bool overteIOSMicrophonePermissionGranted() {
    return AVAudioSession.sharedInstance.recordPermission == AVAudioSessionRecordPermissionGranted;
}

void overteIOSRequestMicrophonePermission() {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        dispatch_async(dispatch_get_main_queue(), ^{
            AVAudioSession* session = AVAudioSession.sharedInstance;
            if (session.recordPermission != AVAudioSessionRecordPermissionUndetermined) {
                return;
            }
            [session requestRecordPermission:^(BOOL granted) {
                os_log_info(OS_LOG_DEFAULT, "Overte microphone permission resolved: %{public}s",
                            granted ? "granted" : "denied");
            }];
        });
    });
}
