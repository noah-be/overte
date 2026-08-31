//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "SceneDelegate.h"

#import <os/log.h>

#import "BootstrapViewController.h"

#include "PendingDeepLinkStore.h"
#include "LifecycleStateMachine.h"

NSNotificationName const OverteOpenURLNotification = @"org.overte.interface.open-url";

namespace {
os_log_t sceneLog() {
    static os_log_t log = os_log_create("org.overte.interface", "scene");
    return log;
}

void routeURLContexts(NSSet<UIOpenURLContext*>* URLContexts) {
    for (UIOpenURLContext* context in URLContexts) {
        NSURL* url = context.URL;
        NSString* scheme = url.scheme.lowercaseString;
        const char* encodedURL = url.absoluteString.UTF8String;
        auto result = encodedURL != nullptr
            ? overte::ios::PendingDeepLinkStore::instance().enqueue(encodedURL)
            : overte::ios::DeepLinkEnqueueResult::Invalid;
        if (result == overte::ios::DeepLinkEnqueueResult::Accepted) {
            // Do not log the complete URL; locations can contain sensitive
            // path and query data. The notification is only a wake-up edge;
            // the integrated client drains PendingDeepLinkStore exactly once.
            os_log_info(sceneLog(), "Accepted deep link with scheme %{public}@", scheme);
            [NSNotificationCenter.defaultCenter postNotificationName:OverteOpenURLNotification object:nil];
        } else if (result == overte::ios::DeepLinkEnqueueResult::Duplicate) {
            os_log_info(sceneLog(), "Ignored duplicate deep link with scheme %{public}@", scheme);
        } else {
            os_log_error(sceneLog(), "Rejected invalid, unsupported, or excessive deep link");
        }
    }
}
}

@implementation SceneDelegate

- (void)scene:(UIScene*)scene
        willConnectToSession:(UISceneSession*)session
        options:(UISceneConnectionOptions*)connectionOptions {
    (void)session;
    if (![scene isKindOfClass:UIWindowScene.class]) {
        return;
    }

    UIWindowScene* windowScene = (UIWindowScene*)scene;
    self.window = [[UIWindow alloc] initWithWindowScene:windowScene];
    self.window.rootViewController = [[BootstrapViewController alloc] init];
    [self.window makeKeyAndVisible];
    os_log_info(sceneLog(), "Scene connected");
    routeURLContexts(connectionOptions.URLContexts);
}

- (void)sceneDidBecomeActive:(UIScene*)scene {
    (void)scene;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidBecomeActive);
    os_log_info(sceneLog(), "Scene became active");
}

- (void)sceneWillResignActive:(UIScene*)scene {
    (void)scene;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::WillResignActive);
    os_log_info(sceneLog(), "Scene will resign active");
}

- (void)sceneDidEnterBackground:(UIScene*)scene {
    (void)scene;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidEnterBackground);
    os_log_info(sceneLog(), "Scene entered background");
}

- (void)sceneWillEnterForeground:(UIScene*)scene {
    (void)scene;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::WillEnterForeground);
    os_log_info(sceneLog(), "Scene will enter foreground");
}

- (void)scene:(UIScene*)scene openURLContexts:(NSSet<UIOpenURLContext*>*)URLContexts {
    (void)scene;
    routeURLContexts(URLContexts);
}

@end
