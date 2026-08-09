//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "AppDelegate.h"

#import <AVFoundation/AVFoundation.h>
#import <os/log.h>

namespace {
os_log_t lifecycleLog() {
    static os_log_t log = os_log_create("org.overte.interface", "lifecycle");
    return log;
}
}

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

    os_log_info(lifecycleLog(), "Overte iOS bootstrap launched");
    return YES;
}

- (UISceneConfiguration*)application:(UIApplication*)application
        configurationForConnectingSceneSession:(UISceneSession*)connectingSceneSession
        options:(UISceneConnectionOptions*)options {
    (void)application;
    (void)connectingSceneSession;
    (void)options;
    return [[UISceneConfiguration alloc] initWithName:@"Default Configuration"
                                         sessionRole:UISceneSessionRoleApplication];
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
    os_log_error(lifecycleLog(), "Application received a memory warning");
}

@end
