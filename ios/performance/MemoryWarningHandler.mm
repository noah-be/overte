// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "MemoryWarningHandler.h"
#include <QObject>
#include <QPointer>
#import <UIKit/UIKit.h>
namespace overte::ios {
void installMemoryWarningHandler(QObject* lifetime, std::function<void()> callback) {
    QPointer<QObject> context(lifetime);
    id observer = [NSNotificationCenter.defaultCenter
        addObserverForName:UIApplicationDidReceiveMemoryWarningNotification object:nil
        queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification*) {
            if (context) {
                QMetaObject::invokeMethod(context.data(), [context, callback] {
                    if (context) { callback(); }
                }, Qt::QueuedConnection);
            }
        }];
    QObject::connect(lifetime, &QObject::destroyed, [observer] {
        [NSNotificationCenter.defaultCenter removeObserver:observer];
    });
}
}
