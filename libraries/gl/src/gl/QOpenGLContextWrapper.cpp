//
//  QOpenGLContextWrapper.cpp
//
//
//  Created by Clement on 12/4/15.
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "QOpenGLContextWrapper.h"

#include <QOpenGLContext>

#ifdef Q_OS_WIN
#include <QtPlatformHeaders/QWGLNativeContext>
#endif

QOpenGLContextWrapper::Pointer QOpenGLContextWrapper::currentContextWrapper() {
    return std::make_shared<QOpenGLContextWrapper>(QOpenGLContext::currentContext());
}


QOpenGLContextWrapper::NativeContextPointer QOpenGLContextWrapper::getNativeContext() const {
    QOpenGLContextWrapper::NativeContextPointer result;
#if defined(Q_OS_IOS)
    // Native context extraction is only consumed by the Windows WGL context path.
    // Qt 6 no longer exposes QOpenGLContext::nativeHandle(), and iOS must not
    // manufacture a desktop GL handle for the Vulkan compatibility context.
    return result;
#else
    auto nativeHandle = _context->nativeHandle();
    if (nativeHandle.canConvert<QGLNativeContext>()) {
        result = std::make_shared<QGLNativeContext>();
        *result = nativeHandle.value<QGLNativeContext>();
    }
    return result;
#endif
}


uint32_t QOpenGLContextWrapper::currentContextVersion() {
    QOpenGLContext* context = QOpenGLContext::currentContext();
    if (!context) {
        return 0;
    }
    auto format = context->format();
    auto version = (format.majorVersion() << 8) + format.minorVersion();
    return version;
}


QOpenGLContext* QOpenGLContextWrapper::currentContext() {
    return QOpenGLContext::currentContext();
}

QOpenGLContextWrapper::QOpenGLContextWrapper() :
    _ownContext(true), _context(new QOpenGLContext) { }

QOpenGLContextWrapper::QOpenGLContextWrapper(QOpenGLContext* context) :
    _context(context) { }

QOpenGLContextWrapper::~QOpenGLContextWrapper() {
    if (_ownContext) {
        delete _context;
        _context = nullptr;
    }
}

void QOpenGLContextWrapper::setFormat(const QSurfaceFormat& format) {
    _context->setFormat(format);
}

bool QOpenGLContextWrapper::create() {
    return _context->create();
}

void QOpenGLContextWrapper::swapBuffers(QSurface* surface) {
    _context->swapBuffers(surface);
}

bool QOpenGLContextWrapper::makeCurrent(QSurface* surface) {
    return _context->makeCurrent(surface);
}

void QOpenGLContextWrapper::doneCurrent() {
    _context->doneCurrent();
}

void QOpenGLContextWrapper::setShareContext(QOpenGLContext* otherContext) {
    _context->setShareContext(otherContext);
}

bool isCurrentContext(QOpenGLContext* context) {
    return QOpenGLContext::currentContext() == context;
}

void QOpenGLContextWrapper::moveToThread(QThread* thread) {
    _context->moveToThread(thread);
}
