// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "NativeWebAdapter.h"
#include "../src/RedactingDiagnostics.h"
#include <QCoreApplication>
#include <QGuiApplication>
#include <QTimer>
#import <UIKit/UIKit.h>
#import <WebKit/WebKit.h>

namespace {
overte::ios::NativeWebAdapter& nativeAdapter();
NSString* nativeString(const QString& value) {
    const QByteArray utf8 = value.toUtf8();
    return [[NSString alloc] initWithBytes:utf8.constData() length:utf8.size()
                                  encoding:NSUTF8StringEncoding];
}
QString privateUrl(NSURL* url) {
    return url == nil ? QString() : QString::fromUtf8(url.absoluteString.UTF8String);
}
// Constant rules contain no URL, origin, permission or user data. The compiled
// rule cache is not a saved site grant. Install it before the first WK load.
NSString* const CONTENT_RULES = @"[{\"trigger\":{\"url-filter\":\".*\",\"load-type\":[\"third-party\"]},\"action\":{\"type\":\"block\"}},"
    "{\"trigger\":{\"url-filter\":\".*\",\"resource-type\":[\"script\",\"media\",\"raw\",\"popup\"]},\"action\":{\"type\":\"block\"}},"
    "{\"trigger\":{\"url-filter\":\".*\"},\"action\":{\"type\":\"css-display-none\",\"selector\":\"form,input,textarea,select,button,[contenteditable]\"}}]";

void boundedContentRules(void (^completion)(WKContentRuleList*, NSError*)) {
    static WKContentRuleList* cachedRules = nil;
    static bool compiling = false; // Confined to the UIKit main thread.
    if (cachedRules) { completion(cachedRules, nil); return; }
    if (compiling) { completion(nil, nil); return; } // Never queue request closures.
    compiling = true;
    @try {
    [WKContentRuleListStore.defaultStore compileContentRuleListForIdentifier:@"org.overte.contained-readonly-v1"
        encodedContentRuleList:CONTENT_RULES completionHandler:^(WKContentRuleList* rules, NSError* error) {
            dispatch_async(dispatch_get_main_queue(), ^{
                cachedRules = rules;
                compiling = false;
                completion(rules, error);
            });
        }];
    } @catch (NSException*) {
        compiling = false;
        completion(nil, nil);
    }
}

UIViewController* foregroundPresenter(UIWindow** selectedWindow) {
    if (!NSThread.isMainThread) { return nil; }
    *selectedWindow = nil;
    UIWindow* candidate = nil;
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class] ||
                scene.activationState != UISceneActivationStateForegroundActive) { continue; }
        for (UIWindow* window in ((UIWindowScene*)scene).windows) {
            if (!window.isKeyWindow || window.hidden) { continue; }
            // The Shared request carries no originating scene/window identity.
            // Never choose an arbitrary scene for a security confirmation.
            if (candidate) { return nil; }
            candidate = window;
        }
    }
    UIViewController* presenter = candidate.rootViewController;
    while (presenter.presentedViewController != nil) {
        presenter = presenter.presentedViewController;
    }
    if (!presenter || [presenter isKindOfClass:UIAlertController.class] ||
            presenter.isBeingDismissed || presenter.isBeingPresented ||
            presenter.viewIfLoaded.window != candidate) { return nil; }
    *selectedWindow = candidate;
    return presenter;
}
}

@interface OverteContainedWebContext : NSObject <WKNavigationDelegate, WKUIDelegate>
@property(nonatomic) uint64_t ticket;
@property(nonatomic) BOOL active;
@property(nonatomic) BOOL failed;
@property(nonatomic, copy) NSString* origin;
@property(nonatomic, strong) NSURL* initialURL;
@property(nonatomic, weak) UIWindow* window;
@property(nonatomic, weak) UIViewController* presenter;
@property(nonatomic, strong) UIViewController* presentation;
@property(nonatomic, strong) WKWebView* webView;
@property(nonatomic, strong) UILabel* statusLabel;
@property(nonatomic, strong) UIBarButtonItem* backButton;
@property(nonatomic, strong) UIBarButtonItem* forwardButton;
@property(nonatomic, strong) UIBarButtonItem* reloadButton;
@property(nonatomic, strong) NSMutableArray* observers;
@property(nonatomic, strong) NSTimer* deadline;
- (BOOL)isForeground;
- (BOOL)allows:(NSURL*)url;
- (void)close;
- (void)failClosed;
- (void)openBrowser;
- (BOOL)tearDown;
@end

