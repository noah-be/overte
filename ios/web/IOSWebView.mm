// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSWebView.h"
#include "IOSWebChannel.h"
#include "IOSWebDocumentEpoch.h"
#include "WKWebSnapshot.h"
#include <EmbeddedWebPolicy.h>
#include <QCoreApplication>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QInputMethod>
#include <QInputMethodEvent>
#include <QJsonArray>
#include <QJsonDocument>
#include <QKeyEvent>
#include <QMouseEvent>
#include <QMimeDatabase>
#include <QNetworkAccessManager>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QPainter>
#include <QPointer>
#include <QQmlContext>
#include <QQmlEngine>
#include <QTimer>
#include <QUuid>
#include <QWheelEvent>
#include <atomic>
#include <PathUtils.h>
#import <UIKit/UIKit.h>
#import <WebKit/WebKit.h>

namespace overte::ios {
struct IOSWebViewNative {
    static bool current(IOSWebView*, std::uint64_t);
    static bool navigation(IOSWebView*, std::uint64_t, NSURL*, bool, NSString*);
    static void message(IOSWebView*, std::uint64_t, NSString*, NSString*, NSURL*, bool);
    static void prepare(IOSWebView*, std::uint64_t, NSURL*);
    static void redirected(IOSWebView*, std::uint64_t, NSURL*);
    static void finished(IOSWebView*, std::uint64_t);
    static void started(IOSWebView*, std::uint64_t);
    static void failed(IOSWebView*, std::uint64_t);
    static void close(IOSWebView*);
};
}

namespace {
QString qtString(NSString* text) { return text ? QString::fromUtf8(text.UTF8String) : QString(); }
NSString* nativeString(const QString& text) {
    const auto bytes = text.toUtf8();
    return [[NSString alloc] initWithBytes:bytes.constData() length:bytes.size() encoding:NSUTF8StringEncoding];
}
QUrl qtURL(NSURL* url) {
    QUrl result(qtString(url.absoluteString));
    if (result.scheme() == QStringLiteral("overte-qrc")) { result.setScheme(QStringLiteral("qrc")); }
    return result;
}
NSURL* nativeURL(QUrl url) {
    if (url.scheme() == QStringLiteral("qrc")) { url.setScheme(QStringLiteral("overte-qrc")); }
    return [NSURL URLWithString:nativeString(url.toString(QUrl::FullyEncoded))];
}
QString packagedRoot(const QUrl& url) {
    using Policy = overte::web::EmbeddedWebSession;
    // All roots come from native resource owners. A page never supplies a root.
    const QStringList roots { QStringLiteral("qrc:/html"), QStringLiteral("qrc:/scripts"),
        PathUtils::defaultScriptsLocation().toLocalFile(),
        PathUtils::resourcesPath().startsWith(QLatin1Char(':')) ? QString() : PathUtils::resourcesPath(),
        QCoreApplication::applicationDirPath() + QStringLiteral("/overte-resources") };
    for (const auto& root : roots) { if (Policy::isPackagedURL(url, root)) { return root; } }
    return {};
}
UIViewController* presenter(UIWindow** result) {
    *result = nil;
    if (!NSThread.isMainThread) { return nil; }
    for (UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if (![scene isKindOfClass:UIWindowScene.class] ||
                scene.activationState != UISceneActivationStateForegroundActive) { continue; }
        for (UIWindow* window in ((UIWindowScene*)scene).windows) {
            if (!window.isKeyWindow || window.hidden) { continue; }
            if (*result) { return nil; } // No arbitrary choice across active scenes.
            *result = window;
        }
    }
    UIViewController* controller = (*result).rootViewController;
    while (controller.presentedViewController) { controller = controller.presentedViewController; }
    if (!controller || controller.isBeingDismissed || controller.isBeingPresented ||
            [controller isKindOfClass:UIAlertController.class]) { return nil; }
    return controller;
}
QString encodedArguments(const QJsonArray& arguments) {
    return QString::fromUtf8(QJsonDocument(arguments).toJson(QJsonDocument::Compact));
}
QString guardedScript(const QString& code, const QString& nonce) {
    return QStringLiteral("(function(identity){var t=window.qt&&window.qt.webChannelTransport;if(!t||t.document!==identity[0])return;\n%1\n})(%2);")
        .arg(code, encodedArguments(QJsonArray { nonce }));
}
QVariant qtValue(id value) {
    if (!value || value == NSNull.null) { return {}; }
    if ([value isKindOfClass:NSString.class]) { return qtString(value); }
    if ([value isKindOfClass:NSNumber.class]) {
        return CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID() ? QVariant([value boolValue] == YES) : QVariant([value doubleValue]);
    }
    if ([NSJSONSerialization isValidJSONObject:value]) {
        NSData* encoded = [NSJSONSerialization dataWithJSONObject:value options:0 error:nil];
        return QJsonDocument::fromJson(QByteArray(static_cast<const char*>(encoded.bytes), static_cast<int>(encoded.length))).toVariant();
    }
    return {};
}
}

@interface OverteIOSWebDelegate : NSObject <WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler> {
@public
    QPointer<overte::ios::IOSWebView> owner;
    std::uint64_t generation;
}
- (void)close;
- (void)back;
- (void)forward;
- (void)reload;
@end

@interface OverteIOSQrcHandler : NSObject <WKURLSchemeHandler> {
@public
    QPointer<overte::ios::IOSWebView> owner;
    std::uint64_t generation;
}
@end

