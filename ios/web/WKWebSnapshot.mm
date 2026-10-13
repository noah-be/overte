// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "WKWebSnapshot.h"
#include "EmbeddedWebSurfaceState.h"
#include <QElapsedTimer>
#include <QPointer>
#include <QTimer>
#import <UIKit/UIKit.h>
#import <WebKit/WebKit.h>

namespace overte::ios {
namespace {
bool foreground(WKWebView* view) {
    return NSThread.isMainThread && view.window.isKeyWindow && !view.hidden && !view.window.hidden &&
        view.window.windowScene.activationState == UISceneActivationStateForegroundActive &&
        UIApplication.sharedApplication.applicationState == UIApplicationStateActive;
}
}
struct WKWebSnapshot::Private {
    __strong WKWebView* view { nil };
    EmbeddedWebSurfaceState state;
    std::uint64_t generation { 0 };
    QTimer timer;
    QElapsedTimer clock;
    bool nativeCapturePending { false };
    std::uint64_t nativeCaptureStarted { 0 };
};

WKWebSnapshot::WKWebSnapshot(QObject* parent) : QObject(parent), _private(std::make_unique<Private>()) {
    _private->clock.start();
    _private->timer.setInterval(EmbeddedWebSurfaceState::FRAME_INTERVAL_MS);
    connect(&_private->timer, &QTimer::timeout, this, &WKWebSnapshot::capture);
}

WKWebSnapshot::~WKWebSnapshot() { detach(); }

void WKWebSnapshot::detach() {
    _private->state.invalidate(); // Old completions cannot release a new capture.
    _private->generation = 0;
    _private->timer.stop();
    _private->view = nil;
}

bool WKWebSnapshot::attach(void* nativeView, QSize logicalSize) {
    detach();
    if (!NSThread.isMainThread ||
            logicalSize.width() <= 0 || logicalSize.height() <= 0) { return false; }
    const EmbeddedWebSurfaceState::Size size {
        static_cast<unsigned>(logicalSize.width()), static_cast<unsigned>(logicalSize.height()) };
    if (!EmbeddedWebSurfaceState::validSize(size)) { return false; }
    WKWebView* view = (__bridge WKWebView*)nativeView;
    if (![view isKindOfClass:WKWebView.class] || !foreground(view) ||
            view.bounds.size.width < size.width || view.bounds.size.height < size.height) { return false; }
    _private->view = view;
    _private->generation = _private->state.reset(size, true);
    _private->timer.start();
    capture();
    return _private->generation != 0;
}

void WKWebSnapshot::fail() {
    detach();
    emit failed(); // Closed signal: no URLs, native errors or content.
}

void WKWebSnapshot::capture() {
    if (!NSThread.isMainThread || !_private->generation) { return; }
    WKWebView* view = _private->view;
    if (!foreground(view)) { fail(); return; }
    const auto generation = _private->generation;
    const auto now = static_cast<std::uint64_t>(_private->clock.elapsed());
    if (_private->state.snapshotTimedOut(generation, now)) { fail(); return; }
    if (_private->nativeCapturePending) {
        // A replacement can wait for the old operation without submitting a
        // second native capture. Its original deadline still applies.
        if (now - _private->nativeCaptureStarted >= EmbeddedWebSurfaceState::SNAPSHOT_TIMEOUT_MS) { fail(); }
        return;
    }
    if (!_private->state.beginSnapshot(generation, now)) { return; }
    _private->nativeCapturePending = true;
    _private->nativeCaptureStarted = now;
    const auto size = _private->state.size();
    QPointer<WKWebSnapshot> owner(this);
    @try {
        WKSnapshotConfiguration* configuration = [WKSnapshotConfiguration new];
        configuration.rect = CGRectMake(0, 0, size.width, size.height);
        configuration.snapshotWidth = @(size.width);
        configuration.afterScreenUpdates = NO;
        [view takeSnapshotWithConfiguration:configuration completionHandler:^(UIImage* snapshot, NSError* error) {
            if (!owner) { return; }
            owner->_private->nativeCapturePending = false;
            if (!owner->_private->state.current(generation)) { return; }
            if (error || !snapshot.CGImage || !foreground(owner->_private->view)) { owner->fail(); return; }
            // WebKit may return a Retina bitmap. Bound our upload allocation to
            // the requested logical dimensions rather than device scale.
            QImage pixels(static_cast<int>(size.width), static_cast<int>(size.height), QImage::Format_RGBA8888_Premultiplied);
            if (pixels.isNull()) { owner->fail(); return; }
            CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
            CGContextRef context = CGBitmapContextCreate(pixels.bits(), size.width, size.height,
                8, pixels.bytesPerLine(), colorSpace, kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
            CGColorSpaceRelease(colorSpace);
            if (!context) { owner->fail(); return; }
            CGContextDrawImage(context, CGRectMake(0, 0, size.width, size.height), snapshot.CGImage);
            CGContextRelease(context);
            const auto completed = static_cast<std::uint64_t>(owner->_private->clock.elapsed());
            if (!owner->_private->state.finishSnapshot(generation, size, completed)) { owner->fail(); return; }
            emit owner->imageReady(pixels);
        }];
    } @catch (NSException*) { _private->nativeCapturePending = false; fail(); }
}
} // namespace overte::ios
