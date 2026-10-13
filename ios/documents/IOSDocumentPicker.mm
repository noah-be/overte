// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "DocumentImport.h"
#include <FileDialogHelper.h>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QThread>
#include <QTimer>
#include <memory>
#include <mutex>
#import <UIKit/UIKit.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

using overte::ios::DocumentImport;
@class OverteDocumentPickerDelegate;
namespace {
struct Operation {
    Operation(QString id,bool multiple,bool tree,FileDialogHelper::DocumentSelection completion,QString root) :
        id(std::move(id)),multiple(multiple),tree(tree),completion(std::move(completion)),files(std::move(root)) {}
    const QString id;
    const bool multiple;
    const bool tree;
    FileDialogHelper::DocumentSelection completion;
    DocumentImport files;
    std::atomic<bool> copying {false},finished {false};
    std::mutex coordinatorMutex;
    __strong NSFileCoordinator* coordinator {nil};
    // Both native objects are accessed exclusively on UIKit's main queue.
    __strong UIDocumentPickerViewController* picker {nil};
    __strong OverteDocumentPickerDelegate* delegate {nil};
};
// Read/written exclusively on the Qt application owner. The shared operation
// itself owns atomics and immutable request authority across native queues.
std::shared_ptr<Operation> active;
NSString* nativeString(const QString& value) {
    const auto bytes=value.toUtf8();
    return [[NSString alloc] initWithBytes:bytes.constData() length:bytes.size() encoding:NSUTF8StringEncoding];
}
QString string(NSString* value) { return value ? QString::fromUtf8(value.UTF8String) : QString(); }
UIViewController* presenter() {
    for(UIScene* scene in UIApplication.sharedApplication.connectedScenes) {
        if(scene.activationState!=UISceneActivationStateForegroundActive || ![scene isKindOfClass:UIWindowScene.class])continue;
        for(UIWindow* window in ((UIWindowScene*)scene).windows) {
            if(!window.isKeyWindow || window.hidden)continue;
            auto controller=window.rootViewController;
            while(controller.presentedViewController && !controller.presentedViewController.isBeingDismissed)controller=controller.presentedViewController;
            if(controller.view.window && !controller.isBeingDismissed)return controller;
        }
    }
    return nil;
}
// Escaping Objective-C blocks retain value captures, not C++ reference
// parameters. Keep a copied shared owner until native dismissal returns.
void finish(std::shared_ptr<Operation> operation,QList<QUrl> urls={},QString error={}) {
    if(operation->finished.exchange(true))return;
    dispatch_async(dispatch_get_main_queue(),^{
        auto returnToOwner=^{
            operation->picker=nil;operation->delegate=nil;
            if(auto application=QCoreApplication::instance()) {
                QMetaObject::invokeMethod(application,[operation,urls,error] {
                    if(active!=operation)return;
                    active.reset();
                    // FileDialogHelper's QPointer inspection happens only here
                    // on its Qt owner. Its request ID also rejects stale returns.
                    operation->completion(urls,error);
                },Qt::QueuedConnection);
            }
        };
        auto picker=operation->picker;
        if(picker.isBeingPresented && picker.transitionCoordinator) {
            [picker.transitionCoordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context) {
                (void)context;
                [picker dismissViewControllerAnimated:NO completion:returnToOwner];
            }];
        } else if(picker.presentingViewController) {
            [picker dismissViewControllerAnimated:NO completion:returnToOwner];
        } else { returnToOwner(); }
    });
}
void cancelCoordination(const std::shared_ptr<Operation>& operation) {
    if(operation->finished.load())return;
    NSFileCoordinator* coordinator=nil;
    { std::lock_guard<std::mutex> guard(operation->coordinatorMutex);coordinator=operation->coordinator; }
    [coordinator cancel];
    // Cover cancellation racing the instant just before a coordination call
    // starts. Never release the copy lease or claim rollback while it runs.
    if(operation->copying.load()) {
        std::weak_ptr<Operation> weak=operation;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,NSEC_PER_SEC/4),dispatch_get_main_queue(),^{
            if(auto current=weak.lock())cancelCoordination(current);
        });
    }
}
void cancel(const QString& id) {
    if(!active || active->id!=id)return;
    auto operation=active;
    operation->files.cancel();
    cancelCoordination(operation);
    dispatch_async(dispatch_get_main_queue(),^{
        // A coordinated provider copy is allowed to unwind before releasing
        // the chooser lease; partial selections are never published.
        if(!operation->copying.load())finish(operation);
    });
}
void importDocuments(std::shared_ptr<Operation> operation,NSArray<NSURL*>* urls) {
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
        @autoreleasepool {
            QString error;
            if(urls.count>DocumentImport::MAX_COUNT || (!operation->multiple && urls.count>1)) {
                error="The document provider returned too many files for this selection.";
            }
            for(NSURL* url in urls) {
                if(!error.isEmpty() || operation->files.cancelled())break;
                if(!url.isFileURL) { error="The document provider did not return a local readable file.";break; }
                const BOOL scoped=[url startAccessingSecurityScopedResource];
                NSFileCoordinator* coordinator=[[NSFileCoordinator alloc] initWithFilePresenter:nil];
                { std::lock_guard<std::mutex> guard(operation->coordinatorMutex);operation->coordinator=coordinator; }
                NSError* coordinationError=nil;
                __block QString copyError;
                __block bool copied=false;
                auto copyAccessor=^(NSURL* readable) {
                    NSNumber* directory=nil;
                    NSNumber* regular=nil;
                    NSNumber* symbolic=nil;
                    NSNumber* alias=nil;
                    NSString* name=nil;
                    NSError* resourceError=nil;
                    if(![readable getResourceValue:&regular forKey:NSURLIsRegularFileKey error:&resourceError] ||
                        ![readable getResourceValue:&directory forKey:NSURLIsDirectoryKey error:&resourceError] ||
                        (operation->tree ? !directory.boolValue : !regular.boolValue) ||
                        ![readable getResourceValue:&symbolic forKey:NSURLIsSymbolicLinkKey error:&resourceError] || symbolic.boolValue ||
                        ![readable getResourceValue:&alias forKey:NSURLIsAliasFileKey error:&resourceError] || alias.boolValue ||
                        ![url getResourceValue:&name forKey:NSURLNameKey error:&resourceError]) {
                        copyError=operation->tree ? "Select a readable folder rather than a file alias." :
                            "Select readable files rather than folders or file aliases.";return;
                    }
                    if(operation->tree) {
                        copied=operation->files.copyDirectory(string(readable.path),string(name),copyError,
                            [](const QString& path,QString& error) {
                                NSURL* child=[NSURL fileURLWithPath:nativeString(path)];
                                NSNumber* alias=nil;
                                NSError* resourceError=nil;
                                if(![child getResourceValue:&alias forKey:NSURLIsAliasFileKey error:&resourceError] || alias.boolValue) {
                                    error="The selected folder contains an unreadable item or file alias.";return false;
                                }
                                return true;
                            },[operation,coordinator](const QString& path,const std::function<bool(QIODevice&)>& consume,QString& error) {
                                if(operation->files.cancelled())return false;
                                NSError* readError=nil;
                                __block QString copyError;
                                __block bool copied=false;
                                // This synchronous nested read materializes the
                                // actual child through its provider before QFile.
                                [coordinator coordinateReadingItemAtURL:[NSURL fileURLWithPath:nativeString(path)]
                                    options:NSFileCoordinatorReadingWithoutChanges error:&readError byAccessor:^(NSURL* child) {
                                        const QFileInfo source(string(child.path));
                                        NSNumber* alias=nil;
                                        NSError* resourceError=nil;
                                        if(source.isSymLink() || !source.isFile() || source.canonicalFilePath()!=path ||
                                            ![child getResourceValue:&alias forKey:NSURLIsAliasFileKey error:&resourceError] || alias.boolValue) {
                                            copyError="A folder file changed or became an unsafe alias.";return;
                                        }
                                        QFile input(source.canonicalFilePath());
                                        if(!input.open(QIODevice::ReadOnly)) { copyError="A selected folder file could not be read.";return; }
                                        copied=consume(input);
                                    }];
                                if(!copied && error.isEmpty() && !operation->files.cancelled()) {
                                    error=copyError.isEmpty() ? "The document provider could not supply a complete folder file." : copyError;
                                }
                                return !readError && copied;
                            });
                        return;
                    }
                    QFile input(string(readable.path));
                    if(!input.open(QIODevice::ReadOnly)) { copyError="The selected document could not be read.";return; }
                    copied=operation->files.copy(input,string(name),copyError);
                };
                if(!operation->files.cancelled()) {
                    if(operation->tree) {
                        // Batch the top-level directory, then coordinate its
                        // traversal and every child read with the same owner.
                        // Apple's documented completion releases all presenters.
                        [coordinator prepareForReadingItemsAtURLs:@[url] options:0 writingItemsAtURLs:@[] options:0
                            error:&coordinationError byAccessor:^(void (^completed)(void)) {
                                NSError* directoryError=nil;
                                if(!operation->files.cancelled()) {
                                    [coordinator coordinateReadingItemAtURL:url options:NSFileCoordinatorReadingWithoutChanges
                                        error:&directoryError byAccessor:copyAccessor];
                                }
                                if(directoryError) {
                                    copied=false;
                                    if(copyError.isEmpty())copyError="The selected folder could not be coordinated for reading.";
                                }
                                completed();
                            }];
                    } else {
                        [coordinator coordinateReadingItemAtURL:url options:NSFileCoordinatorReadingWithoutChanges
                            error:&coordinationError byAccessor:copyAccessor];
                    }
                }
                { std::lock_guard<std::mutex> guard(operation->coordinatorMutex);operation->coordinator=nil; }
                if(scoped)[url stopAccessingSecurityScopedResource];
                if(coordinationError || !copied) {
                    if(!operation->files.cancelled())error=copyError.isEmpty() ? "The document provider could not supply this file." : copyError;
                    break;
                }
            }
            if(error.isEmpty() && !operation->files.urls().isEmpty() && operation->files.commit()) {
                finish(operation,operation->files.urls());
            } else {
                operation->files.rollback();
                finish(operation,{},operation->files.cancelled() ? QString() : error);
            }
        }
    });
}
} // namespace