@implementation OverteIOSQrcHandler
- (void)webView:(WKWebView*)view startURLSchemeTask:(id<WKURLSchemeTask>)task {
    (void)view;
    const QUrl url = qtURL(task.request.URL);
    if (!owner || !overte::ios::IOSWebViewNative::navigation(owner, generation, task.request.URL, false, @"GET")) {
        [task didFailWithError:[NSError errorWithDomain:@"org.overte.web" code:1 userInfo:nil]]; return;
    }
    QFile file(QStringLiteral(":") + url.path());
    if (!file.open(QFile::ReadOnly) || file.size() > 16 * 1024 * 1024) {
        [task didFailWithError:[NSError errorWithDomain:@"org.overte.web" code:2 userInfo:nil]]; return;
    }
    const auto bytes = file.readAll();
    const auto mime = QMimeDatabase().mimeTypeForFile(url.path()).name();
    NSURLResponse* response = [[NSURLResponse alloc] initWithURL:task.request.URL MIMEType:nativeString(mime)
        expectedContentLength:bytes.size() textEncodingName:@"utf-8"];
    [task didReceiveResponse:response];
    [task didReceiveData:[NSData dataWithBytes:bytes.constData() length:bytes.size()]];
    [task didFinish];
}
- (void)webView:(WKWebView*)view stopURLSchemeTask:(id<WKURLSchemeTask>)task { (void)view; (void)task; }
@end

@implementation OverteIOSWebDelegate
- (void)close { if (owner) { overte::ios::IOSWebViewNative::close(owner); } }
- (void)back { if (owner) { owner->goBack(); } }
- (void)forward { if (owner) { owner->goForward(); } }
- (void)reload { if (owner) { owner->reload(); } }
- (void)webView:(WKWebView*)view decidePolicyForNavigationAction:(WKNavigationAction*)action
        decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    if (!action.targetFrame) {
        decisionHandler(WKNavigationActionPolicyCancel);
        if (owner && !action.shouldPerformDownload &&
                overte::ios::IOSWebViewNative::navigation(owner, generation, action.request.URL, true, action.request.HTTPMethod)) {
            overte::ios::IOSWebViewNative::prepare(owner, generation, action.request.URL);
            [view loadRequest:action.request];
        }
        return;
    }
    const bool allowed = owner && !action.shouldPerformDownload && action.targetFrame &&
        overte::ios::IOSWebViewNative::navigation(owner, generation, action.request.URL,
            action.targetFrame.mainFrame, action.request.HTTPMethod);
    const auto previous = qtURL(view.URL);
    const auto destination = qtURL(action.request.URL);
    const bool fragmentOnly = overte::ios::IOSWebDocumentEpoch::isFragmentNavigation(previous, destination);
    // Fragment links retain the same JavaScript document, including its nonce.
    if (allowed && action.targetFrame.mainFrame && !fragmentOnly) { overte::ios::IOSWebViewNative::prepare(owner, generation, action.request.URL); }
    decisionHandler(allowed ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel);
}
- (void)webView:(WKWebView*)view decidePolicyForNavigationResponse:(WKNavigationResponse*)response
        decisionHandler:(void (^)(WKNavigationResponsePolicy))decisionHandler {
    (void)view;
    const bool allowed = owner && response.canShowMIMEType &&
        overte::ios::IOSWebViewNative::navigation(owner, generation, response.response.URL,
            response.isForMainFrame, @"GET");
    if (allowed && response.isForMainFrame) { overte::ios::IOSWebViewNative::redirected(owner, generation, response.response.URL); }
    decisionHandler(allowed ? WKNavigationResponsePolicyAllow : WKNavigationResponsePolicyCancel);
}
- (void)webView:(WKWebView*)view didStartProvisionalNavigation:(WKNavigation*)navigation {
    (void)view; (void)navigation;
    if (owner) { overte::ios::IOSWebViewNative::started(owner, generation); }
}
- (void)webView:(WKWebView*)view didFinishNavigation:(WKNavigation*)navigation {
    (void)view; (void)navigation;
    if (owner) { overte::ios::IOSWebViewNative::finished(owner, generation); }
}
- (void)webView:(WKWebView*)view didFailNavigation:(WKNavigation*)navigation withError:(NSError*)error {
    (void)view; (void)navigation;
    if (error.code != NSURLErrorCancelled && owner) { overte::ios::IOSWebViewNative::failed(owner, generation); }
}
- (void)webView:(WKWebView*)view didFailProvisionalNavigation:(WKNavigation*)navigation withError:(NSError*)error {
    [self webView:view didFailNavigation:navigation withError:error];
}
- (void)webViewWebContentProcessDidTerminate:(WKWebView*)view {
    (void)view;
    if (owner) { overte::ios::IOSWebViewNative::failed(owner, generation); }
}
- (void)userContentController:(WKUserContentController*)controller didReceiveScriptMessage:(WKScriptMessage*)message {
    (void)controller;
    if (owner && [message.body isKindOfClass:NSDictionary.class] &&
            [message.body[@"envelope"] isKindOfClass:NSString.class] &&
            [message.body[@"document"] isKindOfClass:NSString.class]) {
        overte::ios::IOSWebViewNative::message(owner, generation, message.body[@"envelope"], message.body[@"document"],
            message.frameInfo.request.URL, message.frameInfo.mainFrame);
    }
}
- (void)webView:(WKWebView*)view didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge*)challenge
        completionHandler:(void (^)(NSURLSessionAuthChallengeDisposition, NSURLCredential*))completionHandler {
    (void)view;
    // Normal system TLS verification; no supplied trust, account credentials,
    // client certificates or HTTP-auth grant from the application.
    const bool current = owner && overte::ios::IOSWebViewNative::current(owner, generation);
    if (current && [challenge.protectionSpace.authenticationMethod isEqualToString:NSURLAuthenticationMethodServerTrust]) {
        completionHandler(NSURLSessionAuthChallengePerformDefaultHandling, nil);
    } else { completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil); }
}
- (WKWebView*)webView:(WKWebView*)view createWebViewWithConfiguration:(WKWebViewConfiguration*)configuration
        forNavigationAction:(WKNavigationAction*)action windowFeatures:(WKWindowFeatures*)features {
    (void)configuration; (void)features;
    // Ordinary target=_blank links stay in this isolated view, under policy.
    if (owner && overte::ios::IOSWebViewNative::navigation(owner, generation, action.request.URL, true, action.request.HTTPMethod)) {
        [view loadRequest:action.request];
    }
    return nil;
}
- (void)webView:(WKWebView*)view requestMediaCapturePermissionForOrigin:(WKSecurityOrigin*)origin
        initiatedByFrame:(WKFrameInfo*)frame type:(WKMediaCaptureType)type
        decisionHandler:(void (^)(WKPermissionDecision))decisionHandler {
    (void)view; (void)origin; (void)frame; (void)type;
    decisionHandler(WKPermissionDecisionDeny); // Overte voice permission is not a website capture grant.
}
- (void)webView:(WKWebView*)view requestDeviceOrientationAndMotionPermissionForOrigin:(WKSecurityOrigin*)origin
        initiatedByFrame:(WKFrameInfo*)frame decisionHandler:(void (^)(WKPermissionDecision))decisionHandler {
    (void)view; (void)origin; (void)frame; decisionHandler(WKPermissionDecisionDeny);
}
- (void)webView:(WKWebView*)view navigationAction:(WKNavigationAction*)action didBecomeDownload:(WKDownload*)download {
    (void)view; (void)action; [download cancel:^(NSData*) {}];
}
- (void)webView:(WKWebView*)view navigationResponse:(WKNavigationResponse*)response didBecomeDownload:(WKDownload*)download {
    (void)view; (void)response; [download cancel:^(NSData*) {}];
}
// No custom file-panel delegate: WK's system-mediated chooser requires explicit
// user file selection. This HTML mode does not grant app filesystem access and
// keeps the existing iOS17 floor. The separate text-only adapter remains stricter.
@end

