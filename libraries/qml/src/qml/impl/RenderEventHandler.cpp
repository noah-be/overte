//
//  Created by Bradley Austin Davis on 2018-01-04
//  Copyright 2013-2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "RenderEventHandler.h"

#ifndef DISABLE_QML

#include <gl/Config.h>
#include <gl/QOpenGLContextWrapper.h>
#include <gl/GLHelpers.h>

#include <QtQuick/QQuickWindow>
#include <QtCore/QMetaObject>
#include <QtCore/QPointer>

#include <shared/NsightHelpers.h>
#include "Profiling.h"
#include "SharedObject.h"
#include "TextureCache.h"
#include "RenderControl.h"
#include "../Logging.h"

using namespace hifi::qml::impl;

bool RenderEventHandler::event(QEvent* e) {
    switch (static_cast<OffscreenEvent::Type>(e->type())) {
        case OffscreenEvent::Render:
            onRender();
            return true;

        case OffscreenEvent::RenderSync:
            onRenderSync();
            return true;

        case OffscreenEvent::Initialize:
            onInitalize();
            return true;

        case OffscreenEvent::Quit:
            onQuit();
            return true;

        default:
            break;
    }
    return QObject::event(e);
}

RenderEventHandler::RenderEventHandler(SharedObject* shared, QThread* targetThread) :
        _shared(shared) {
    // Create the GL canvas in the same thread as the share canvas
    if (!_canvas.create(SharedObject::getSharedContext())) {
        qFatal("Unable to create new offscreen GL context");
    }

    _canvas.moveToThreadWithContext(targetThread);
    moveToThread(targetThread);
}

void RenderEventHandler::onInitalize() {
    if (_shared->isQuit()) {
        return;
    }

    _canvas.setThreadContext();
    if (!_canvas.makeCurrent()) {
        qFatal("Unable to make QML rendering context current on render thread");
    }
    _shared->initializeRenderControl(_canvas.getContext());
    _initialized = true;
}

void RenderEventHandler::resize() {
    PROFILE_RANGE(render_qml_gl, __FUNCTION__);
    auto targetSize = _shared->getSize();
    if (_currentSize != targetSize) {
        auto& offscreenTextures = SharedObject::getTextureCache();
        // Release hold on the textures of the old size
        if (_currentSize != QSize()) {
            _shared->releaseTextureAndFence();
            offscreenTextures.releaseSize(_currentSize, _shared->getGenerateMips());
        }

        _currentSize = targetSize;

        // Acquire the new texture size
        if (_currentSize != QSize()) {
            qCDebug(qmlLogging) << "Upating offscreen textures to " << _currentSize.width() << " x " << _currentSize.height();
            offscreenTextures.acquireSize(_currentSize, _shared->getGenerateMips());
            if (_depthStencil) {
                glDeleteRenderbuffers(1, &_depthStencil);
                _depthStencil = 0;
            }
            glGenRenderbuffers(1, &_depthStencil);
            glBindRenderbuffer(GL_RENDERBUFFER, _depthStencil);
            glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH_COMPONENT16, _currentSize.width(), _currentSize.height());
            if (!_fbo) {
                glGenFramebuffers(1, &_fbo);
            }
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, _fbo);
            glFramebufferRenderbuffer(GL_DRAW_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, _depthStencil);
            glViewport(0, 0, _currentSize.width(), _currentSize.height());
            glScissor(0, 0, _currentSize.width(), _currentSize.height());
            glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
        }
    }
}

void RenderEventHandler::onRender() {
    qmlRender(false);
}

void RenderEventHandler::onRenderSync() {
    qmlRender(true);
}

void RenderEventHandler::qmlRender(bool sceneGraphSync) {
    if (_shared->isQuit()) {
        return;
    }

    if (_canvas.getContext() != QOpenGLContextWrapper::currentContext()) {
        qFatal("QML rendering context not current on render thread");
    }

    PROFILE_RANGE(render_qml_gl, __FUNCTION__);

    // Never wait for macOS' global GL serialization lock from a QML render
    // thread. Apple's software renderer can hold it for minutes while it
    // compiles a production shader. A synchronous scene-graph event would
    // otherwise leave the GUI thread asleep in SharedObject::onRender(),
    // preventing network replies and downloaded assets from being delivered.
    // If the lock is busy, release the GUI synchronization waiter (if any) and
    // queue the exact same request for a later event-loop turn.
    if (!gl::globalTryLock()) {
        if (sceneGraphSync) {
            _shared->wakeRenderSyncWaiter();
        }
        QPointer<SharedObject> shared(_shared);
        QMetaObject::invokeMethod(_shared, [shared, sceneGraphSync] {
            if (!shared) {
                return;
            }
            if (sceneGraphSync) {
                shared->requestRenderSync();
            } else {
                shared->requestRender();
            }
        }, Qt::QueuedConnection);
        return;
    }

    // The GUI thread is blocked only for QQuickRenderControl::sync(). The GL
    // lock is already held, so preRender() cannot wake it into another
    // minutes-long lock wait.
    if (!_shared->preRender(sceneGraphSync)) {
        gl::globalRelease();
        return;
    }

    resize();

    if (_currentSize != QSize()) {
        PROFILE_RANGE(render_qml_gl, "render");
        const bool generateMips = _shared->getGenerateMips();
        GLuint texture = SharedObject::getTextureCache().acquireTexture(_currentSize, generateMips);
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, _fbo);
        glFramebufferTexture2D(
            GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
        if (nsightActive()) {
            glClearColor(0.0f, 0.0f, 0.0f, 0.0f);
            glClear(GL_COLOR_BUFFER_BIT);
        } else {
            glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
            _shared->setRenderTarget(_fbo, _currentSize);

            // workaround for https://highfidelity.atlassian.net/browse/BUGZ-1119
            {
                // Serialize QML rendering because of a crash caused by Qt bug 
                // https://bugreports.qt.io/browse/QTBUG-77469
                static std::mutex qmlRenderMutex;
                std::unique_lock<std::mutex> qmlRenderLock{ qmlRenderMutex };
                _shared->_renderControl->render();
            }
        }
        _shared->_lastRenderTime = usecTimestampNow();
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0);
        if (generateMips) {
            glBindTexture(GL_TEXTURE_2D, texture);
            glGenerateMipmap(GL_TEXTURE_2D);
            glBindTexture(GL_TEXTURE_2D, 0);
        }
        auto fence = glFenceSync(GL_SYNC_GPU_COMMANDS_COMPLETE, 0);
        // Fence will be used in another thread / context, so a flush is required
        glFlush();
        _shared->updateTextureAndFence({ texture, fence });
        _shared->_quickWindow->resetOpenGLState();
    }
    gl::globalRelease();
}

void RenderEventHandler::onQuit() {
    if (_initialized) {
        if (_canvas.getContext() != QOpenGLContextWrapper::currentContext()) {
            qFatal("QML rendering context not current on render thread");
        }

        if (_depthStencil) {
            glDeleteRenderbuffers(1, &_depthStencil);
            _depthStencil = 0;
        }

        if (_fbo) {
            glDeleteFramebuffers(1, &_fbo);
            _fbo = 0;
        }

        _shared->shutdownRendering(_currentSize);
        _canvas.doneCurrent();
    }
    _canvas.moveToThreadWithContext(qApp->thread());
    moveToThread(qApp->thread());
    QThread::currentThread()->quit();
}

#endif
