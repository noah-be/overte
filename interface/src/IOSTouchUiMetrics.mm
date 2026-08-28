// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSTouchUiMetrics.h"

#import <UIKit/UIKit.h>

#include <algorithm>
#include <cmath>

#include <QCoreApplication>
#include <QJSEngine>
#include <QMetaObject>
#include <QPointer>
#include <QQmlEngine>
#include <QTimer>
#include <QtQml>

#include <shared/IOSRuntimeLogging.h>
#include <ui/TabletScriptingInterface.h>

@interface OverteIOSAccessibilityElement : UIAccessibilityElement
@property(nonatomic, copy) BOOL (^activationHandler)(void);
@end

@implementation OverteIOSAccessibilityElement
- (BOOL)accessibilityActivate {
    return self.activationHandler != nil && self.activationHandler();
}
@end

@interface OverteIOSAccessibilityOverlay : UIView
@end

@implementation OverteIOSAccessibilityOverlay
- (BOOL)pointInside:(CGPoint)point withEvent:(UIEvent*)event {
    (void)point;
    (void)event;
    return NO;
}
@end

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

UIResponder* findFirstResponder(UIView* view) {
    if (view.isFirstResponder) {
        return view;
    }
    for (UIView* child in view.subviews) {
        if (UIResponder* responder = findFirstResponder(child)) {
            return responder;
        }
    }
    return nil;
}

NSArray<UIWindow*>* applicationWindows() {
    NSMutableArray<UIWindow*>* windows = [NSMutableArray array];
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class] ||
            scene.activationState == UISceneActivationStateUnattached) {
            continue;
        }
        for (UIWindow* window in ((UIWindowScene*)scene).windows) {
            if (![windows containsObject:window]) {
                [windows addObject:window];
            }
        }
    }
    return windows;
}

int suppressInputAssistantForAllWindows() {
    int suppressed { 0 };
    for (UIWindow* window in applicationWindows()) {
        UIResponder* responder = findFirstResponder(window);
        if ([responder respondsToSelector:@selector(inputAssistantItem)]) {
            UITextInputAssistantItem* assistant = responder.inputAssistantItem;
            assistant.allowsHidingShortcuts = YES;
            assistant.leadingBarButtonGroups = @[];
            assistant.trailingBarButtonGroups = @[];
            ++suppressed;
        }
        if ([responder conformsToProtocol:@protocol(UITextInputTraits)]) {
            // With an attached Magic Keyboard, iPadOS can keep the QuickType
            // prediction strip visible even though no software-keyboard frame
            // exists. Disable prediction-producing traits on Qt's native text
            // responder while leaving the editor and hardware keys active.
            id<UITextInputTraits> traits = (id<UITextInputTraits>)responder;
            traits.autocorrectionType = UITextAutocorrectionTypeNo;
            traits.spellCheckingType = UITextSpellCheckingTypeNo;
            traits.smartQuotesType = UITextSmartQuotesTypeNo;
            traits.smartDashesType = UITextSmartDashesTypeNo;
            traits.smartInsertDeleteType = UITextSmartInsertDeleteTypeNo;
        }
    }
    return suppressed;
}

void dismissActiveWindowEditing() {
    suppressInputAssistantForAllWindows();
    for (UIWindow* window in applicationWindows()) {
        // QInputMethod::hide() can dismiss the keyboard while leaving its
        // input-assistant/QuickType bar attached to a hidden QML editor.
        // Ending editing on every application window clears Qt's auxiliary
        // responder too; it is not guaranteed to live in the key window.
        UIResponder* responder = findFirstResponder(window);
        [responder resignFirstResponder];
        [window endEditing:YES];
    }
}

