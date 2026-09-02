// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

#include "IOSTouchUiMetrics.h"

#import <UIKit/UIKit.h>

#include <algorithm>
#include <cmath>

#include <QCoreApplication>
#include <QAccessible>
#include <QJSEngine>
#include <QMetaObject>
#include <QPointer>
#include <QQuickItem>
#include <QQmlEngine>
#include <QSet>
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

#if defined(OVERTE_IOS_E2E_TEST_BUILD)
@interface OverteIOSE2EAccessibilityButton : UIButton
@property(nonatomic, copy) BOOL (^activationHandler)(void);
@end

@implementation OverteIOSE2EAccessibilityButton
- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self != nil) {
        self.backgroundColor = UIColor.clearColor;
        self.opaque = NO;
        self.isAccessibilityElement = YES;
        self.accessibilityTraits = UIAccessibilityTraitButton;
        self.exclusiveTouch = YES;
        [self addTarget:self action:@selector(overteActivate:)
             forControlEvents:UIControlEventTouchUpInside];
    }
    return self;
}

- (void)overteActivate:(id)sender {
    (void)sender;
    if (self.activationHandler != nil) {
        self.activationHandler();
    }
}

- (BOOL)accessibilityActivate {
    return self.activationHandler != nil && self.activationHandler();
}
@end
#endif

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

#if defined(OVERTE_IOS_E2E_TEST_BUILD)
OverteIOSE2EAccessibilityButton* tabletE2EAccessibilityButton(UIWindow* window) {
    static __weak UIWindow* installedWindow = nil;
    static OverteIOSE2EAccessibilityButton* button = nil;
    if (installedWindow != window || button == nil) {
        [button removeFromSuperview];
        button = [[OverteIOSE2EAccessibilityButton alloc] initWithFrame:CGRectZero];
        [window addSubview:button];
        installedWindow = window;
    }
    [window bringSubviewToFront:button];
    return button;
}


NSMutableDictionary<NSString*, OverteIOSE2EAccessibilityButton*>*
tabletE2EAccessibilityButtons(UIWindow* window) {
    static __weak UIWindow* installedWindow = nil;
    static NSMutableDictionary<NSString*, OverteIOSE2EAccessibilityButton*>* buttons = nil;
    if (installedWindow != window || buttons == nil) {
        for (OverteIOSE2EAccessibilityButton* button in buttons.allValues) {
            [button removeFromSuperview];
        }
        buttons = [NSMutableDictionary dictionary];
        installedWindow = window;
    }
    return buttons;
}

OverteIOSE2EAccessibilityButton* tabletE2EAccessibilityButton(
        UIWindow* window, NSString* identifier) {
    NSMutableDictionary* buttons = tabletE2EAccessibilityButtons(window);
    OverteIOSE2EAccessibilityButton* button = buttons[identifier];
    if (button == nil) {
        button = [[OverteIOSE2EAccessibilityButton alloc] initWithFrame:CGRectZero];
        buttons[identifier] = button;
        [window addSubview:button];
    }
    [window bringSubviewToFront:button];
    return button;
}

void retainTabletE2EAccessibilityButtons(
        UIWindow* window, NSSet<NSString*>* activeIdentifiers) {
    NSMutableDictionary* buttons = tabletE2EAccessibilityButtons(window);
    for (NSString* identifier in buttons.allKeys.copy) {
        if (![activeIdentifiers containsObject:identifier]) {
            [buttons[identifier] removeFromSuperview];
            [buttons removeObjectForKey:identifier];
        }
    }
}

const QSet<QString>& tabletSemanticScreenIds() {
    static const QSet<QString> ids {
        QStringLiteral("settings.audio"),
        QStringLiteral("settings.controllers"),
        QStringLiteral("settings.general"),
        QStringLiteral("settings.graphics"),
        QStringLiteral("settings.home"),
        QStringLiteral("settings.security"),
        QStringLiteral("tablet.home"),
    };
    return ids;
}

