//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "SceneDelegate.h"


#import "BootstrapViewController.h"
#import "AppDelegate.h"

#include "PendingDeepLinkStore.h"
#include "LifecycleStateMachine.h"
#include "RedactingDiagnostics.h"

NSNotificationName const OverteOpenURLNotification = @"org.overte.interface.open-url";

namespace {
using Event = overte::security::DiagnosticEvent;
using overte::ios::logSharedDiagnostic;

void routeURLContexts(NSSet<UIOpenURLContext*>* URLContexts) {
    for (UIOpenURLContext* context in URLContexts) {
        NSURL* url = context.URL;
        const char* encodedURL = url.absoluteString.UTF8String;
        auto result = encodedURL != nullptr
            ? overte::ios::PendingDeepLinkStore::instance().enqueue(encodedURL)
            : overte::ios::DeepLinkEnqueueResult::Invalid;
        if (result == overte::ios::DeepLinkEnqueueResult::Accepted) {
            // Do not log the complete URL; locations can contain sensitive
            // path and query data. The notification is only a wake-up edge;
            // the integrated client drains PendingDeepLinkStore exactly once.
            logSharedDiagnostic(Event::Redacted); // enqueue is not connection success
            [NSNotificationCenter.defaultCenter postNotificationName:OverteOpenURLNotification object:nil];
        } else if (result == overte::ios::DeepLinkEnqueueResult::Duplicate) {
            logSharedDiagnostic(Event::CallbackDiscarded);
        } else {
            logSharedDiagnostic(Event::UrlRejected);
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
    logSharedDiagnostic(Event::LifecycleResumed);
    routeURLContexts(connectionOptions.URLContexts);
}

- (void)sceneDidBecomeActive:(UIScene*)scene {
    (void)scene;
    [(AppDelegate*)UIApplication.sharedApplication.delegate setAudioForeground:YES];
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidBecomeActive);
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)sceneWillResignActive:(UIScene*)scene {
    (void)scene;
    [(AppDelegate*)UIApplication.sharedApplication.delegate setAudioForeground:NO];
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::WillResignActive);
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)sceneDidEnterBackground:(UIScene*)scene {
    (void)scene;
    [(AppDelegate*)UIApplication.sharedApplication.delegate setAudioForeground:NO];
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::DidEnterBackground);
    logSharedDiagnostic(Event::LifecycleSuspended);
}

- (void)sceneWillEnterForeground:(UIScene*)scene {
    (void)scene;
    overte::ios::LifecycleStateMachine::instance().apply(
        overte::ios::LifecycleEvent::WillEnterForeground);
    logSharedDiagnostic(Event::LifecycleResumed);
}

- (void)scene:(UIScene*)scene openURLContexts:(NSSet<UIOpenURLContext*>*)URLContexts {
    (void)scene;
    routeURLContexts(URLContexts);
}

@end
