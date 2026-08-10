//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "AppDelegate.h"

#import <AVFoundation/AVFoundation.h>
#import <os/log.h>

#import "SceneDelegate.h"

#include "LifecycleStateMachine.h"

namespace {
os_log_t lifecycleLog() {
    static os_log_t log = os_log_create("org.overte.interface", "lifecycle");
    return log;
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
                                                 AVAudioSessionCategoryOptionAllowBluetooth)
                                          error:&error];
    if (!configured) {
        os_log_error(lifecycleLog(), "Audio session configuration failed: %{public}@", error);
    }

    self.audioInterruptionObserver = [NSNotificationCenter.defaultCenter
        addObserverForName:AVAudioSessionInterruptionNotification
                    object:audioSession
                     queue:NSOperationQueue.mainQueue
                usingBlock:^(NSNotification* notification) {
        NSNumber* typeValue = notification.userInfo[AVAudioSessionInterruptionTypeKey];
        AVAudioSessionInterruptionType type = (AVAudioSessionInterruptionType)typeValue.unsignedIntegerValue;
        if (type == AVAudioSessionInterruptionTypeBegan) {
            os_log_info(lifecycleLog(), "Audio interruption began");
        } else {
            NSNumber* optionValue = notification.userInfo[AVAudioSessionInterruptionOptionKey];
            BOOL shouldResume = (optionValue.unsignedIntegerValue &
                                 AVAudioSessionInterruptionOptionShouldResume) != 0;
            os_log_info(lifecycleLog(), "Audio interruption ended; should resume: %{public}s",
                        shouldResume ? "yes" : "no");
        }
    }];
    self.audioRouteObserver = [NSNotificationCenter.defaultCenter
        addObserverForName:AVAudioSessionRouteChangeNotification
                    object:audioSession
                     queue:NSOperationQueue.mainQueue
                usingBlock:^(NSNotification* notification) {
        NSNumber* reasonValue = notification.userInfo[AVAudioSessionRouteChangeReasonKey];
        os_log_info(lifecycleLog(), "Audio route changed; reason: %lu",
                    (unsigned long)reasonValue.unsignedIntegerValue);
    }];

    os_log_info(lifecycleLog(), "Overte iOS bootstrap launched");
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
        initWithName:@"Default Configuration" sessionRole:UISceneSessionRoleApplication];
    configuration.sceneClass = UIWindowScene.class;
    configuration.delegateClass = SceneDelegate.class;
    return configuration;
}

- (void)applicationDidBecomeActive:(UIApplication*)application {
    (void)application;
    os_log_info(lifecycleLog(), "Application became active");
}

- (void)applicationWillResignActive:(UIApplication*)application {
    (void)application;
    os_log_info(lifecycleLog(), "Application will resign active");
}

- (void)applicationDidEnterBackground:(UIApplication*)application {
    (void)application;
    os_log_info(lifecycleLog(), "Application entered background");
}

- (void)applicationWillEnterForeground:(UIApplication*)application {
    (void)application;
    os_log_info(lifecycleLog(), "Application will enter foreground");
}

- (void)applicationDidReceiveMemoryWarning:(UIApplication*)application {
    (void)application;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidReceiveMemoryWarning);
    os_log_error(lifecycleLog(), "Application received a memory warning");
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
    os_log_info(lifecycleLog(), "Application will terminate");
}

@end