const QSet<QString>& tabletSemanticControlIds() {
    static const QSet<QString> ids {
        QStringLiteral("app.settings"),
        QStringLiteral("nav.back"),
        QStringLiteral("nav.close"),
        QStringLiteral("nav.home"),
        QStringLiteral("settings.audio"),
        QStringLiteral("settings.controllers"),
        QStringLiteral("settings.general"),
        QStringLiteral("settings.graphics"),
        QStringLiteral("settings.hmd-preferences"),
        QStringLiteral("settings.security"),
        QStringLiteral("settings.vr-render-resolution"),
    };
    return ids;
}

bool visibleTabletItem(QQuickItem* item) {
    if (item == nullptr || !item->isVisible() || !item->isEnabled() ||
            item->opacity() <= 0.01 || item->width() <= 0.0 || item->height() <= 0.0) {
        return false;
    }
    const QRectF sceneRect = item->mapRectToScene(item->boundingRect());
    return sceneRect.isValid() && sceneRect.width() > 0.0 && sceneRect.height() > 0.0;
}

CGRect tabletItemFrame(QQuickItem* item, CGRect safeBounds) {
    const QRectF sceneRect = item->mapRectToScene(item->boundingRect());
    CGRect frame = CGRectMake(
        CGRectGetMinX(safeBounds) + sceneRect.x(),
        CGRectGetMinY(safeBounds) + sceneRect.y(),
        sceneRect.width(), sceneRect.height());
    return CGRectIntersection(frame, safeBounds);
}

QList<QQuickItem*> tabletVisualItems(QQuickItem* tabletRoot) {
    QList<QQuickItem*> items;
    if (tabletRoot == nullptr) {
        return items;
    }
    items.append(tabletRoot);
    for (int index = 0; index < items.size(); ++index) {
        for (QQuickItem* child : items.at(index)->childItems()) {
            if (child != nullptr && !items.contains(child)) {
                items.append(child);
            }
        }
    }
    return items;
}

QString observedTabletScreen(QQuickItem* tabletRoot) {
    if (tabletRoot == nullptr) {
        return {};
    }

    QString observedScreen;
    for (QQuickItem* item : tabletVisualItems(tabletRoot)) {
        if (!visibleTabletItem(item)) {
            continue;
        }
        const QVariant property = item->property("semanticScreenId");
        if (!property.isValid()) {
            continue;
        }
        const QString screen = property.toString();
        if (!tabletSemanticScreenIds().contains(screen)) {
            continue;
        }
        if (observedScreen.isEmpty()) {
            observedScreen = screen;
        } else if (observedScreen != screen) {
            // Dynamic QML replacement may briefly leave two pages in the
            // object tree. Never claim a semantic screen while two different
            // visible page contracts disagree.
            return {};
        }
    }
    return observedScreen;
}

