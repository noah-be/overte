//
// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
//

#import "SceneDelegate.h"

#import <os/log.h>

#import "BootstrapViewController.h"

NSNotificationName const OverteOpenURLNotification = @"org.overte.interface.open-url";

namespace {
os_log_t sceneLog() {
    static os_log_t log = os_log_create("org.overte.interface", "scene");
    return log;
}
}

@implementation SceneDelegate

- (void)scene:(UIScene*)scene
        willConnectToSession:(UISceneSession*)session
        options:(UISceneConnectionOptions*)connectionOptions {
    (void)session;
    (void)connectionOptions;
    if (![scene isKindOfClass:UIWindowScene.class]) {
        return;
    }

    UIWindowScene* windowScene = (UIWindowScene*)scene;
    self.window = [[UIWindow alloc] initWithWindowScene:windowScene];
    self.window.rootViewController = [[BootstrapViewController alloc] init];
    [self.window makeKeyAndVisible];
    os_log_info(sceneLog(), "Scene connected");
}

- (void)sceneDidBecomeActive:(UIScene*)scene {
    (void)scene;
    os_log_info(sceneLog(), "Scene became active");
}

- (void)sceneWillResignActive:(UIScene*)scene {
    (void)scene;
    os_log_info(sceneLog(), "Scene will resign active");
}

- (void)sceneDidEnterBackground:(UIScene*)scene {
    (void)scene;
    os_log_info(sceneLog(), "Scene entered background");
}

- (void)sceneWillEnterForeground:(UIScene*)scene {
    (void)scene;
    os_log_info(sceneLog(), "Scene will enter foreground");
}

- (void)scene:(UIScene*)scene openURLContexts:(NSSet<UIOpenURLContext*>*)URLContexts {
    (void)scene;
    NSSet<NSString*>* allowedSchemes = [NSSet setWithObjects:@"overte", @"hifi", nil];
    for (UIOpenURLContext* context in URLContexts) {
        NSURL* url = context.URL;
        NSString* scheme = url.scheme.lowercaseString;
        if (url != nil && [allowedSchemes containsObject:scheme]) {
            // Do not log the complete URL; locations can contain sensitive
            // path and query data. The integrated client consumes the object
            // through the notification on its application thread.
            os_log_info(sceneLog(), "Accepted deep link with scheme %{public}@", scheme);
            [NSNotificationCenter.defaultCenter postNotificationName:OverteOpenURLNotification
                                                               object:url];
        } else {
            os_log_error(sceneLog(), "Rejected unsupported deep-link scheme");
        }
    }
}

@end