namespace overte::ios {
struct IOSWebView::Private {
    web::EmbeddedWebSession policy;
    web::EmbeddedWebSession::Generation generation { 0 };
    IOSWebDocumentEpoch document;
    IOSWebChannel channel;
    WKWebSnapshot snapshot;
    QTimer openTimer, deadline;
    QNetworkAccessManager network;
    QPointer<QNetworkReply> scriptReply;
    QUrl url, scriptUrl, bridgeFrame;
    QString userAgent, surface { QStringLiteral("tablet") }, identity, bootstrap, packagedRoot, documentRoot, scriptRoot, error;
    QImage image;
    QByteArray script;
    bool complete { false }, loading { false }, background { true }, back { false }, forward { false }, resumeOnForeground { false }, cleanupFailed { false }, inputActive { false }, bridgeReady { false };
    __strong WKWebView* view { nil };
    __strong OverteIOSWebDelegate* delegate { nil };
    __strong OverteIOSQrcHandler* qrcHandler { nil };
    __weak UIWindow* window { nil };
    __weak UIViewController* presenter { nil };
    __strong UINavigationController* presentation { nil };
    __strong NSMutableArray* observers { nil };
};

IOSWebView::IOSWebView(QQuickItem* parent) : QQuickPaintedItem(parent), _private(std::make_unique<Private>()) {
    static std::atomic<std::uint64_t> identity { 0 };
    _private->identity = QStringLiteral("ios-web-%1").arg(++identity);
    setAcceptedMouseButtons(Qt::AllButtons);
    setFlag(QQuickItem::ItemAcceptsInputMethod, true);
    _private->openTimer.setSingleShot(true);
    _private->deadline.setSingleShot(true);
    _private->deadline.setInterval(30000);
    connect(&_private->openTimer, &QTimer::timeout, this, &IOSWebView::open);
    connect(&_private->deadline, &QTimer::timeout, this, [this] { fail(tr("The web page did not respond. Reload to try again.")); });
    connect(this, &QQuickItem::visibleChanged, this, [this] { if (!isVisible()) { stop(); } else { scheduleOpen(); } });
    connect(this, &QQuickItem::enabledChanged, this, [this] { if (!isEnabled()) { stop(); } else { scheduleOpen(); } });
    connect(qGuiApp, &QGuiApplication::applicationStateChanged, this, [this](Qt::ApplicationState state) {
        if (state == Qt::ApplicationActive) {
            if (_private->resumeOnForeground) { _private->resumeOnForeground = false; scheduleOpen(); }
        } else if (_private->generation) {
            _private->resumeOnForeground = true;
            _private->policy.setForeground(false); tearDown();
        }
    });
    connect(&_private->snapshot, &WKWebSnapshot::imageReady, this, [this](const QImage& image) {
        if (!active()) { return; }
        _private->image = image;
        emit frameChanged(); update();
    });
    connect(&_private->snapshot, &WKWebSnapshot::failed, this, [this] {
        _private->image = QImage(); emit frameChanged();
        _private->error = tr("The web surface is unavailable. Open the native browser or reload.");
        emit errorChanged(); update();
    });
    connect(&_private->channel, &IOSWebChannel::webEventReceived, this, &IOSWebView::webEventReceived);
    connect(&_private->channel, &IOSWebChannel::bridgeInitialized, this, [this] { _private->bridgeReady = true; emit bridgeAvailableChanged(); });
    connect(&_private->channel, &IOSWebChannel::sendToPage, this, [this](const QString& envelope) {
        if (!_private->view || !_private->policy.allowsBridge(_private->generation, _private->bridgeFrame, true,
                static_cast<std::size_t>(envelope.toUtf8().size()))) { return; }
        const auto literal = encodedArguments(QJsonArray { envelope });
        evaluate(QStringLiteral("(function(v){var t=window.qt&&qt.webChannelTransport;if(t&&t.onmessage)t.onmessage({data:v[0]});})(%1);").arg(literal));
    });
}
IOSWebView::~IOSWebView() { tearDown(); }
QUrl IOSWebView::url() const { return _private->url; }
QUrl IOSWebView::currentUrl() const { return _private->view.URL ? qtURL(_private->view.URL) : _private->url; }
void IOSWebView::setUrl(const QUrl& value) {
    if (_private->url == value) { return; }
    _private->url = value; scheduleOpen(); emit urlChanged();
}
QUrl IOSWebView::scriptUrl() const { return _private->scriptUrl; }
void IOSWebView::setScriptUrl(const QUrl& value) { if (_private->scriptUrl != value) { _private->scriptUrl = value; scheduleOpen(); emit configurationChanged(); } }
QString IOSWebView::userAgent() const { return _private->userAgent; }
void IOSWebView::setUserAgent(const QString& value) { if (_private->userAgent != value) { _private->userAgent = value; scheduleOpen(); emit configurationChanged(); } }
bool IOSWebView::useBackground() const { return _private->background; }
void IOSWebView::setUseBackground(bool value) { _private->background = value; if (_private->view) { _private->view.opaque = value; _private->view.backgroundColor = value ? UIColor.whiteColor : UIColor.clearColor; } emit configurationChanged(); update(); }
QString IOSWebView::surface() const { return _private->surface; }
void IOSWebView::setSurface(const QString& value) { if (_private->surface != value) { _private->surface = value; scheduleOpen(); emit configurationChanged(); } }
QString IOSWebView::sourceIdentity() const { return _private->identity; }
void IOSWebView::setSourceIdentity(const QString& value) { if (_private->identity != value) { _private->identity = value; scheduleOpen(); emit configurationChanged(); } }
QString IOSWebView::eventBridgeJavaScript() const { return _private->bootstrap; }
void IOSWebView::setEventBridgeJavaScript(const QString& value) { if (_private->bootstrap != value) { _private->bootstrap = value; scheduleOpen(); emit configurationChanged(); } }
QString IOSWebView::packagedScriptRoot() const { return _private->packagedRoot; }
void IOSWebView::setPackagedScriptRoot(const QString& value) { if (_private->packagedRoot != value) { _private->packagedRoot = value; scheduleOpen(); emit configurationChanged(); } }
bool IOSWebView::loading() const { return _private->loading; }
bool IOSWebView::canGoBack() const { return _private->back; }
bool IOSWebView::canGoForward() const { return _private->forward; }
QString IOSWebView::error() const { return _private->error; }
QImage IOSWebView::frameSource() const { return _private->image; }
bool IOSWebView::bridgeAvailable() const {
    return active() && _private->bridgeReady && _private->policy.allowsBridge(_private->generation, _private->bridgeFrame, true, 1);
}

void IOSWebView::componentComplete() {
    QQuickPaintedItem::componentComplete();
    _private->complete = true;
    if (_private->bootstrap.isEmpty()) {
        if (auto* context = QQmlEngine::contextForObject(this)) {
            _private->bootstrap = context->contextProperty(QStringLiteral("eventBridgeJavaScriptToInject")).toString();
        }
    }
    scheduleOpen();
}
void IOSWebView::geometryChange(const QRectF& next, const QRectF& previous) {
    QQuickPaintedItem::geometryChange(next, previous);
    if (next.size() != previous.size() && !_private->presentation) { scheduleOpen(); }
}
void IOSWebView::paint(QPainter* painter) {
    if (_private->background) { painter->fillRect(boundingRect(), Qt::white); }
    if (!_private->image.isNull()) { painter->drawImage(boundingRect(), _private->image); }
    else if (!_private->error.isEmpty()) {
        painter->setPen(Qt::darkGray); painter->drawText(boundingRect().adjusted(12, 12, -12, -12), Qt::AlignCenter | Qt::TextWordWrap, _private->error);
    }
}
void IOSWebView::scheduleOpen() {
    // Revoke before public configuration signals or the queued replacement.
    // The bridge objects stay alive through a possible current Qt invocation.
    if (_private->generation) {
        _private->policy.close(); _private->generation = 0;
        _private->document.invalidate(); _private->snapshot.detach();
        _private->bridgeReady = false; _private->bridgeFrame = QUrl();
        _private->deadline.stop(); [_private->view stopLoading];
        _private->image = QImage(); emit frameChanged(); emit bridgeAvailableChanged(); update();
    }
    if (_private->complete) { _private->openTimer.start(0); }
}
bool IOSWebView::active() const {
    return NSThread.isMainThread && _private->generation && _private->policy.active() &&
        _private->generation == _private->policy.generation() && _private->window.isKeyWindow &&
        _private->window.windowScene.activationState == UISceneActivationStateForegroundActive &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive && isVisible() && isEnabled();
}
bool IOSWebView::allowsNavigation(const QUrl& destination, bool mainFrame, const QString& method) const {
    return active() && _private->policy.allowsNavigation(_private->generation, destination, mainFrame, method);
}
void IOSWebView::setLoading(bool value) { if (_private->loading != value) { _private->loading = value; emit loadingChanged(); } }
void IOSWebView::updateNavigation() {
    _private->back = _private->view.canGoBack;
    _private->forward = _private->view.canGoForward;
    if (_private->presentation) {
        _private->presentation.topViewController.navigationItem.title = nativeString(qtURL(_private->view.URL).host());
    }
    emit navigationChanged();
}

void IOSWebView::tearDown() {
    _private->policy.close(); // Shared invalidation precedes every native cleanup.
    _private->generation = 0;
    _private->openTimer.stop(); _private->deadline.stop();
    _private->snapshot.detach(); _private->channel.reset();
    _private->document.invalidate();
    if (_private->scriptReply) { _private->scriptReply->abort(); _private->scriptReply->deleteLater(); _private->scriptReply = nullptr; }
    _private->script.clear();
    _private->bridgeFrame = QUrl();
    _private->bridgeReady = false; emit bridgeAvailableChanged();
    _private->inputActive = false;
    @try {
        for (id observer in _private->observers) { [NSNotificationCenter.defaultCenter removeObserver:observer]; }
        _private->observers = nil;
        if (_private->delegate) { _private->delegate->owner.clear(); }
        if (_private->qrcHandler) { _private->qrcHandler->owner.clear(); }
        [_private->view stopLoading];
        _private->view.navigationDelegate = nil; _private->view.UIDelegate = nil;
        [_private->view.configuration.userContentController removeAllScriptMessageHandlers];
        [_private->view.configuration.userContentController removeAllUserScripts];
        [_private->view removeFromSuperview];
        if (_private->presentation.presentingViewController) { [_private->presentation dismissViewControllerAnimated:NO completion:nil]; }
    } @catch (NSException*) {
        _private->cleanupFailed = true; // No replacement after an unknown native stop.
        @try { [_private->view stopLoading]; [_private->view removeFromSuperview]; }
        @catch (NSException*) {}
    }
    _private->view = nil; _private->delegate = nil; _private->qrcHandler = nil; _private->presentation = nil;
    _private->window = nil; _private->presenter = nil;
    _private->image = QImage(); emit frameChanged(); update();
    setLoading(false); updateNavigation();
}
void IOSWebView::stop() { _private->resumeOnForeground = false; tearDown(); }
void IOSWebView::fail(const QString& message) {
    _private->error = message; emit errorChanged(); tearDown(); update();
}

void IOSWebView::open() {
    tearDown();
    if (_private->cleanupFailed) { fail(tr("Native browser cleanup failed. Restart Overte before opening another page.")); return; }
    if (!isVisible() || !isEnabled() || _private->url.isEmpty() || !qIsFinite(width()) || !qIsFinite(height()) || width() <= 0 || height() <= 0) { return; }
    if (_private->surface != QStringLiteral("tablet") && _private->surface != QStringLiteral("world-entity")) {
        fail(tr("Unknown web surface.")); return;
    }
    _private->policy.setVisible(true);
    _private->policy.setForeground(UIApplication.sharedApplication.applicationState == UIApplicationStateActive);
    _private->documentRoot = packagedRoot(_private->url);
    _private->scriptRoot = packagedRoot(_private->scriptUrl);
    if (!_private->packagedRoot.isEmpty() && _private->packagedRoot != _private->scriptRoot) {
        fail(tr("The packaged script root does not match the native resource owner.")); return;
    }
    _private->generation = _private->policy.open(_private->url,
        _private->surface == QStringLiteral("tablet") ? web::Surface::Tablet : web::Surface::WorldEntity, _private->identity,
        _private->documentRoot);
    if (!_private->generation) { fail(tr("This web URL is not permitted.")); return; }
    _private->error.clear(); emit errorChanged(); setLoading(true);
    UIWindow* window = nil;
    _private->presenter = presenter(&window); _private->window = window;
    if (!_private->presenter) { fail(tr("No active window is available for this web page.")); return; }
    const auto generation = _private->generation;
    QPointer<IOSWebView> owner(this);
    _private->channel.reset([owner, generation](const QUrl& frame, bool mainFrame, std::size_t bytes) {
        return owner && owner->active() && owner->_private->generation == generation &&
            owner->_private->policy.allowsBridge(generation, frame, mainFrame, bytes);
    });
    _private->deadline.start();
    // Script bytes are prepared before the WK configuration is constructed.
    // A source assignment grants this URL; pages cannot assign scriptUrl.
    auto createView = [owner, generation] {
        if (!owner || !owner->active() || owner->_private->generation != generation) { return; }
        auto& state = *owner->_private;
        @try {
            WKWebViewConfiguration* configuration = [WKWebViewConfiguration new];
            configuration.websiteDataStore = [WKWebsiteDataStore nonPersistentDataStore];
            configuration.defaultWebpagePreferences.allowsContentJavaScript = YES;
            configuration.preferences.javaScriptCanOpenWindowsAutomatically = NO;
            configuration.allowsInlineMediaPlayback = YES;
            configuration.allowsAirPlayForMediaPlayback = NO;
            configuration.mediaTypesRequiringUserActionForPlayback = WKAudiovisualMediaTypeAll;
            configuration.dataDetectorTypes = WKDataDetectorTypeNone;
            if (state.url.scheme() == QStringLiteral("qrc")) {
                state.qrcHandler = [OverteIOSQrcHandler new];
                state.qrcHandler->owner = owner; state.qrcHandler->generation = generation;
                [configuration setURLSchemeHandler:state.qrcHandler forURLScheme:@"overte-qrc"];
            }
            state.delegate = [OverteIOSWebDelegate new];
            state.delegate->owner = owner; state.delegate->generation = generation;
            [configuration.userContentController addScriptMessageHandler:state.delegate name:@"overteWebChannel"];
            const auto size = QSize(static_cast<int>(qBound(1.0, owner->width(), 2048.0)),
                                    static_cast<int>(qBound(1.0, owner->height(), 2048.0)));
            state.view = [[WKWebView alloc] initWithFrame:CGRectMake(0, 0, size.width(), size.height()) configuration:configuration];
            state.view.navigationDelegate = state.delegate; state.view.UIDelegate = state.delegate;
            state.view.opaque = state.background;
            state.view.backgroundColor = state.background ? UIColor.whiteColor : UIColor.clearColor;
            state.view.allowsLinkPreview = NO;
            if (!state.userAgent.isEmpty()) { state.view.customUserAgent = nativeString(state.userAgent); }
            [state.window.rootViewController.view insertSubview:state.view atIndex:0];
            state.observers = [NSMutableArray array];
            for (NSNotificationName name in @[UIApplicationWillResignActiveNotification, UISceneWillDeactivateNotification,
                    UIWindowDidResignKeyNotification]) {
                id token = [NSNotificationCenter.defaultCenter addObserverForName:name object:nil queue:NSOperationQueue.mainQueue
                    usingBlock:^(NSNotification* note) {
                        if (!owner || owner->_private->generation != generation) { return; }
                        if ([note.name isEqualToString:UIApplicationWillResignActiveNotification] ||
                                note.object == owner->_private->window.windowScene || note.object == owner->_private->window) {
                            owner->_private->resumeOnForeground = true;
                            owner->_private->policy.setForeground(false); owner->tearDown();
                        }
                    }];
                [state.observers addObject:token];
            }
            if (state.surface == QStringLiteral("tablet") && !owner->openNative()) { owner->fail(owner->tr("Unable to present the native browser.")); return; }
            NSURL* url = nativeURL(state.url);
            if (!owner->allowsNavigation(qtURL(url), true, QStringLiteral("GET"))) { owner->fail(owner->tr("This web request is not permitted.")); return; }
            if (state.url.isLocalFile()) {
                [state.view loadFileURL:url allowingReadAccessToURL:[NSURL fileURLWithPath:nativeString(state.documentRoot) isDirectory:YES]];
            } else {
                [state.view loadRequest:[NSURLRequest requestWithURL:url cachePolicy:NSURLRequestUseProtocolCachePolicy timeoutInterval:30]];
            }
        } @catch (NSException*) { owner->fail(owner->tr("Unable to create the native browser.")); }
    };
    if (_private->scriptUrl.isEmpty()) { createView(); return; }
    if (!_private->policy.allowsScriptURL(_private->scriptUrl, _private->scriptRoot)) { fail(tr("This injected script URL is not permitted.")); return; }
    if (_private->scriptUrl.scheme() == QStringLiteral("qrc") || _private->scriptUrl.isLocalFile()) {
        QFile file(_private->scriptUrl.scheme() == QStringLiteral("qrc") ? QStringLiteral(":") + _private->scriptUrl.path() : _private->scriptUrl.toLocalFile());
        if (!file.open(QFile::ReadOnly) || file.size() > 1024 * 1024) { fail(tr("The packaged web script is unavailable.")); return; }
        _private->script = file.readAll(); createView(); return;
    }
    QNetworkRequest request(_private->scriptUrl);
    request.setAttribute(QNetworkRequest::RedirectPolicyAttribute, QNetworkRequest::ManualRedirectPolicy);
    _private->scriptReply = _private->network.get(request);
    auto* reply = _private->scriptReply.data();
    connect(reply, &QNetworkReply::readyRead, this, [owner, generation, reply] {
        if (!owner || owner->_private->generation != generation) { return; }
        owner->_private->script.append(reply->readAll());
        if (owner->_private->script.size() > 1024 * 1024) { owner->fail(owner->tr("The web script exceeds the allowed size.")); }
    });
    connect(reply, &QNetworkReply::finished, this, [owner, generation, reply, createView] {
        if (!owner || owner->_private->generation != generation) { reply->deleteLater(); return; }
        owner->_private->scriptReply = nullptr;
        const bool success = reply->error() == QNetworkReply::NoError &&
            !reply->attribute(QNetworkRequest::RedirectionTargetAttribute).isValid();
        owner->_private->script.append(reply->readAll()); reply->deleteLater();
        if (!success || owner->_private->script.size() > 1024 * 1024) { owner->fail(owner->tr("The web script could not be loaded.")); return; }
        createView();
    });
}

bool IOSWebView::openNative() {
    if (!active() || !_private->view || !_private->presenter) { return false; }
    if (_private->presentation) { return true; }
    if (_private->presenter.presentedViewController) { return false; }
    _private->snapshot.detach();
    UIViewController* content = [UIViewController new];
    content.view.backgroundColor = UIColor.systemBackgroundColor;
    [_private->view removeFromSuperview];
    _private->view.translatesAutoresizingMaskIntoConstraints = NO;
    [content.view addSubview:_private->view];
    [NSLayoutConstraint activateConstraints:@[
        [_private->view.topAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.topAnchor],
        [_private->view.leadingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.leadingAnchor],
        [_private->view.trailingAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.trailingAnchor],
        [_private->view.bottomAnchor constraintEqualToAnchor:content.view.safeAreaLayoutGuide.bottomAnchor]
    ]];
    content.navigationItem.title = nativeString(_private->url.host().isEmpty() ? tr("Overte app") : _private->url.host());
    content.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:@"Close" style:UIBarButtonItemStyleDone target:_private->delegate action:@selector(close)];
    content.toolbarItems = @[
        [[UIBarButtonItem alloc] initWithTitle:@"Back" style:UIBarButtonItemStylePlain target:_private->delegate action:@selector(back)],
        [[UIBarButtonItem alloc] initWithTitle:@"Forward" style:UIBarButtonItemStylePlain target:_private->delegate action:@selector(forward)],
        [[UIBarButtonItem alloc] initWithTitle:@"Reload" style:UIBarButtonItemStylePlain target:_private->delegate action:@selector(reload)]
    ];
    _private->presentation = [[UINavigationController alloc] initWithRootViewController:content];
    _private->presentation.toolbarHidden = NO;
    _private->presentation.modalPresentationStyle = UIModalPresentationFullScreen;
    _private->presentation.modalInPresentation = YES;
    [_private->presenter presentViewController:_private->presentation animated:NO completion:nil];
    return true;
}
void IOSWebView::closePresentation() {
    if (_private->surface == QStringLiteral("tablet")) { stop(); emit nativeClosed(); return; }
    if (!_private->presentation) { return; }
    [_private->view removeFromSuperview];
    QPointer<IOSWebView> owner(this);
    const auto generation = _private->generation;
    [_private->presentation dismissViewControllerAnimated:NO completion:^{
        if (!owner || !owner->active() || owner->_private->generation != generation) { return; }
        auto& state = *owner->_private;
        state.presentation = nil;
        state.view.translatesAutoresizingMaskIntoConstraints = YES;
        const QSize size(qBound(1, static_cast<int>(owner->width()), 2048), qBound(1, static_cast<int>(owner->height()), 2048));
        state.view.frame = CGRectMake(0, 0, size.width(), size.height());
        [state.window.rootViewController.view insertSubview:state.view atIndex:0];
        if (!state.loading) { owner->nativeNavigationFinished(); }
        emit owner->nativeClosed();
    }];
}
void IOSWebView::nativeNavigationFinished() {
    if (!active()) { return; }
    _private->deadline.stop(); setLoading(false); updateNavigation();
    if (!_private->presentation) {
        const QSize size(qBound(1, static_cast<int>(width()), 2048), qBound(1, static_cast<int>(height()), 2048));
        if (!_private->snapshot.attach((__bridge void*)_private->view, size)) {
            _private->error = tr("Unable to capture the web surface. Open the native browser to interact.");
            emit errorChanged(); update();
        }
    }
}
void IOSWebView::verifyDocument() {
    if (!active() || !_private->view) { return; }
    QPointer<IOSWebView> owner(this);
    const auto generation = _private->generation;
    const auto epoch = _private->document.epoch();
    const auto nonce = encodedArguments(QJsonArray { _private->document.nonce() });
    const auto script = QStringLiteral("!!(window.qt&&qt.webChannelTransport&&qt.webChannelTransport.document===%1[0]);").arg(nonce);
    [_private->view evaluateJavaScript:nativeString(script) completionHandler:^(id result, NSError* error) {
        if (!owner || !owner->active() || owner->_private->generation != generation || owner->_private->document.epoch() != epoch) { return; }
        auto& state = *owner->_private;
        const auto verified = state.document.verify(generation, epoch,
            !error && [result isKindOfClass:NSNumber.class] && [result boolValue]);
        if (verified == IOSWebDocumentEpoch::Verification::Ready) {
            owner->nativeNavigationFinished();
        } else if (verified == IOSWebDocumentEpoch::Verification::Reload) {
            // WK's back-forward cache can restore the old JavaScript context
            // without document-start injection. Reload this history item once;
            // do not reauthorize its origin or accept the cached old nonce.
            [state.view reload];
        } else if (verified == IOSWebDocumentEpoch::Verification::Failed) {
            owner->fail(owner->tr("The web document could not be initialized. Reload to try again."));
        }
    }];
}
void IOSWebView::nativeMessage(const QString& envelope, const QString& documentNonce, const QUrl& frame, bool mainFrame) {
    if (active() && _private->document.accepts(_private->generation, documentNonce, frame, mainFrame) &&
            _private->policy.allowsBridge(_private->generation, frame, mainFrame,
            static_cast<std::size_t>(envelope.toUtf8().size()))) {
        // WK's URL may not yet be committed at document creation, when the real
        // qwebchannel bootstrap sends init. Bind replies to the validated frame.
        _private->bridgeFrame = frame;
        _private->channel.receiveEnvelope(envelope, frame, mainFrame);
    }
}
void IOSWebView::prepareDocument(const QUrl& frame) {
    if (!active() || !_private->view) { return; }
    _private->snapshot.detach(); _private->bridgeFrame = QUrl();
    _private->bridgeReady = false; emit bridgeAvailableChanged();
    if (!_private->document.begin(_private->generation, frame, QUuid::createUuid().toString(QUuid::WithoutBraces))) {
        fail(tr("The web document identity is unavailable.")); return;
    }
    QPointer<IOSWebView> guarded(this);
    const auto generation = _private->generation;
    _private->channel.reset([guarded, generation](const QUrl& frameURL, bool mainFrame, std::size_t bytes) {
        return guarded && guarded->active() && guarded->_private->generation == generation &&
            guarded->_private->policy.allowsBridge(generation, frameURL, mainFrame, bytes);
    });
    WKUserContentController* controller = _private->view.configuration.userContentController;
    [controller removeAllUserScripts];
    WKUserScript* bridge = [[WKUserScript alloc] initWithSource:nativeString(IOSWebChannel::transportJavaScript(_private->document.nonce()) + _private->bootstrap)
        injectionTime:WKUserScriptInjectionTimeAtDocumentStart forMainFrameOnly:YES];
    [controller addUserScript:bridge];
    if (!_private->script.isEmpty()) {
        WKUserScript* user = [[WKUserScript alloc] initWithSource:nativeString(QString::fromUtf8(_private->script))
            injectionTime:WKUserScriptInjectionTimeAtDocumentEnd forMainFrameOnly:YES];
        [controller addUserScript:user];
    }
}
void IOSWebView::emitScriptEvent(const QVariant& message) {
    if (active()) { _private->channel.publishScriptEvent(message); }
}
void IOSWebView::evaluate(const QString& code) {
    if (active() && _private->view) { [_private->view evaluateJavaScript:nativeString(guardedScript(code, _private->document.nonce())) completionHandler:nil]; }
}
void IOSWebView::goBack() { if (active() && _private->view.canGoBack) { _private->document.resetRecovery(); [_private->view goBack]; } }
void IOSWebView::goForward() { if (active() && _private->view.canGoForward) { _private->document.resetRecovery(); [_private->view goForward]; } }
void IOSWebView::reload() { if (active() && _private->view) { _private->document.resetRecovery(); [_private->view reload]; } else { scheduleOpen(); } }
void IOSWebView::reloadAndBypassCache() { if (active() && _private->view) { _private->document.resetRecovery(); [_private->view reloadFromOrigin]; } else { scheduleOpen(); } }
void IOSWebView::unfocus() { evaluate(QStringLiteral("if(document.activeElement)document.activeElement.blur();")); }
void IOSWebView::runJavaScript(const QString& code, const QJSValue& callback) {
    if (!active() || !_private->view || code.toUtf8().size() > 1024 * 1024) { return; }
    const auto identity = encodedArguments(QJsonArray { _private->document.nonce() });
    // A guarded if-statement preserves JavaScript's completion value for the
    // existing WebView callback API, without eval or message interpolation.
    const auto source = QStringLiteral("if(window.qt&&qt.webChannelTransport&&qt.webChannelTransport.document===%1[0]){\n%2\n}").arg(identity, code);
    QPointer<IOSWebView> owner(this);
    const auto generation = _private->generation;
    const auto epoch = _private->document.epoch();
    [_private->view evaluateJavaScript:nativeString(source) completionHandler:^(id result, NSError* error) {
        if (!owner || !owner->active() || owner->_private->generation != generation || owner->_private->document.epoch() != epoch || !callback.isCallable()) { return; }
        auto* engine = qmlEngine(owner.data());
        if (!engine) { return; }
        QJSValue callable = callback;
        callable.call({ error ? QJSValue(QJSValue::UndefinedValue) : engine->toScriptValue(qtValue(result)) });
    }];
}
void IOSWebView::pointerEvent(const QString& type, double x, double y, int button) {
    if (_private->presentation || !active() || !qIsFinite(x) || !qIsFinite(y) || x < 0 || y < 0 || x > width() || y > height()) { return; }
    if (type != QStringLiteral("press") && type != QStringLiteral("release") && type != QStringLiteral("move")) { return; }
    forceActiveFocus();
    const auto args = encodedArguments(QJsonArray { type, x * qMin(width(), 2048.0) / width(), y * qMin(height(), 2048.0) / height(), button });
    const QString code = QStringLiteral(R"JS((function(a){var el=document.elementFromPoint(a[1],a[2]);if(!el)return false;
var kind=a[0]==='press'?'mousedown':a[0]==='release'?'mouseup':'mousemove';
el.dispatchEvent(new MouseEvent(kind,{bubbles:true,clientX:a[1],clientY:a[2],button:a[3]}));
if(a[0]==='press'){el.focus();window.__overteInput=el;}
if(a[0]==='release'){el.click();}
return !!(el.isContentEditable||el.tagName==='TEXTAREA'||(el.tagName==='INPUT'&&!/^(button|submit|checkbox|radio|file|range|color|hidden)$/.test(el.type)));})(%1);)JS").arg(args);
    QPointer<IOSWebView> owner(this);
    const auto generation = _private->generation;
    const auto epoch = _private->document.epoch();
    [_private->view evaluateJavaScript:nativeString(guardedScript(QStringLiteral("return ") + code, _private->document.nonce())) completionHandler:^(id result, NSError* error) {
        if (!owner || !owner->active() || owner->_private->generation != generation || type != QStringLiteral("press")) { return; }
        if (owner->_private->document.epoch() != epoch) { return; }
        owner->_private->inputActive = !error && [result isKindOfClass:NSNumber.class] && [result boolValue];
        QGuiApplication::inputMethod()->update(Qt::ImEnabled | Qt::ImHints);
        if (owner->_private->inputActive) { QGuiApplication::inputMethod()->show(); }
    }];
}
void IOSWebView::keyEvent(const QString& text, int key, int modifiers) {
    Q_UNUSED(modifiers);
    if (!active() || text.size() > 8192) { return; }
    const bool control = key == Qt::Key_Backspace || key == Qt::Key_Delete || key == Qt::Key_Return || key == Qt::Key_Enter;
    const auto args = encodedArguments(QJsonArray { control ? QString() : text, key });
    evaluate(QStringLiteral(R"JS((function(a){var el=document.activeElement;if(!el)return;
if(typeof el.value==='string'){var start=el.selectionStart==null?el.value.length:el.selectionStart;
var end=el.selectionEnd==null?start:el.selectionEnd;
if(a[1]===16777219&&!a[0]&&start===end&&start>0)start--;
if(a[1]===16777223&&!a[0]&&start===end&&end<el.value.length)end++;
el.value=el.value.substring(0,start)+a[0]+el.value.substring(end);
if(el.setSelectionRange)el.setSelectionRange(start+a[0].length,start+a[0].length);
el.dispatchEvent(new Event('input',{bubbles:true}));}
else if(el.isContentEditable){document.execCommand(a[1]===16777219?'delete':'insertText',false,a[0]);}
el.dispatchEvent(new KeyboardEvent('keydown',{bubbles:true,key:a[1]===16777220||a[1]===16777221?'Enter':a[0]}));
if((a[1]===16777220||a[1]===16777221)&&el.form)el.form.requestSubmit();})(%1);)JS").arg(args));
}
void IOSWebView::mousePressEvent(QMouseEvent* event) { pointerEvent(QStringLiteral("press"), event->position().x(), event->position().y(), event->button() == Qt::RightButton ? 2 : 0); event->accept(); }
void IOSWebView::mouseReleaseEvent(QMouseEvent* event) { pointerEvent(QStringLiteral("release"), event->position().x(), event->position().y(), event->button() == Qt::RightButton ? 2 : 0); event->accept(); }
void IOSWebView::mouseMoveEvent(QMouseEvent* event) { pointerEvent(QStringLiteral("move"), event->position().x(), event->position().y()); event->accept(); }
void IOSWebView::wheelEvent(QWheelEvent* event) {
    evaluate(QStringLiteral("window.scrollBy(0,%1);").arg(-event->angleDelta().y())); event->accept();
}
void IOSWebView::keyPressEvent(QKeyEvent* event) { keyEvent(event->text(), event->key(), event->modifiers()); event->accept(); }
void IOSWebView::inputMethodEvent(QInputMethodEvent* event) { keyEvent(event->commitString()); event->accept(); }
QVariant IOSWebView::inputMethodQuery(Qt::InputMethodQuery query) const {
    if (query == Qt::ImEnabled) { return active() && _private->inputActive && !_private->presentation; }
    if (query == Qt::ImHints) { return static_cast<int>(Qt::ImhNoPredictiveText); }
    return QQuickPaintedItem::inputMethodQuery(query);
}