BOOL activateTabletItem(QPointer<QQuickItem> guardedItem) {
    if (!guardedItem || !visibleTabletItem(guardedItem.data())) {
        return NO;
    }
    QMetaObject::invokeMethod(guardedItem.data(), [guardedItem] {
        if (!guardedItem || !visibleTabletItem(guardedItem.data())) {
            return;
        }
        // TabletButton and Settings rows expose their production activate()
        // function directly. Prefer it when present; otherwise use the same
        // Accessible press action that keyboard/assistive input invokes.
        if (guardedItem->metaObject()->indexOfMethod("activate()") >= 0 &&
                QMetaObject::invokeMethod(
                    guardedItem.data(), "activate", Qt::DirectConnection)) {
            return;
        }
        QAccessibleInterface* accessible = QAccessible::queryAccessibleInterface(
            guardedItem.data());
        QAccessibleActionInterface* action = accessible
            ? accessible->actionInterface() : nullptr;
        if (action && action->actionNames().contains(
                QAccessibleActionInterface::pressAction())) {
            action->doAction(QAccessibleActionInterface::pressAction());
        }
    }, Qt::QueuedConnection);
    return YES;
}
#endif
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
    QPointer<TabletProxy> guardedTablet(tablet);
    CGRect safeBounds = UIEdgeInsetsInsetRect(window.bounds, window.safeAreaInsets);
    NSString* identifier = nil;
    NSString* label = nil;
    NSString* hint = nil;
    CGRect controlFrame = CGRectZero;
    BOOL (^activationHandler)(void) = nil;
    if (tabletShown) {
        identifier = @"OverteTabletClose";
        label = @"Close tablet";
        hint = @"Return to the world controls";
        const CGFloat width = std::min<CGFloat>(240.0, safeBounds.size.width * 0.30);
        controlFrame = CGRectMake(
            CGRectGetMidX(safeBounds) - width * 0.5,
            CGRectGetMaxY(safeBounds) - 72.0, width, 56.0);
        activationHandler = ^BOOL {
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
        identifier = @"OverteTabletOpen";
        label = @"Open tablet";
        hint = @"Open the Overte tablet controls";
        controlFrame = CGRectMake(
            CGRectGetMinX(safeBounds) + 16.0,
            CGRectGetMinY(safeBounds) + 16.0, 128.0, 64.0);
        const int width = std::lround(metrics->surfaceWidth());
        const int height = std::lround(metrics->surfaceHeight());
        activationHandler = ^BOOL {
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

#if defined(OVERTE_IOS_E2E_TEST_BUILD)
    // XCUITest's element click synthesizes a physical tap; it does not call a
    // synthetic UIAccessibilityElement's accessibilityActivate method. Keep
    // the production overlay passive, but give E2E builds one real invisible
    // native control whose hit target exactly matches the exposed identifier.
    overlay.accessibilityElements = @[];
    OverteIOSE2EAccessibilityButton* button = tabletE2EAccessibilityButton(window);
    button.frame = controlFrame;
    button.accessibilityIdentifier = identifier;
    button.accessibilityLabel = label;
    button.accessibilityHint = hint;
    button.activationHandler = activationHandler;
    UIAccessibilityPostNotification(UIAccessibilityLayoutChangedNotification, button);

    QQuickItem* tabletRoot = tablet->getIOSTabletRoot();
    QQuickItem* loader = tabletRoot
        ? tabletRoot->findChild<QQuickItem*>(QStringLiteral("loader")) : nullptr;
    // QmlSurface.load() exposes its item as a JavaScript-valued QML property,
    // which cannot be unwrapped reliably through QObject::property on the
    // physical iOS build. Walk the stable root's visual QQuickItem tree and
    // consume only explicit, allow-listed semanticScreenId properties. Equal
    // duplicate projections are harmless; conflicting visible pages fail
    // closed in observedTabletScreen().
    QQuickItem* loadedItem = tabletRoot;
    const QString screenId = observedTabletScreen(loadedItem);
    NSMutableSet<NSString*>* activeIdentifiers = [NSMutableSet setWithObject:identifier];

    if (tabletShown && loadedItem != nullptr && !screenId.isEmpty()) {
        NSString* screenIdentifier = [NSString stringWithFormat:
            @"OverteTabletScreen.%s", screenId.toUtf8().constData()];
        OverteIOSE2EAccessibilityButton* screenMarker =
            tabletE2EAccessibilityButton(window, screenIdentifier);
        screenMarker.frame = CGRectMake(
            CGRectGetMinX(safeBounds), CGRectGetMinY(safeBounds), 1.0, 1.0);
        screenMarker.accessibilityIdentifier = screenIdentifier;
        screenMarker.accessibilityLabel = @"Tablet semantic screen";
        screenMarker.accessibilityHint = nil;
        screenMarker.accessibilityTraits = UIAccessibilityTraitStaticText;
        screenMarker.activationHandler = nil;
        screenMarker.enabled = NO;
        [activeIdentifiers addObject:screenIdentifier];

        const bool ready = visibleTabletItem(loadedItem) && loader != nullptr &&
            !loader->property("source").toString().isEmpty();
        if (ready) {
            NSString* readyIdentifier = [NSString stringWithFormat:
                @"OverteTabletReady.%s", screenId.toUtf8().constData()];
            OverteIOSE2EAccessibilityButton* readyMarker =
                tabletE2EAccessibilityButton(window, readyIdentifier);
            readyMarker.frame = CGRectMake(
                CGRectGetMinX(safeBounds) + 1.0, CGRectGetMinY(safeBounds), 1.0, 1.0);
            readyMarker.accessibilityIdentifier = readyIdentifier;
            readyMarker.accessibilityLabel = @"Tablet semantic screen ready";
            readyMarker.accessibilityHint = nil;
            readyMarker.accessibilityTraits = UIAccessibilityTraitStaticText;
            readyMarker.activationHandler = nil;
            readyMarker.enabled = NO;
            [activeIdentifiers addObject:readyIdentifier];
        }

        QSet<QString> exposedControls;
        for (QQuickItem* item : tabletVisualItems(tabletRoot)) {
            QString controlId = item->property("semanticId").toString();
            if (controlId.isEmpty()) {
                controlId = item->objectName();
            }
            if (controlId == QStringLiteral("OverteTabletClose") &&
                    screenId == QStringLiteral("tablet.home")) {
                controlId = QStringLiteral("nav.close");
            }
            // Several contract IDs intentionally name both an entry control
            // and the screen reached through it. The loaded page root is
            // screen evidence, not another visible entry control.
            if (controlId == screenId) {
                continue;
            }
            if (!tabletSemanticControlIds().contains(controlId) ||
                    exposedControls.contains(controlId) || !visibleTabletItem(item)) {
                continue;
            }
            const CGRect itemFrame = tabletItemFrame(item, safeBounds);
            if (CGRectIsNull(itemFrame) || CGRectIsEmpty(itemFrame)) {
                continue;
            }
            NSString* controlIdentifier = [NSString stringWithFormat:
                @"OverteTabletControl.%s", controlId.toUtf8().constData()];
            OverteIOSE2EAccessibilityButton* control =
                tabletE2EAccessibilityButton(window, controlIdentifier);
            control.frame = itemFrame;
            control.accessibilityIdentifier = controlIdentifier;
            control.accessibilityLabel = @"Tablet semantic control";
            control.accessibilityHint = nil;
            control.accessibilityTraits = UIAccessibilityTraitButton;
            QPointer<QQuickItem> guardedItem(item);
            QAccessibleInterface* accessible = QAccessible::queryAccessibleInterface(item);
            QAccessibleActionInterface* action = accessible
                ? accessible->actionInterface() : nullptr;
            const bool actionable = item->metaObject()->indexOfMethod("activate()") >= 0 ||
                (action && action->actionNames().contains(
                    QAccessibleActionInterface::pressAction()));
            control.enabled = actionable;
            if (actionable) {
                control.activationHandler = ^BOOL {
                    return activateTabletItem(guardedItem);
                };
            } else {
                control.activationHandler = nil;
            }
            exposedControls.insert(controlId);
            [activeIdentifiers addObject:controlIdentifier];
        }
    }
    retainTabletE2EAccessibilityButtons(window, activeIdentifiers);
#else
    OverteIOSAccessibilityElement* element =
        [[OverteIOSAccessibilityElement alloc] initWithAccessibilityContainer:overlay];
    element.accessibilityTraits = UIAccessibilityTraitButton;
    element.accessibilityIdentifier = identifier;
    element.accessibilityLabel = label;
    element.accessibilityHint = hint;
    element.accessibilityFrameInContainerSpace = controlFrame;
    element.activationHandler = activationHandler;
    overlay.accessibilityElements = @[element];
    UIAccessibilityPostNotification(UIAccessibilityLayoutChangedNotification, element);
#endif
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
