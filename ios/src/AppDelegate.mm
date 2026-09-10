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
@property(nonatomic) BOOL audioForeground;
@property(nonatomic) BOOL audioConfigured;
@property(nonatomic) BOOL audioInterrupted;
@property(nonatomic) BOOL audioResumeAllowed;
@end

@implementation AppDelegate

- (BOOL)application:(UIApplication*)application
        didFinishLaunchingWithOptions:(NSDictionary<UIApplicationLaunchOptionsKey, id>*)launchOptions {
    (void)application;
    (void)launchOptions;

    AVAudioSession* audioSession = AVAudioSession.sharedInstance;
    NSError* error = nil;
    // The preview has no voice-input caller. Do not prompt for a microphone or
    // configure recording merely to display its native scene.
    BOOL configured = [audioSession setCategory:AVAudioSessionCategoryPlayback
                                           mode:AVAudioSessionModeDefault
                                        options:0
                                          error:&error];
    if (!configured) {
        overte::ios::logDiagnostic(overte::ios::DiagnosticEvent::AudioConfigurationFailed);
    }

    self.audioConfigured = configured;
    self.audioResumeAllowed = YES;
    __weak AppDelegate* weakSelf = self;
    self.audioInterruptionObserver = [NSNotificationCenter.defaultCenter
        addObserverForName:AVAudioSessionInterruptionNotification
                    object:audioSession
                     queue:NSOperationQueue.mainQueue
                usingBlock:^(NSNotification* notification) {
        NSNumber* typeValue = notification.userInfo[AVAudioSessionInterruptionTypeKey];
        AppDelegate* strongSelf = weakSelf;
        if (strongSelf == nil || ![typeValue isKindOfClass:NSNumber.class]) { return; }
        AVAudioSessionInterruptionType type = (AVAudioSessionInterruptionType)typeValue.unsignedIntegerValue;
        if (type == AVAudioSessionInterruptionTypeBegan) {
            strongSelf.audioInterrupted = YES;
            logSharedDiagnostic(Event::AudioInterrupted);
        } else {
            NSNumber* optionValue = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            BOOL shouldResume = [optionValue isKindOfClass:NSNumber.class] && (optionValue.unsignedIntegerValue &
                                 AVAudioSessionInterruptionOptionShouldResume) != 0;
            strongSelf.audioInterrupted = NO;
            strongSelf.audioResumeAllowed = shouldResume;
            logSharedDiagnostic(Event::AudioStopped);
            if (shouldResume && strongSelf.audioForeground && strongSelf.audioConfigured) {
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
    [self setAudioForeground:YES];
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)applicationWillResignActive:(UIApplication*)application {
    (void)application;
    [self setAudioForeground:NO];
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)applicationDidEnterBackground:(UIApplication*)application {
    (void)application;
    [self setAudioForeground:NO];
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)applicationWillEnterForeground:(UIApplication*)application {
    (void)application;
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)setAudioForeground:(BOOL)foreground {
    if (self.audioForeground == foreground) { return; }
    _audioForeground = foreground;
    if (!foreground) {
        setAudioSessionActive(false, AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation);
    } else if (self.audioConfigured && !self.audioInterrupted && self.audioResumeAllowed) {
        setAudioSessionActive(true);
    }
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
