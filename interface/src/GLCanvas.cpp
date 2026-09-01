//
//  GLCanvas.cpp
//  interface/src
//
//  Created by Stephen Birarda on 8/14/13.
//  Copyright 2013 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "GLCanvas.h"

#include "Application.h"
#include <DependencyManager.h>
#include <OffscreenUi.h>
#include <QInputMethodEvent>
#include <QQuickItem>
#include <QQuickWindow>

QVariant GLCanvas::inputMethodQuery(Qt::InputMethodQuery query) const {
#if defined(ANDROID_APP_PHONE_INTERFACE)
    auto offscreenUi = DependencyManager::get<OffscreenUi>();
    auto offscreenWindow = offscreenUi ? offscreenUi->getWindow() : nullptr;
    auto focusItem = offscreenWindow ? offscreenWindow->activeFocusItem() : nullptr;
    if (focusItem) {
        QInputMethodQueryEvent queryEvent(query);
        QCoreApplication::sendEvent(focusItem, &queryEvent);
        QVariant value = queryEvent.value(query);
        if (query == Qt::ImCursorRectangle || query == Qt::ImAnchorRectangle) {
            QRectF rectangle = focusItem->mapRectToScene(value.toRectF());
            const QSize sourceSize = offscreenWindow->size();
            if (sourceSize.width() > 0 && sourceSize.height() > 0) {
                rectangle.setX(rectangle.x() * width() / sourceSize.width());
                rectangle.setY(rectangle.y() * height() / sourceSize.height());
                rectangle.setWidth(rectangle.width() * width() / sourceSize.width());
                rectangle.setHeight(rectangle.height() * height() / sourceSize.height());
                return rectangle;
            }
        } else if (value.isValid()) {
            return value;
        }
    }
#endif
    return GLWidget::inputMethodQuery(query);
}

bool GLCanvas::event(QEvent* event) {
    if (QEvent::Paint == event->type() && qApp->isAboutToQuit()) {
        return true;
    }
    return GLWidget::event(event);
}