bool IOSWebViewNative::current(IOSWebView* owner, std::uint64_t generation) { return owner && owner->active() && owner->_private->generation == generation; }
bool IOSWebViewNative::navigation(IOSWebView* owner, std::uint64_t generation, NSURL* url, bool mainFrame, NSString* method) { return current(owner, generation) && owner->allowsNavigation(qtURL(url), mainFrame, qtString(method)); }
void IOSWebViewNative::message(IOSWebView* owner, std::uint64_t generation, NSString* message, NSString* nonce, NSURL* frame, bool mainFrame) { if (current(owner, generation)) { owner->nativeMessage(qtString(message), qtString(nonce), qtURL(frame), mainFrame); } }
void IOSWebViewNative::prepare(IOSWebView* owner, std::uint64_t generation, NSURL* frame) { if (current(owner, generation)) { owner->prepareDocument(qtURL(frame)); } }
void IOSWebViewNative::redirected(IOSWebView* owner, std::uint64_t generation, NSURL* frame) { if (current(owner, generation)) { owner->_private->document.redirected(qtURL(frame)); } }
void IOSWebViewNative::finished(IOSWebView* owner, std::uint64_t generation) { if (current(owner, generation)) { owner->verifyDocument(); } }
void IOSWebViewNative::started(IOSWebView* owner, std::uint64_t generation) {
    if (!current(owner, generation)) { return; }
    owner->_private->snapshot.detach();
    owner->setLoading(true); owner->_private->deadline.start();
}
void IOSWebViewNative::failed(IOSWebView* owner, std::uint64_t generation) { if (current(owner, generation)) { owner->fail(owner->tr("The web page could not be loaded. Reload to try again.")); } }
void IOSWebViewNative::close(IOSWebView* owner) { if (owner) { owner->closePresentation(); } }
} // namespace overte::ios

namespace {
void registerIOSWebView() { qmlRegisterType<overte::ios::IOSWebView>("Overte.iOS", 1, 0, "IOSWebView"); }
Q_COREAPP_STARTUP_FUNCTION(registerIOSWebView)
}
