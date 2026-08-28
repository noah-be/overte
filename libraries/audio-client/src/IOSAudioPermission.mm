// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSAudioPermission.h"

#import <AVFoundation/AVFoundation.h>
#import <os/log.h>
#import <pthread.h>

#include <mutex>
#include <utility>

namespace {

void runOnMainQueue(dispatch_block_t block) {
    if (pthread_main_np() != 0) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
}

std::mutex eventHandlerMutex;
OverteIOSAudioSessionEventHandler eventHandler;

OverteIOSMicrophonePermissionState microphonePermissionState(AVAudioSession* session) {
    switch (session.recordPermission) {
        case AVAudioSessionRecordPermissionGranted:
            return OverteIOSMicrophonePermissionState::Granted;
        case AVAudioSessionRecordPermissionDenied:
            return OverteIOSMicrophonePermissionState::Denied;
        case AVAudioSessionRecordPermissionUndetermined:
        default:
            return OverteIOSMicrophonePermissionState::Undetermined;
    }
}

void notifyAudioSessionEvent(OverteIOSAudioSessionEvent event, bool shouldResume = false,
                             unsigned long reason = 0) {
    OverteIOSAudioSessionEventHandler handler;
    {
        std::lock_guard<std::mutex> guard(eventHandlerMutex);
        handler = eventHandler;
    }
    if (handler) {
        handler(event, shouldResume, reason);
    }
}

void installAudioSessionObservers(AVAudioSession* session) {
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
                notifyAudioSessionEvent(OverteIOSAudioSessionEvent::InterruptionBegan);
                return;
            }
            NSNumber* optionValue = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            const bool shouldResume =
                (optionValue.unsignedIntegerValue & AVAudioSessionInterruptionOptionShouldResume) != 0;
            os_log_info(OS_LOG_DEFAULT,
                        "Overte full-client audio session interruption ended; should-resume=%{public}s",
                        shouldResume ? "true" : "false");
            notifyAudioSessionEvent(OverteIOSAudioSessionEvent::InterruptionEnded, shouldResume);
        }];

        [NSNotificationCenter.defaultCenter
            addObserverForName:AVAudioSessionRouteChangeNotification
                        object:session
                         queue:NSOperationQueue.mainQueue
                    usingBlock:^(NSNotification* notification) {
            NSNumber* reasonValue = notification.userInfo[AVAudioSessionRouteChangeReasonKey];
            const unsigned long reason = reasonValue.unsignedLongValue;
            os_log_info(OS_LOG_DEFAULT,
                        "Overte full-client audio route changed; reason=%{public}lu inputs=%{public}lu outputs=%{public}lu",
                        reason, (unsigned long)session.currentRoute.inputs.count,
                        (unsigned long)session.currentRoute.outputs.count);
            notifyAudioSessionEvent(OverteIOSAudioSessionEvent::RouteChanged, false, reason);
        }];

        [NSNotificationCenter.defaultCenter
            addObserverForName:AVAudioSessionMediaServicesWereResetNotification
                        object:session
                         queue:NSOperationQueue.mainQueue
                    usingBlock:^(__unused NSNotification* notification) {
            os_log_info(OS_LOG_DEFAULT, "Overte full-client audio media services were reset");
            notifyAudioSessionEvent(OverteIOSAudioSessionEvent::MediaServicesReset);
        }];
    });
}

} // namespace

OverteIOSMicrophonePermissionState overteIOSMicrophonePermissionState() {
    return microphonePermissionState(AVAudioSession.sharedInstance);
}

bool overteIOSMicrophonePermissionGranted() {
    return overteIOSMicrophonePermissionState() == OverteIOSMicrophonePermissionState::Granted;
}

void overteIOSRequestMicrophonePermission(OverteIOSMicrophonePermissionHandler handler) {
    dispatch_async(dispatch_get_main_queue(), ^{
        AVAudioSession* session = AVAudioSession.sharedInstance;
        const auto state = microphonePermissionState(session);
        if (state != OverteIOSMicrophonePermissionState::Undetermined) {
            if (handler) {
                handler(state);
            }
            return;
        }
        if (handler) {
            handler(state);
        }
        [session requestRecordPermission:^(BOOL granted) {
            const auto resolvedState = granted ? OverteIOSMicrophonePermissionState::Granted
                                               : OverteIOSMicrophonePermissionState::Denied;
            os_log_info(OS_LOG_DEFAULT, "Overte microphone permission resolved: %{public}s",
                        granted ? "granted" : "denied");
            if (handler) {
                handler(resolvedState);
            }
        }];
    });
}

void overteIOSSetAudioSessionEventHandler(OverteIOSAudioSessionEventHandler handler) {
    std::lock_guard<std::mutex> guard(eventHandlerMutex);
    eventHandler = std::move(handler);
}

bool overteIOSActivateAudioSession() {
    __block BOOL activated = NO;
    runOnMainQueue(^{
        AVAudioSession* session = AVAudioSession.sharedInstance;
        installAudioSessionObservers(session);
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
        if (![session setPreferredSampleRate:48000.0 error:&error]) {
            os_log_error(OS_LOG_DEFAULT,
                         "Overte preferred audio sample rate failed; code=%{public}ld",
                         (long)(error ? error.code : 0));
        }
        error = nil;
        if (![session setPreferredIOBufferDuration:0.01 error:&error]) {
            os_log_error(OS_LOG_DEFAULT,
                         "Overte preferred audio buffer duration failed; code=%{public}ld",
                         (long)(error ? error.code : 0));
        }
        error = nil;
        activated = [session setActive:YES error:&error];
        os_log_info(OS_LOG_DEFAULT,
                    "Overte full-client audio session activation=%{public}s code=%{public}ld rate=%{public}.0f buffer-ms=%{public}.1f",
                    activated ? "ok" : "failed", (long)(error ? error.code : 0),
                    session.sampleRate, session.IOBufferDuration * 1000.0);
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
