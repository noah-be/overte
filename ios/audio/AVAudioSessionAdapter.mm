// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSAudioAdapter.h"
#include "../src/RedactingDiagnostics.h"
#import <AVFoundation/AVFoundation.h>
#import <UIKit/UIKit.h>
#include <QCoreApplication>

namespace overte::ios {
namespace {
class AVAudioOperations final : public NativeAudioOperations {
public:
    AVAudioOperations() : _queue(dispatch_queue_create("org.overte.audio.operations", DISPATCH_QUEUE_SERIAL)) {}

    bool activate(bool capture, std::function<bool()> stillCurrent) override {
        return perform([capture, stillCurrent] {
            if (!stillCurrent()) { return false; }
            AVAudioSession* session = AVAudioSession.sharedInstance;
            NSError* error = nil;
            NSString* category = capture ? AVAudioSessionCategoryPlayAndRecord : AVAudioSessionCategoryPlayback;
            NSString* mode = capture ? AVAudioSessionModeGameChat : AVAudioSessionModeDefault;
            AVAudioSessionCategoryOptions options = capture ?
                (AVAudioSessionCategoryOptionDefaultToSpeaker | AVAudioSessionCategoryOptionAllowBluetoothHFP) : 0;
            if (![session setCategory:category mode:mode options:options error:&error]) { return false; }
            if (!stillCurrent()) { return false; }
            return [session setActive:YES error:&error] == YES;
        }, stillCurrent);
    }

    bool deactivate() override {
        return perform([] {
            NSError* error = nil;
            return [AVAudioSession.sharedInstance setActive:NO
                withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:&error] == YES;
        }, [] { return true; });
    }

    audio::Permission permission() override {
        @try {
            switch (AVAudioSession.sharedInstance.recordPermission) {
                case AVAudioSessionRecordPermissionGranted: return audio::Permission::Granted;
                case AVAudioSessionRecordPermissionDenied: return audio::Permission::Denied;
                default: return audio::Permission::Unknown;
            }
        } @catch (NSException*) { return audio::Permission::Revoked; }
    }

    void requestPermission(std::function<bool()> stillCurrent,
                           std::function<void(audio::Permission)> completion) override {
        dispatch_async(dispatch_get_main_queue(), ^{
            @try {
                if (!stillCurrent() ||
                        UIApplication.sharedApplication.applicationState != UIApplicationStateActive) {
                    completion(audio::Permission::Unknown);
                    return;
                }
                [AVAudioSession.sharedInstance requestRecordPermission:^(BOOL granted) {
                    logSharedDiagnostic(granted ? security::DiagnosticEvent::PermissionGranted
                                                : security::DiagnosticEvent::PermissionDenied);
                    completion(granted ? audio::Permission::Granted : audio::Permission::Denied);
                }];
            } @catch (NSException*) { completion(audio::Permission::Revoked); }
        });
    }

private:
    struct Operation {
        dispatch_semaphore_t finished { dispatch_semaphore_create(0) };
        std::atomic<bool> cancelled { false }, succeeded { false };
    };
    bool perform(std::function<bool()> action, std::function<bool()> stillCurrent) {
        bool expected = false;
        // No unbounded queue accumulation while an OS operation is stuck.
        if (!_busy->compare_exchange_strong(expected, true)) { return false; }
        auto operation = std::make_shared<Operation>();
        auto busy = _busy;
        dispatch_async(_queue, ^{
            bool success = false;
          try {
            @try {
                success = !operation->cancelled && action();
                success = success && !operation->cancelled && stillCurrent();
            } @catch (NSException*) { success = false; }
          } catch (...) { success = false; }
            if (!success) {
                // Failure (including exception) can leave the previous capture
                // session active. Attempt native stop, but preserve failure:
                // cleanup is not a successful operation/stop receipt.
                @try {
                    NSError* error = nil;
                    [AVAudioSession.sharedInstance setActive:NO error:&error];
                } @catch (NSException*) {}
            }
            operation->succeeded = success;
            dispatch_semaphore_signal(operation->finished);
        });
        if (dispatch_semaphore_wait(operation->finished, dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC)) != 0) {
            operation->cancelled = true;
            // Keep the executor busy until this serialized cleanup finishes.
            // This also closes the race where timeout arrives after the worker's
            // cancellation check but before its completion semaphore signal.
            dispatch_async(_queue, ^{
                @try {
                    NSError* error = nil;
                    [AVAudioSession.sharedInstance setActive:NO error:&error];
                } @catch (NSException*) {}
                busy->store(false);
            });
            logSharedDiagnostic(security::DiagnosticEvent::Redacted);
            return false; // failure/timeout is not successful native stop
        }
        busy->store(false);
        return operation->succeeded;
    }
    dispatch_queue_t _queue;
    std::shared_ptr<std::atomic<bool>> _busy { std::make_shared<std::atomic<bool>>(false) };
};

void installNativeAudioAdapter() {
    auto adapter = std::make_shared<IOSAudioAdapter>(std::make_shared<AVAudioOperations>());
    if (!audio::installIOSAudioSessionAdapter(adapter)) {
        logSharedDiagnostic(security::DiagnosticEvent::Redacted);
        return;
    }
    dispatch_async(dispatch_get_main_queue(), ^{
        NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
        // Registry is process-lived, as are these observers. Only closed events
        // are retained; route names and device identifiers never leave UIKit.
        [center addObserverForName:UIApplicationDidBecomeActiveNotification object:nil
                             queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*) {
            adapter->foreground(true);
        }];
        [center addObserverForName:UIApplicationWillResignActiveNotification object:nil
                             queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*) {
            adapter->foreground(false);
        }];
        [center addObserverForName:AVAudioSessionInterruptionNotification object:nil
                             queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification* notification) {
            NSNumber* type = notification.userInfo[AVAudioSessionInterruptionTypeKey];
            if (![type isKindOfClass:NSNumber.class]) { return; }
            const bool began = type.unsignedIntegerValue == AVAudioSessionInterruptionTypeBegan;
            NSNumber* options = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            const bool resume = [options isKindOfClass:NSNumber.class] &&
                (options.unsignedIntegerValue & AVAudioSessionInterruptionOptionShouldResume);
            logSharedDiagnostic(security::DiagnosticEvent::AudioInterrupted);
            adapter->interruption(began, resume);
        }];
        [center addObserverForName:AVAudioSessionRouteChangeNotification object:nil
                             queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*) {
            adapter->routeChanged();
        }];
        [center addObserverForName:AVAudioSessionMediaServicesWereResetNotification object:nil
                             queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*) {
            adapter->interruption(false, false); // explicit restart required
        }];
        adapter->foreground(UIApplication.sharedApplication.applicationState == UIApplicationStateActive);
    });
}
}
} // namespace overte::ios
namespace {
void registerIOSNativeAudio() { overte::ios::installNativeAudioAdapter(); }
}
Q_COREAPP_STARTUP_FUNCTION(registerIOSNativeAudio)
