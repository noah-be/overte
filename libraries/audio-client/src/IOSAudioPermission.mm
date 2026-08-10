// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSAudioPermission.h"

#import <AVFoundation/AVFoundation.h>
#import <os/log.h>
#import <pthread.h>

namespace {

void runOnMainQueue(dispatch_block_t block) {
    if (pthread_main_np() != 0) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
}

void installInterruptionTelemetry(AVAudioSession* session) {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        [NSNotificationCenter.defaultCenter
            addObserverForName:AVAudioSessionInterruptionNotification
                        object:session
                         queue:NSOperationQueue.mainQueue
                    usingBlock:^(NSNotification* notification) {
            NSNumber* typeValue = notification.userInfo[AVAudioSessionInterruptionTypeKey];
            if (typeValue.unsignedIntegerValue == AVAudioSessionInterruptionTypeBegan) {
                os_log_info(OS_LOG_DEFAULT, "Overte full-client audio session interruption began");
                return;
            }
            NSNumber* optionValue = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            const bool shouldResume =
                (optionValue.unsignedIntegerValue & AVAudioSessionInterruptionOptionShouldResume) != 0;
            os_log_info(OS_LOG_DEFAULT,
                        "Overte full-client audio session interruption ended; should-resume=%{public}s",
                        shouldResume ? "true" : "false");
            if (shouldResume) {
                NSError* error = nil;
                const BOOL active = [session setActive:YES error:&error];
                os_log_info(OS_LOG_DEFAULT,
                            "Overte full-client audio session interruption reactivation=%{public}s code=%{public}ld",
                            active ? "ok" : "failed", (long)(error ? error.code : 0));
            }
        }];
    });
}

} // namespace

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

bool overteIOSActivateAudioSession() {
    __block BOOL activated = NO;
    runOnMainQueue(^{
        AVAudioSession* session = AVAudioSession.sharedInstance;
        installInterruptionTelemetry(session);
        NSError* error = nil;
        const AVAudioSessionCategoryOptions options =
            AVAudioSessionCategoryOptionDefaultToSpeaker |
            AVAudioSessionCategoryOptionAllowBluetoothHFP;
        if (![session setCategory:AVAudioSessionCategoryPlayAndRecord
                              mode:AVAudioSessionModeGameChat
                           options:options
                             error:&error]) {
            os_log_error(OS_LOG_DEFAULT,
                         "Overte full-client audio session configuration failed; code=%{public}ld",
                         (long)(error ? error.code : 0));
            return;
        }
        error = nil;
        activated = [session setActive:YES error:&error];
        os_log_info(OS_LOG_DEFAULT,
                    "Overte full-client audio session activation=%{public}s code=%{public}ld",
                    activated ? "ok" : "failed", (long)(error ? error.code : 0));
    });
    return activated == YES;
}

bool overteIOSDeactivateAudioSession() {
    __block BOOL deactivated = NO;
    runOnMainQueue(^{
        NSError* error = nil;
        deactivated = [AVAudioSession.sharedInstance
            setActive:NO
            withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation
            error:&error];
        os_log_info(OS_LOG_DEFAULT,
                    "Overte full-client audio session deactivation=%{public}s code=%{public}ld",
                    deactivated ? "ok" : "failed", (long)(error ? error.code : 0));
    });
    return deactivated == YES;
}
