// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IPadLandscapePolicy.h"
#import <UIKit/UIKit.h>
#import <objc/runtime.h>

#include <shared/IOSRuntimeLogging.h>

namespace {
char installedKey;
char requestedKey;
char orientationKey;

UIInterfaceOrientationMask landscapeOrientations(id, SEL) {
    return UIInterfaceOrientationMaskLandscape;
}

UIInterfaceOrientation preferredLandscape(UIViewController* controller, SEL) {
    UIInterfaceOrientation current = controller.view.window.windowScene.interfaceOrientation;
    return UIInterfaceOrientationIsLandscape(current) ? current : UIInterfaceOrientationLandscapeRight;
}

BOOL preferOrientationLock(UIViewController* controller, SEL) {
    // Do not lock an initial portrait scene before its landscape request wins.
    return UIInterfaceOrientationIsLandscape(controller.view.window.windowScene.interfaceOrientation);
}

// Qt owns the root controller. Subclass only this iPad instance, retaining its
// complete inheritance and view/input implementation. Do not replace the root,
// swizzle UIKit globally, or depend on a private Qt class name/header.
bool installControllerPolicy(UIViewController* controller) {
    if (objc_getAssociatedObject(controller, &installedKey)) {
        return true;
    }
    Class base = object_getClass(controller);
    NSString* name = [@"OverteIPadLandscape_" stringByAppendingString:NSStringFromClass(base)];
    Class policy = NSClassFromString(name);
    if (!policy) {
        policy = objc_allocateClassPair(base, name.UTF8String, 0);
        if (!policy) { return false; }
        Method mask = class_getInstanceMethod(UIViewController.class, @selector(supportedInterfaceOrientations));
        Method preferred = class_getInstanceMethod(UIViewController.class, @selector(preferredInterfaceOrientationForPresentation));
        class_addMethod(policy, @selector(supportedInterfaceOrientations),
                        reinterpret_cast<IMP>(landscapeOrientations), method_getTypeEncoding(mask));
        class_addMethod(policy, @selector(preferredInterfaceOrientationForPresentation),
                        reinterpret_cast<IMP>(preferredLandscape), method_getTypeEncoding(preferred));
        if (@available(iOS 26.0, *)) {
            Method locked = class_getInstanceMethod(UIViewController.class, @selector(prefersInterfaceOrientationLocked));
            class_addMethod(policy, @selector(prefersInterfaceOrientationLocked),
                            reinterpret_cast<IMP>(preferOrientationLock), method_getTypeEncoding(locked));
        }
        objc_registerClassPair(policy);
    }
    if (class_getSuperclass(policy) != base) { return false; }
    object_setClass(controller, policy);
    objc_setAssociatedObject(controller, &installedKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    [controller setNeedsUpdateOfSupportedInterfaceOrientations];
    return true;
}
} // namespace

void applyIPadLandscapePolicy(UIWindow* window) {
    NSCAssert(NSThread.isMainThread, @"iPad orientation policy requires the UIKit main thread");
    if (!window || window.traitCollection.userInterfaceIdiom != UIUserInterfaceIdiomPad) { return; }
    UIViewController* controller = window.rootViewController;
    UIWindowScene* scene = window.windowScene;
    if (!controller || !scene || !installControllerPolicy(controller)) { return; }

    NSNumber* orientation = @(scene.interfaceOrientation);
    NSNumber* previous = objc_getAssociatedObject(controller, &orientationKey);
    if (![previous isEqual:orientation]) {
        objc_setAssociatedObject(controller, &orientationKey, orientation, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        if (@available(iOS 26.0, *)) {
            [controller setNeedsUpdateOfPrefersInterfaceOrientationLocked];
        }
    }
    if (UIInterfaceOrientationIsLandscape(scene.interfaceOrientation)) { return; }
    if (scene.activationState != UISceneActivationStateForegroundActive ||
        [objc_getAssociatedObject(controller, &requestedKey) boolValue]) { return; }

    objc_setAssociatedObject(controller, &requestedKey, @YES, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    UIWindowSceneGeometryPreferencesIOS* geometry = [[UIWindowSceneGeometryPreferencesIOS alloc]
        initWithInterfaceOrientations:UIInterfaceOrientationMaskLandscape];
    __weak UIViewController* weakController = controller;
    [scene requestGeometryUpdateWithPreferences:geometry errorHandler:^(NSError* error) {
        if (weakController) {
            objc_setAssociatedObject(weakController, &requestedKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
        (void)error;
        // Use the existing closed diagnostic vocabulary; do not log UIKit's
        // potentially identifying error description or geometry payload.
        logIOSRuntimeEvent(overte::security::DiagnosticEvent::Redacted);
    }];
    // Permit a future external geometry change to request landscape again.
    dispatch_async(dispatch_get_main_queue(), ^{
        if (weakController) {
            objc_setAssociatedObject(weakController, &requestedKey, @NO, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        }
    });
}