@implementation OverteContainedWebContext
- (BOOL)isForeground {
    // A full-screen presentation detaches the underlying presenter's view.
    // Inspect our own attached presentation first, not the hidden root view.
    UIWindow* attachedWindow = self.presentation.viewIfLoaded.window ?: self.presenter.viewIfLoaded.window;
    return NSThread.isMainThread && self.active && self.window.isKeyWindow &&
        !self.window.hidden && attachedWindow == self.window &&
        self.window.windowScene.activationState == UISceneActivationStateForegroundActive;
}
- (BOOL)allows:(NSURL*)url {
    return !self.failed && [self isForeground] &&
        nativeAdapter().mayNavigate(self.ticket, privateUrl(url));
}
- (void)close { nativeAdapter().close(self.ticket); }
- (void)failClosed {
    if (!self.active) { return; }
    self.failed = YES;
    @try {
        [self.deadline invalidate]; self.deadline = nil;
        [self.webView stopLoading];
        self.webView.hidden = YES;
        self.statusLabel.text = @"This request is unavailable. Only plain text is supported; HTML, forms and sign-in are not permitted. Close to return to Overte.";
        self.backButton.enabled = self.forwardButton.enabled = self.reloadButton.enabled = NO;
    } @catch (NSException*) { /* Failure stays latched, no native success claim. */ }
    overte::ios::logSharedDiagnostic(overte::security::DiagnosticEvent::Redacted);
}
- (void)startDeadline {
    if (self.deadline) { return; }
    __weak OverteContainedWebContext* weakSelf = self;
    self.deadline = [NSTimer scheduledTimerWithTimeInterval:30.0 repeats:NO block:^(NSTimer*) {
        OverteContainedWebContext* context = weakSelf;
        if (context.active) { [context failClosed]; }
    }];
}
- (void)updateControls {
    self.backButton.enabled = !self.failed && self.webView.canGoBack;
    self.forwardButton.enabled = !self.failed && self.webView.canGoForward;
    self.reloadButton.enabled = !self.failed && self.webView.URL != nil;
}
- (void)back {
    if ([self allows:self.webView.backForwardList.backItem.URL]) {
        [self startDeadline]; [self.webView goBack];
    }
}
- (void)forward {
    if ([self allows:self.webView.backForwardList.forwardItem.URL]) {
        [self startDeadline]; [self.webView goForward];
    }
}
- (void)reload {
    if ([self allows:self.webView.URL]) { [self startDeadline]; [self.webView reload]; }
}
- (void)openBrowser {
    if (![self allows:self.initialURL] || self.presenter.presentedViewController != nil) {
        [self close]; return;
    }
    @try {
        UIViewController* content = [UIViewController new];
        content.view.backgroundColor = UIColor.systemBackgroundColor;
        content.navigationItem.title = self.origin;
        content.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc]
            initWithTitle:@"Close" style:UIBarButtonItemStyleDone target:self action:@selector(close)];
        self.statusLabel = [UILabel new];
        self.statusLabel.numberOfLines = 0;
        self.statusLabel.text = @"Preparing a protected plain-text view. HTML, forms, sign-in and JavaScript are unavailable.";
        self.statusLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
        self.statusLabel.adjustsFontForContentSizeCategory = YES;
        self.statusLabel.translatesAutoresizingMaskIntoConstraints = NO;
        [content.view addSubview:self.statusLabel];
        [NSLayoutConstraint activateConstraints:@[
            [self.statusLabel.topAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.topAnchor constant:8],
            [self.statusLabel.leadingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.leadingAnchor constant:12],
            [self.statusLabel.trailingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.trailingAnchor constant:-12]
        ]];
        self.backButton = [[UIBarButtonItem alloc] initWithTitle:@"Back" style:UIBarButtonItemStylePlain
                                                       target:self action:@selector(back)];
        self.forwardButton = [[UIBarButtonItem alloc] initWithTitle:@"Forward" style:UIBarButtonItemStylePlain
                                                          target:self action:@selector(forward)];
        self.reloadButton = [[UIBarButtonItem alloc] initWithTitle:@"Reload" style:UIBarButtonItemStylePlain
                                                         target:self action:@selector(reload)];
        content.toolbarItems = @[self.backButton, self.forwardButton, self.reloadButton];
        [self updateControls];
        UINavigationController* navigation = [[UINavigationController alloc] initWithRootViewController:content];
        navigation.toolbarHidden = NO;
        navigation.modalPresentationStyle = UIModalPresentationFullScreen;
        navigation.modalInPresentation = YES;
        self.presentation = navigation;
        [self.presenter presentViewController:navigation animated:NO completion:nil];
        [self startDeadline];
        __weak OverteContainedWebContext* weakSelf = self;
        boundedContentRules(^(WKContentRuleList* rules, NSError* error) {
                // Compilation can finish after cancel/replacement/background. No
                // private request enters WKWebView before this final ticket check.
                dispatch_async(dispatch_get_main_queue(), ^{
                    OverteContainedWebContext* context = weakSelf;
                    if (!context || ![context allows:context.initialURL]) { return; }
                    if (!rules || error) { [context failClosed]; return; }
                    @try {
                        WKWebViewConfiguration* configuration = [WKWebViewConfiguration new];
                        configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
                        configuration.defaultWebpagePreferences.allowsContentJavaScript = NO;
                        configuration.preferences.javaScriptCanOpenWindowsAutomatically = NO;
                        configuration.dataDetectorTypes = WKDataDetectorTypeNone;
                        configuration.allowsAirPlayForMediaPlayback = NO;
                        configuration.mediaTypesRequiringUserActionForPlayback = WKAudiovisualMediaTypeAll;
                        [configuration.userContentController addContentRuleList:rules];
                        WKWebView* view = [[WKWebView alloc] initWithFrame:CGRectZero configuration:configuration];
                        context.webView = view;
                        view.navigationDelegate = context;
                        view.UIDelegate = context;
                        view.allowsLinkPreview = NO;
                        view.translatesAutoresizingMaskIntoConstraints = NO;
                        [content.view addSubview:view];
                        [NSLayoutConstraint activateConstraints:@[
                            [view.topAnchor constraintEqualToAnchor:context.statusLabel.bottomAnchor constant:8],
                            [view.leadingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.leadingAnchor],
                            [view.trailingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.trailingAnchor],
                            [view.bottomAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.bottomAnchor]
                        ]];
                        if (![context allows:context.initialURL]) { [context close]; return; }
                        [view loadRequest:[NSURLRequest requestWithURL:context.initialURL
                            cachePolicy:NSURLRequestUseProtocolCachePolicy timeoutInterval:30.0]];
                    } @catch (NSException*) { [context failClosed]; }
                });
            });
    } @catch (NSException*) { [self failClosed]; }
}
- (BOOL)tearDown {
    self.active = NO;
    BOOL success = YES;
    // Invalidation is independent of native stop/dismiss success. Always attempt
    // every cleanup step, and propagate failure to the process-lived adapter.
    @try { [self.deadline invalidate]; self.deadline = nil; }
    @catch (NSException*) { success = NO; }
    for (id token in self.observers) {
        @try { [NSNotificationCenter.defaultCenter removeObserver:token]; }
        @catch (NSException*) { success = NO; }
    }
    self.observers = nil;
    @try { [self.webView stopLoading]; }
    @catch (NSException*) { success = NO; }
    @try {
        self.webView.navigationDelegate = nil;
        self.webView.UIDelegate = nil;
        [self.webView.configuration.userContentController removeAllUserScripts];
        [self.webView removeFromSuperview];
    } @catch (NSException*) { success = NO; }
    @try {
        // Dismiss only our own controller; never the presenter's replacement.
        if (self.presentation.presentingViewController) {
            [self.presentation dismissViewControllerAnimated:NO completion:nil];
        }
    } @catch (NSException*) { success = NO; }
    self.webView = nil; self.presentation = nil; self.initialURL = nil; self.origin = nil;
    if (!success) { overte::ios::logSharedDiagnostic(overte::security::DiagnosticEvent::Redacted); }
    return success;
}
- (void)webView:(WKWebView*)view decidePolicyForNavigationAction:(WKNavigationAction*)action
        preferences:(WKWebpagePreferences*)preferences
        decisionHandler:(void (^)(WKNavigationActionPolicy, WKWebpagePreferences*))decisionHandler {
    preferences.allowsContentJavaScript = NO;
    const BOOL safeMethod = [action.request.HTTPMethod isEqualToString:@"GET"] ||
        [action.request.HTTPMethod isEqualToString:@"HEAD"];
    const BOOL allowed = view == self.webView && action.targetFrame.mainFrame &&
        !action.shouldPerformDownload && safeMethod && [self allows:action.request.URL];
    if (allowed && action.targetFrame.mainFrame) { [self startDeadline]; }
    decisionHandler(allowed ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel, preferences);
    if (!allowed && self.active) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view decidePolicyForNavigationResponse:(WKNavigationResponse*)response
        decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler {
    BOOL attachment = NO;
    if ([response.response isKindOfClass:NSHTTPURLResponse.class]) {
        NSDictionary* headers = ((NSHTTPURLResponse*)response.response).allHeaderFields;
        for (id key in headers) {
            if ([key isKindOfClass:NSString.class] && [key caseInsensitiveCompare:@"Content-Disposition"] == NSOrderedSame) {
                id value = headers[key];
                attachment = ![value isKindOfClass:NSString.class] ||
                    [value rangeOfString:@"attachment" options:NSCaseInsensitiveSearch].location != NSNotFound;
            }
        }
    }
    const BOOL allowed = view == self.webView && response.canShowMIMEType && !attachment &&
        overte::ios::acceptsNativeWebMime(QString::fromUtf8(response.response.MIMEType.UTF8String)) &&
        [self allows:response.response.URL];
    decisionHandler(allowed ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
    if (!allowed && self.active) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view didReceiveServerRedirectForProvisionalNavigation:(WKNavigation*)navigation {
    (void)navigation;
    if (view != self.webView || ![self allows:view.URL]) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view didCommitNavigation:(WKNavigation*)navigation {
    (void)navigation;
    if (view != self.webView || ![self allows:view.URL]) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view didFinishNavigation:(WKNavigation*)navigation {
    (void)navigation;
    if (view != self.webView || ![self allows:view.URL]) { [self failClosed]; return; }
    [self.deadline invalidate]; self.deadline = nil;
    self.statusLabel.text = @"Plain-text view. HTML, forms, sign-in, external content and JavaScript are unavailable.";
    [self updateControls];
}
- (void)webView:(WKWebView*)view didFailNavigation:(WKNavigation*)navigation withError:(NSError*)error {
    (void)view; (void)navigation; (void)error; if (self.active) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view didFailProvisionalNavigation:(WKNavigation*)navigation withError:(NSError*)error {
    (void)view; (void)navigation; (void)error; if (self.active) { [self failClosed]; }
}
- (void)webViewWebContentProcessDidTerminate:(WKWebView*)view {
    (void)view; if (self.active) { [self failClosed]; }
}
- (void)webView:(WKWebView*)view didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge*)challenge
        completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential*))completionHandler {
    (void)view;
    // System TLS verification only; never accept a supplied certificate, HTTP
    // authentication, client certificate or saved credential from this delegate.
    NSURLComponents* origin = [NSURLComponents new];
    origin.scheme = challenge.protectionSpace.protocol;
    origin.host = challenge.protectionSpace.host;
    origin.port = @(challenge.protectionSpace.port);
    if ([self allows:origin.URL] &&
            [challenge.protectionSpace.authenticationMethod isEqualToString:NSURLAuthenticationMethodServerTrust]) {
        completionHandler(NSURLSessionAuthChallengePerformDefaultHandling, nil);
    } else {
        completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
        if (self.active) { [self failClosed]; }
    }
}
- (WKWebView*)webView:(WKWebView*)view createWebViewWithConfiguration:(WKWebViewConfiguration*)configuration
        forNavigationAction:(WKNavigationAction*)action windowFeatures:(WKWindowFeatures*)features {
    (void)view; (void)configuration; (void)action; (void)features;
    [self failClosed]; return nil;
}
- (void)webView:(WKWebView*)view navigationAction:(WKNavigationAction*)action didBecomeDownload:(WKDownload*)download {
    (void)view; (void)action; [download cancel:^(NSData*) {}]; [self failClosed];
}
- (void)webView:(WKWebView*)view navigationResponse:(WKNavigationResponse*)response didBecomeDownload:(WKDownload*)download {
    (void)view; (void)response; [download cancel:^(NSData*) {}]; [self failClosed];
}
- (void)webView:(WKWebView*)view requestMediaCapturePermissionForOrigin:(WKSecurityOrigin*)origin
        initiatedByFrame:(WKFrameInfo*)frame type:(WKMediaCaptureType)type
        decisionHandler:(void (^)(WKPermissionDecision))decisionHandler {
    (void)view; (void)origin; (void)frame; (void)type; decisionHandler(WKPermissionDecisionDeny);
}
- (void)webView:(WKWebView*)view requestDeviceOrientationAndMotionPermissionForOrigin:(WKSecurityOrigin*)origin
        initiatedByFrame:(WKFrameInfo*)frame decisionHandler:(void (^)(WKPermissionDecision))decisionHandler {
    (void)view; (void)origin; (void)frame; decisionHandler(WKPermissionDecisionDeny);
}
#if __IPHONE_OS_VERSION_MAX_ALLOWED >= 180400
- (void)webView:(WKWebView*)view runOpenPanelWithParameters:(WKOpenPanelParameters*)parameters
        initiatedByFrame:(WKFrameInfo*)frame completionHandler:(void (^)(NSArray<NSURL*>*))completionHandler {
    (void)view; (void)parameters; (void)frame; completionHandler(nil);
}
#endif
- (void)webView:(WKWebView*)view contextMenuConfigurationForElement:(WKContextMenuElementInfo*)element
        completionHandler:(void (^)(UIContextMenuConfiguration*))completionHandler {
    (void)view; (void)element; completionHandler(nil);
}
@end

namespace {
class UIKitWebOperations final : public overte::ios::NativeWebOperations {
public:
    bool confirmation(const overte::web::Request& request) noexcept override {
        // Earlier WebKit cannot publicly delegate/deny the file upload panel.
        // Keep the application supported there, but this optional view unavailable.
#if __IPHONE_OS_VERSION_MAX_ALLOWED >= 180400
        if (@available(iOS 18.4, *)) {
            if (!NSThread.isMainThread || _context != nil) { return false; }
            @try {
                UIWindow* window = nil;
                UIViewController* presenter = foregroundPresenter(&window);
                if (!presenter) { return false; }
                OverteContainedWebContext* context = [OverteContainedWebContext new];
                _context = context;
                context.ticket = request.ticket; context.active = YES;
                context.window = window; context.presenter = presenter;
                context.origin = nativeString(request.origin);
                context.initialURL = [NSURL URLWithString:nativeString(request.url.toString(QUrl::FullyEncoded))];
                if (!context.initialURL || !context.origin) { return false; }
                context.observers = [NSMutableArray array];
                __weak OverteContainedWebContext* weakContext = context;
                for (NSNotificationName name in @[UIApplicationWillResignActiveNotification,
                        UISceneWillDeactivateNotification, UIWindowDidResignKeyNotification]) {
                    id token = [NSNotificationCenter.defaultCenter addObserverForName:name object:nil
                        queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification* note) {
                            OverteContainedWebContext* live = weakContext;
                            if (live && ([note.name isEqualToString:UIApplicationWillResignActiveNotification] ||
                                    note.object == live.window.windowScene || note.object == live.window)) { [live close]; }
                        }];
                    [context.observers addObject:token];
                }
                UIAlertController* alert = [UIAlertController alertControllerWithTitle:@"Open protected web view?"
                    message:[context.origin stringByAppendingString:@"\nPlain text only. HTML, forms, sign-in and JavaScript are unavailable."]
                    preferredStyle:UIAlertControllerStyleAlert];
                [alert addAction:[UIAlertAction actionWithTitle:@"Cancel" style:UIAlertActionStyleCancel
                    handler:^(UIAlertAction*) { [weakContext close]; }]];
                [alert addAction:[UIAlertAction actionWithTitle:@"Open" style:UIAlertActionStyleDefault
                    handler:^(UIAlertAction*) {
                        OverteContainedWebContext* live = weakContext;
                        if (!live || ![live isForeground] || !nativeAdapter().confirm(live.ticket)) { [live close]; return; }
                        UIViewController* confirmation = live.presentation;
                        [confirmation dismissViewControllerAnimated:NO completion:^{
                            OverteContainedWebContext* current = weakContext;
                            if (current && [current allows:current.initialURL]) { [current openBrowser]; }
                        }];
                    }]];
                context.presentation = alert;
                [presenter presentViewController:alert animated:NO completion:nil];
                return true; // Accepted UI presentation, not a load/present receipt.
            } @catch (NSException*) { return false; }
        }
#endif
        (void)request;
        return false;
    }
    bool dismiss(std::uint64_t ticket) noexcept override {
        if (!NSThread.isMainThread) { return false; }
        if (_context == nil) { return true; }
        if (_context.ticket != ticket) { return false; }
        OverteContainedWebContext* context = _context;
        _context = nil;
        @try { return [context tearDown]; }
        @catch (NSException*) {
            overte::ios::logSharedDiagnostic(overte::security::DiagnosticEvent::Redacted);
            return false;
        }
    }
private:
    __strong OverteContainedWebContext* _context { nil };
};
overte::ios::NativeWebAdapter& nativeAdapter() {
    static UIKitWebOperations operations;
    static overte::ios::NativeWebAdapter adapter(operations);
    return adapter;
}
void installContainedWeb() {
    QTimer::singleShot(0, QCoreApplication::instance(), [] {
        if (!qGuiApp || !NSThread.isMainThread ||
                !overte::web::installNativeWebAdapter(&nativeAdapter())) {
            overte::ios::logSharedDiagnostic(overte::security::DiagnosticEvent::Redacted);
        }
    });
}
Q_COREAPP_STARTUP_FUNCTION(installContainedWeb)
}
