// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSTouchUiMetrics.h"

#import <UIKit/UIKit.h>

#include <algorithm>
#include <cmath>

#include <QCoreApplication>
#include <QJSEngine>
#include <QQmlEngine>
#include <QTimer>
#include <QtQml>

namespace {
UIWindow* activeWindow() {
    UIWindow* fallback = nil;
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class] ||
            scene.activationState == UISceneActivationStateUnattached) {
            continue;
        }
        for (UIWindow* window in ((UIWindowScene*)scene).windows) {
            if (window.isKeyWindow) {
                return window;
            }
            if (fallback == nil && !window.hidden) {
                fallback = window;
            }
        }
    }
    return fallback;
}

bool changed(qreal first, qreal second) {
    return std::abs(first - second) > 0.01;
}

void dismissActiveWindowEditing() {
    if (UIWindow* window = activeWindow()) {
        // QInputMethod::hide() can dismiss the keyboard while leaving its
        // input-assistant/QuickType bar attached to a hidden QML editor.
        // Ending UIKit editing clears that stale first responder as well.
        [window endEditing:YES];
    }
}
}

IOSTouchUiMetrics::IOSTouchUiMetrics(QObject* parent) : QObject(parent) {
    NSMutableArray* tokens = [NSMutableArray array];
    NSNotificationCenter* center = NSNotificationCenter.defaultCenter;
    NSArray<NSNotificationName>* names = @[
        UIApplicationDidBecomeActiveNotification,
        UIWindowDidBecomeKeyNotification,
        UIContentSizeCategoryDidChangeNotification,
        UIDeviceOrientationDidChangeNotification,
        UIKeyboardWillChangeFrameNotification,
        UIKeyboardWillHideNotification
    ];
    for (NSNotificationName name in names) {
        id token = [center addObserverForName:name object:nil queue:NSOperationQueue.mainQueue
                                   usingBlock:^(NSNotification* notification) {
            refresh((__bridge void*)notification);
        }];
        [tokens addObject:token];
    }
    _notificationTokens = (__bridge_retained void*)tokens;
    refresh();
    // During Application::initializeUi() UIKit may publish the key window one
    // event-loop turn later. This queued refresh is observed by the native
    // metrics publisher even when DidBecomeActive already fired.
    QTimer::singleShot(0, this, [this] { refresh(); });
}

IOSTouchUiMetrics::~IOSTouchUiMetrics() {
    NSArray* tokens = (__bridge_transfer NSArray*)_notificationTokens;
    for (id token in tokens) {
        [NSNotificationCenter.defaultCenter removeObserver:token];
    }
}

void IOSTouchUiMetrics::refresh(void* keyboardNotification) {
    UIWindow* window = activeWindow();
    if (window == nil) {
        return;
    }

    UIEdgeInsets insets = window.safeAreaInsets;
    CGRect bounds = window.bounds;
    qreal imeInset = _imeInsetBottom;
    bool keyboardIsVisible = _keyboardVisible;
    NSNotification* notification = (__bridge NSNotification*)keyboardNotification;
    if ([notification.name isEqualToString:UIKeyboardWillHideNotification]) {
        imeInset = 0.0;
        keyboardIsVisible = false;
    } else if ([notification.name isEqualToString:UIKeyboardWillChangeFrameNotification]) {
        NSValue* frameValue = notification.userInfo[UIKeyboardFrameEndUserInfoKey];
        CGRect keyboardFrame = [window convertRect:frameValue.CGRectValue fromWindow:nil];
        CGRect overlap = CGRectIntersection(bounds, keyboardFrame);
        imeInset = CGRectIsNull(overlap) ? 0.0 : CGRectGetHeight(overlap);
        keyboardIsVisible = imeInset > 0.0;
    }

    qreal scale = std::max<qreal>(1.0, window.screen.scale);
    qreal textScale = std::clamp<qreal>(
        [UIFont preferredFontForTextStyle:UIFontTextStyleBody].pointSize / 17.0,
        1.0, 1.5);
    bool didChange = changed(_safeInsetLeft, insets.left) ||
        changed(_safeInsetTop, insets.top) || changed(_safeInsetRight, insets.right) ||
        changed(_safeInsetBottom, insets.bottom) || changed(_imeInsetBottom, imeInset) ||
        _keyboardVisible != keyboardIsVisible || changed(_surfaceWidth, bounds.size.width) ||
        changed(_surfaceHeight, bounds.size.height) || changed(_density, scale) ||
        changed(_fontScale, textScale);

    _safeInsetLeft = insets.left;
    _safeInsetTop = insets.top;
    _safeInsetRight = insets.right;
    _safeInsetBottom = insets.bottom;
    _imeInsetBottom = imeInset;
    _keyboardVisible = keyboardIsVisible;
    _surfaceWidth = bounds.size.width;
    _surfaceHeight = bounds.size.height;
    _density = scale;
    _fontScale = textScale;
    if (didChange) {
        emit metricsChanged();
    }
}

void registerIOSTouchUiMetricsQmlType() {
    qmlRegisterSingletonType<IOSTouchUiMetrics>(
        "OverteIOS", 1, 0, "IOSTouchUiMetrics",
        [](QQmlEngine*, QJSEngine*) -> QObject* {
            return new IOSTouchUiMetrics(QCoreApplication::instance());
        });
}

void dismissIOSKeyboard() {
    if (NSThread.isMainThread) {
        dismissActiveWindowEditing();
    } else {
        dispatch_async(dispatch_get_main_queue(), ^{
            dismissActiveWindowEditing();
        });
    }
}
