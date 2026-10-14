// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "IOSSnapshotAdapter.h"
#include "SnapshotExportOperation.h"
#include "../../interface/src/ui/SnapshotStorage.h"
#include <QCoreApplication>
#include <QGuiApplication>
#include <QPointer>
#include <QThread>
#include <QUuid>
#include <QtQml/qqml.h>
#import <UIKit/UIKit.h>
#import <Photos/Photos.h>

namespace overte::ios {
struct IOSSnapshotNativeOperation {
    IOSSnapshotNativeOperation(QString ticket,QString path,QString action,IOSSnapshotAdapter* owner) :
        state(std::move(ticket),std::move(path),std::move(action)),owner(owner) {}
    SnapshotExportOperation state;
    QPointer<IOSSnapshotAdapter> owner;
    // Accessed only on the UIKit main actor; retain original app-owned files.
    __strong UIActivityViewController* sheet {nil};
};
namespace {
bool guiThread() { return qGuiApp && QThread::currentThread()==qGuiApp->thread(); }
NSString* string(const QString& value) { const auto bytes=value.toUtf8();return [[NSString alloc] initWithBytes:bytes.constData() length:bytes.size() encoding:NSUTF8StringEncoding]; }
UIViewController* presenter() {
    for(UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if(scene.activationState!=UISceneActivationStateForegroundActive || ![scene isKindOfClass:UIWindowScene.class]) { continue; }
        for(UIWindow* window in ((UIWindowScene*)scene).windows) {
            if(!window.isKeyWindow || window.hidden) { continue; }
            UIViewController* controller=window.rootViewController;
            while(controller.presentedViewController && !controller.presentedViewController.isBeingDismissed) { controller=controller.presentedViewController; }
            if(controller.view.window && !controller.isBeingDismissed) { return controller; }
        }
    }
    return nil;
}
void deliver(const std::shared_ptr<IOSSnapshotNativeOperation>& operation,const QString& status,const QString& error={}) {
    if(!operation->state.finish()) { return; }
    // Delivery and QPointer inspection execute in the Qt GUI owner, not a
    // Photos worker queue. A destroyed/replaced review cannot receive results.
    if(auto application=QCoreApplication::instance()) {
        QMetaObject::invokeMethod(application,[operation,status,error] {
            if(operation->owner) { operation->owner->nativeFinished(operation,status,error); }
        },Qt::QueuedConnection);
    }
}
// Objective-C Blocks preserve reference capture types. Own the request and
// return payload by value before any delayed native callback captures them.
void dismissShare(std::shared_ptr<IOSSnapshotNativeOperation> operation,QString status,QString error={}) {
    auto sheet=operation->sheet;
    if(!sheet || !sheet.presentingViewController) { operation->sheet=nil;deliver(operation,status,error);return; }
    if(sheet.isBeingPresented && sheet.transitionCoordinator) {
        [sheet.transitionCoordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context) {
            (void)context;
            dismissShare(operation,status,error);
        }];
        return;
    }
    [sheet dismissViewControllerAnimated:NO completion:^{
        operation->sheet=nil;
        deliver(operation,status,error);
    }];
}
void cancelNative(std::shared_ptr<IOSSnapshotNativeOperation> operation) {
    dispatch_async(dispatch_get_main_queue(),^{
        if(!operation->state.current()) { return; }
        const auto phase=operation->state.phase();
        if(phase==SnapshotExportOperation::Phase::Committed || phase==SnapshotExportOperation::Phase::Authorizing) {
            // A visible permission prompt cannot be dismissed by the app. Wait
            // for its real return; after Photos commitment await the real save.
            return;
        }
        dismissShare(operation,"cancelled");
    });
}
void saveToPhotos(std::shared_ptr<IOSSnapshotNativeOperation> operation) {
    if(!operation->state.advance(SnapshotExportOperation::Phase::Authorizing)) { deliver(operation,"cancelled");return; }
    [PHPhotoLibrary requestAuthorizationForAccessLevel:PHAccessLevelAddOnly handler:^(PHAuthorizationStatus status) {
        dispatch_async(dispatch_get_main_queue(),^{
            if(!operation->state.current()) { return; }
            if(operation->state.cancelled()) { deliver(operation,"cancelled");return; }
            if(status!=PHAuthorizationStatusAuthorized && status!=PHAuthorizationStatusLimited) {
                deliver(operation,"error",IOSSnapshotAdapter::tr("Permission to save snapshots to Photos was denied."));return;
            }
            const auto validated=overte::snapshot::exportPath(operation->state.path);
            if(validated.isEmpty() || validated!=operation->state.path) {
                deliver(operation,"error",IOSSnapshotAdapter::tr("The snapshot file is no longer available."));return;
            }
            NSURL* file=[NSURL fileURLWithPath:string(validated)];
            if(!operation->state.advance(SnapshotExportOperation::Phase::Committed)) { deliver(operation,"cancelled");return; }
            [[PHPhotoLibrary sharedPhotoLibrary] performChanges:^{
                PHAssetCreationRequest* asset=[PHAssetCreationRequest creationRequestForAsset];
                PHAssetResourceCreationOptions* options=[[PHAssetResourceCreationOptions alloc] init];
                options.shouldMoveFile=NO;
                [asset addResourceWithType:PHAssetResourceTypePhoto fileURL:file options:options];
            } completionHandler:^(BOOL success,NSError* error) {
                // Preserve the actual Photos result even if Cancel/background
                // arrives after commitment. No fabricated rollback receipt.
                deliver(operation,success ? "success" : "error",success ? QString() : IOSSnapshotAdapter::tr("Photos could not save this snapshot."));
                (void)error;
            }];
        });
    }];
}
void shareWithSystem(std::shared_ptr<IOSSnapshotNativeOperation> operation) {
    if(!operation->state.advance(SnapshotExportOperation::Phase::Choosing)) { deliver(operation,"cancelled");return; }
    auto controller=presenter();
    if(!controller) { deliver(operation,"error",IOSSnapshotAdapter::tr("Open the snapshot review in the foreground to share."));return; }
    const auto validated=overte::snapshot::exportPath(operation->state.path);
    if(validated.isEmpty() || validated!=operation->state.path) { deliver(operation,"error",IOSSnapshotAdapter::tr("The snapshot file is no longer available."));return; }
    // NSURL preserves full-resolution still, panorama/cubemap and animated GIF
    // bytes. UIImage conversion would silently discard GIF animation.
    UIActivityViewController* sheet=[[UIActivityViewController alloc] initWithActivityItems:@[[NSURL fileURLWithPath:string(validated)]] applicationActivities:nil];
    operation->sheet=sheet;
    sheet.completionWithItemsHandler=^(UIActivityType activityType,BOOL completed,NSArray* returnedItems,NSError* error) {
        (void)activityType;(void)returnedItems;
        dispatch_async(dispatch_get_main_queue(),^{
            dismissShare(operation,error ? "error" : completed ? "success" : "cancelled",error ? IOSSnapshotAdapter::tr("The selected sharing service failed.") : QString());
        });
    };
    sheet.popoverPresentationController.sourceView=controller.view;
    sheet.popoverPresentationController.sourceRect=CGRectMake(CGRectGetMidX(controller.view.bounds),CGRectGetMidY(controller.view.bounds),1,1);
    sheet.popoverPresentationController.permittedArrowDirections=0;
    [controller presentViewController:sheet animated:YES completion:nil];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
        if(operation->state.current() && operation->state.phase()==SnapshotExportOperation::Phase::Choosing &&
                !sheet.presentingViewController && !sheet.isBeingPresented) {
            operation->sheet=nil;
            deliver(operation,"error",IOSSnapshotAdapter::tr("The system sharing window could not open."));
        }
    });
}
} // namespace
IOSSnapshotAdapter::IOSSnapshotAdapter(QObject* parent) : QObject(parent) {
    connect(qGuiApp,&QGuiApplication::applicationStateChanged,this,[this](Qt::ApplicationState state) {
        // The application's own Photos authorization prompt is inactive, not
        // background. Keep it alive until the user's real answer arrives.
        if(state==Qt::ApplicationHidden || state==Qt::ApplicationSuspended) {
            if(_operation) { cancel(_operation->state.ticket); }
        }
    });
}
IOSSnapshotAdapter::~IOSSnapshotAdapter() {
    if(_operation) { _operation->state.cancel();cancelNative(_operation); }
}
QString IOSSnapshotAdapter::request(const QString& canonicalPath,const QString& action) {
    if(!guiThread() || _operation || !capabilities().contains(action)) {
        _error=tr("A system snapshot request is already active or cannot start here.");emit changed();return {};
    }
    const auto validated=overte::snapshot::exportPath(canonicalPath);
    if(validated.isEmpty()) { _error=tr("Choose an existing snapshot saved by this app.");emit changed();return {}; }
    const auto ticket=QUuid::createUuid().toString(QUuid::WithoutBraces);
    auto operation=std::make_shared<IOSSnapshotNativeOperation>(ticket,validated,action,this);
    _operation=operation;_error.clear();emit changed();
    dispatch_async(dispatch_get_main_queue(),^{
        if(!operation->state.current() || operation->state.cancelled()) { deliver(operation,"cancelled");return; }
        if(!presenter()) { deliver(operation,"error",IOSSnapshotAdapter::tr("Open the snapshot review in the foreground."));return; }
        if(operation->state.action=="save") { saveToPhotos(operation); } else { shareWithSystem(operation); }
    });
    return ticket;
}
void IOSSnapshotAdapter::cancel(const QString& ticket) {
    if(!guiThread() || !_operation || _operation->state.ticket!=ticket) { return; }
    _operation->state.cancel();cancelNative(_operation);
}
void IOSSnapshotAdapter::nativeFinished(const std::shared_ptr<IOSSnapshotNativeOperation>& operation,const QString& status,const QString& error) {
    if(!guiThread() || _operation!=operation) { return; }
    const auto ticket=operation->state.ticket;
    _operation.reset();_error=error;emit changed();emit completed(ticket,status,error);
}
} // namespace overte::ios
namespace {
void registerIOSSnapshotAdapter() { qmlRegisterType<overte::ios::IOSSnapshotAdapter>("Overte.iOS",1,0,"IOSSnapshotAdapter"); }
Q_COREAPP_STARTUP_FUNCTION(registerIOSSnapshotAdapter)
}