UIView* tabletAccessibilityOverlay(UIWindow* window) {
    static __weak UIWindow* installedWindow = nil;
    static UIView* overlay = nil;
    if (installedWindow != window || overlay == nil) {
        [overlay removeFromSuperview];
        overlay = [[OverteIOSAccessibilityOverlay alloc] initWithFrame:window.bounds];
        overlay.backgroundColor = UIColor.clearColor;
        overlay.isAccessibilityElement = NO;
        overlay.accessibilityViewIsModal = NO;
        overlay.autoresizingMask = UIViewAutoresizingFlexibleWidth |
            UIViewAutoresizingFlexibleHeight;
        [window addSubview:overlay];
        installedWindow = window;
    }
    overlay.frame = window.bounds;
    [window bringSubviewToFront:overlay];
    return overlay;
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
        UIKeyboardWillShowNotification,
        UIKeyboardDidShowNotification,
        UIKeyboardWillChangeFrameNotification,
        UIKeyboardDidChangeFrameNotification,
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
    const bool keyboardNotificationReceived =
        [notification.name hasPrefix:@"UIKeyboard"];
    if (keyboardNotificationReceived) {
        suppressInputAssistantForAllWindows();
        // UIKit may rebuild the hardware-keyboard shortcut groups while the
        // frame/focus transition is completing. Reapply once on the following
        // main-queue turn without resigning the user's active text field.
        dispatch_async(dispatch_get_main_queue(), ^{
            suppressInputAssistantForAllWindows();
        });
    }
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

void updateIOSTabletAccessibilityControls(
        TabletProxy* tablet, const IOSTouchUiMetrics* metrics) {
    if (tablet == nullptr || metrics == nullptr || !NSThread.isMainThread) {
        return;
    }
    UIWindow* window = activeWindow();
    if (window == nil || metrics->surfaceWidth() <= 0.0 ||
            metrics->surfaceHeight() <= 0.0) {
        return;
    }

    UIView* overlay = tabletAccessibilityOverlay(window);
    const bool tabletShown = tablet->property("tabletShown").toBool();
    OverteIOSAccessibilityElement* element =
        [[OverteIOSAccessibilityElement alloc] initWithAccessibilityContainer:overlay];
    element.accessibilityTraits = UIAccessibilityTraitButton;
    QPointer<TabletProxy> guardedTablet(tablet);
    CGRect safeBounds = UIEdgeInsetsInsetRect(window.bounds, window.safeAreaInsets);
    if (tabletShown) {
        element.accessibilityIdentifier = @"OverteTabletClose";
        element.accessibilityLabel = @"Close tablet";
        element.accessibilityHint = @"Return to the world controls";
        const CGFloat width = std::min<CGFloat>(240.0, safeBounds.size.width * 0.30);
        element.accessibilityFrameInContainerSpace = CGRectMake(
            CGRectGetMidX(safeBounds) - width * 0.5,
            CGRectGetMaxY(safeBounds) - 72.0, width, 56.0);
        element.activationHandler = ^BOOL {
            if (!guardedTablet) {
                return NO;
            }
            QMetaObject::invokeMethod(guardedTablet.data(), [guardedTablet] {
                if (guardedTablet) {
                    guardedTablet->hideAndroidTablet();
                }
            }, Qt::QueuedConnection);
            return YES;
        };
    } else {
        element.accessibilityIdentifier = @"OverteTabletOpen";
        element.accessibilityLabel = @"Open tablet";
        element.accessibilityHint = @"Open the Overte tablet controls";
        element.accessibilityFrameInContainerSpace = CGRectMake(
            CGRectGetMinX(safeBounds) + 16.0,
            CGRectGetMinY(safeBounds) + 16.0, 128.0, 64.0);
        const int width = std::lround(metrics->surfaceWidth());
        const int height = std::lround(metrics->surfaceHeight());
        element.activationHandler = ^BOOL {
            if (!guardedTablet) {
                return NO;
            }
            QMetaObject::invokeMethod(guardedTablet.data(), [guardedTablet, width, height] {
                if (guardedTablet) {
                    guardedTablet->showAndroidTablet(width, height);
                }
            }, Qt::QueuedConnection);
            return YES;
        };
    }
    overlay.accessibilityElements = @[element];
    UIAccessibilityPostNotification(UIAccessibilityLayoutChangedNotification, element);
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

void suppressIOSKeyboardAssistant() {
    auto suppress = [] {
        const int responders = suppressInputAssistantForAllWindows();
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_UI_GATE stage=keyboard-assistant-suppressed",
            "responders=", responders);
    };
    if (NSThread.isMainThread) {
        suppress();
    } else {
        dispatch_async(dispatch_get_main_queue(), ^{
            suppress();
        });
    }
}
