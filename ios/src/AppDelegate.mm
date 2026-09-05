//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "AppDelegate.h"

#import <AVFoundation/AVFoundation.h>

#import "SceneDelegate.h"

#include "LifecycleStateMachine.h"
#include "RedactingDiagnostics.h"

namespace {
using Event = overte::security::DiagnosticEvent;
using overte::ios::logSharedDiagnostic;

bool setAudioSessionActive(bool active, AVAudioSessionSetActiveOptions options = 0) {
    NSError* error = nil;
    BOOL changed = [AVAudioSession.sharedInstance setActive:active withOptions:options error:&error];
    if (!changed) {
        overte::ios::logDiagnostic(active ? overte::ios::DiagnosticEvent::AudioActivationFailed
                                         : overte::ios::DiagnosticEvent::AudioDeactivationFailed);
    }
    return changed;
}
}

@interface AppDelegate ()
@property(nonatomic, strong) id audioInterruptionObserver;
@property(nonatomic, strong) id audioRouteObserver;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication*)application
        didFinishLaunchingWithOptions:(NSDictionary<UIApplicationLaunchOptionsKey, id>*)launchOptions {
    (void)application;
    (void)launchOptions;

    AVAudioSession* audioSession = AVAudioSession.sharedInstance;
    NSError* error = nil;
    BOOL configured = [audioSession setCategory:AVAudioSessionCategoryPlayAndRecord
                                           mode:AVAudioSessionModeGameChat
                                        options:(AVAudioSessionCategoryOptionDefaultToSpeaker |
                                                 AVAudioSessionCategoryOptionAllowBluetoothHFP)
                                          error:&error];
    if (!configured) {
        overte::ios::logDiagnostic(overte::ios::DiagnosticEvent::AudioConfigurationFailed);
    }

    AVAudioSessionRecordPermission permission = audioSession.recordPermission;
    if (permission == AVAudioSessionRecordPermissionUndetermined) {
        [audioSession requestRecordPermission:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{
                logSharedDiagnostic(granted ? Event::PermissionGranted : Event::PermissionDenied);
            });
        }];
    } else {
        logSharedDiagnostic(permission == AVAudioSessionRecordPermissionGranted
            ? Event::PermissionGranted : Event::PermissionDenied);
    }

    self.audioInterruptionObserver = [NSNotificationCenter.defaultCenter
        addObserverForName:AVAudioSessionInterruptionNotification
                    object:audioSession
                     queue:NSOperationQueue.mainQueue
                usingBlock:^(NSNotification* notification) {
        NSNumber* typeValue = notification.userInfo[AVAudioSessionInterruptionTypeKey];
        AVAudioSessionInterruptionType type = (AVAudioSessionInterruptionType)typeValue.unsignedIntegerValue;
        if (type == AVAudioSessionInterruptionTypeBegan) {
            logSharedDiagnostic(Event::AudioInterrupted);
        } else {
            NSNumber* optionValue = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            BOOL shouldResume = (optionValue.unsignedIntegerValue &
                                 AVAudioSessionInterruptionOptionShouldResume) != 0;
            logSharedDiagnostic(Event::AudioStopped);
            if (shouldResume) {
                setAudioSessionActive(true);
            }
        }
    }];
    self.audioRouteObserver = [NSNotificationCenter.defaultCenter
        addObserverForName:AVAudioSessionRouteChangeNotification
                    object:audioSession
                     queue:NSOperationQueue.mainQueue
                usingBlock:^(NSNotification* notification) {
        (void)notification;
        logSharedDiagnostic(Event::AudioStopped);
    }];

    logSharedDiagnostic(Event::LifecycleResumed);
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidFinishLaunching);
    return YES;
}

- (UISceneConfiguration*)application:(UIApplication*)application
        configurationForConnectingSceneSession:(UISceneSession*)connectingSceneSession
        options:(UISceneConnectionOptions*)options {
    (void)application;
    (void)connectingSceneSession;
    (void)options;
    UISceneConfiguration* configuration = [[UISceneConfiguration alloc]
        initWithName:@"Default Configuration" sessionRole:UIWindowSceneSessionRoleApplication];
    configuration.sceneClass = UIWindowScene.class;
    configuration.delegateClass = SceneDelegate.class;
    return configuration;
}

- (void)applicationDidBecomeActive:(UIApplication*)application {
    (void)application;
    setAudioSessionActive(true);
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)applicationWillResignActive:(UIApplication*)application {
    (void)application;
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)applicationDidEnterBackground:(UIApplication*)application {
    (void)application;
    setAudioSessionActive(false, AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation);
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)applicationWillEnterForeground:(UIApplication*)application {
    (void)application;
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)applicationDidReceiveMemoryWarning:(UIApplication*)application {
    (void)application;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidReceiveMemoryWarning);
    logSharedDiagnostic(Event::Redacted);
}

- (void)applicationWillTerminate:(UIApplication*)application {
    (void)application;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::WillTerminate);
    NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
    if (self.audioInterruptionObserver != nil) {
        [center removeObserver:self.audioInterruptionObserver];
    }
    if (self.audioRouteObserver != nil) {
        [center removeObserver:self.audioRouteObserver];
    }
    logSharedDiagnostic(Event::LifecycleSuspended);
}

@end