@interface OverteDocumentPickerDelegate : NSObject<UIDocumentPickerDelegate,UIAdaptivePresentationControllerDelegate> {
@public
    std::shared_ptr<Operation> operation;
}
@end
@implementation OverteDocumentPickerDelegate
- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
    (void)controller;
    if(operation->finished.load() || operation->copying.exchange(true))return;
    if(operation->files.cancelled()) { finish(operation);return; }
    importDocuments(operation,[urls copy]);
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {
    (void)controller;
    operation->files.cancel();
    cancelCoordination(operation);
    if(!operation->copying.load())finish(operation);
}
- (void)presentationControllerDidDismiss:(UIPresentationController*)controller {
    (void)controller;
    // The successful selection also dismisses the picker. Its provider copy
    // owns completion from then on; a dismissal must not cancel that copy.
    if(!operation->copying.load()) { operation->files.cancel();finish(operation); }
}
@end

namespace {
bool openPicker(const QString& id,QString caption,QString filter,bool multiple,FileDialogHelper::DocumentSelection completed,bool tree) {
    if(!qGuiApp || QThread::currentThread()!=qGuiApp->thread() || active || id.isEmpty())return false;
    const auto data=QStandardPaths::writableLocation(QStandardPaths::AppDataLocation);
    if(data.isEmpty())return false;
    auto operation=std::make_shared<Operation>(id,multiple,tree,std::move(completed),QDir(data).filePath("ImportedDocuments"));
    active=operation;
    dispatch_async(dispatch_get_main_queue(),^{
        if(operation->files.cancelled()) { finish(operation);return; }
        auto controller=presenter();
        if(!controller) { finish(operation,{},"Open the file picker while Overte is in the foreground.");return; }
        NSMutableArray<UTType*>* types=[NSMutableArray array];
        if(tree)[types addObject:UTTypeFolder];
        const QRegularExpression extensions(QStringLiteral("\\*\\.([A-Za-z0-9_-]+)"));
        auto matches=extensions.globalMatch(filter);
        while(!tree && matches.hasNext()) {
            auto type=[UTType typeWithFilenameExtension:nativeString(matches.next().captured(1))];
            if(type && ![types containsObject:type])[types addObject:type];
        }
        // Unknown types remain selectable; do not substitute a fake QPA flow.
        const QRegularExpression allFiles(QStringLiteral("(?:^|[\\s(])\\*(?:[\\s)]|$)"));
        if(!tree && (types.count==0 || filter.contains("*.*") || allFiles.match(filter).hasMatch()))[types addObject:UTTypeItem];
        auto picker=[[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types asCopy:NO];
        auto delegate=[[OverteDocumentPickerDelegate alloc] init];
        delegate->operation=operation;
        operation->picker=picker;operation->delegate=delegate;
        picker.delegate=delegate;picker.allowsMultipleSelection=multiple;
        picker.title=nativeString(caption);
        [controller presentViewController:picker animated:YES completion:nil];
        picker.presentationController.delegate=delegate;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{
            if(!operation->finished.load() && !operation->copying.load() && !picker.presentingViewController && !picker.isBeingPresented) {
                finish(operation,{},"The system file picker could not open.");
            }
        });
    });
    return true;
}
bool open(const QString& id,QString caption,QString filter,bool multiple,FileDialogHelper::DocumentSelection completed) {
    return openPicker(id,std::move(caption),std::move(filter),multiple,std::move(completed),false);
}
bool openTree(const QString& id,const QString& caption,FileDialogHelper::DocumentSelection completed) {
    return openPicker(id,caption,{},false,std::move(completed),true);
}
void install() {
    static_assert(DocumentImport::MAX_COUNT==FileDialogHelper::MAX_DOCUMENT_COUNT);
    static_assert(DocumentImport::MAX_FILE==FileDialogHelper::MAX_DOCUMENT_BYTES);
    static_assert(DocumentImport::MAX_TOTAL==FileDialogHelper::MAX_DOCUMENT_TOTAL_BYTES);
    static_assert(DocumentImport::MAX_ENTRIES==FileDialogHelper::MAX_DOCUMENT_ENTRIES);
    static_assert(DocumentImport::MAX_DEPTH==FileDialogHelper::MAX_DOCUMENT_DEPTH);
    FileDialogHelper::setDocumentPickerOperator(open,cancel);
    FileDialogHelper::setDocumentTreePickerOperator(openTree,cancel);
    // Startup hooks can run during application construction. Attach GUI state
    // only once its event loop is ready, without invoking UIKit in a Qt ctor.
    QTimer::singleShot(0,QCoreApplication::instance(),[] {
        QObject::connect(qGuiApp,&QGuiApplication::applicationStateChanged,qGuiApp,[](Qt::ApplicationState state) {
            if((state==Qt::ApplicationHidden || state==Qt::ApplicationSuspended) && active)cancel(active->id);
        });
        QObject::connect(qGuiApp,&QCoreApplication::aboutToQuit,qGuiApp,[] {
            if(active)cancel(active->id);
        });
    });
}
Q_COREAPP_STARTUP_FUNCTION(install)
} // namespace
