//
// ResourceImageItem.h
//
// Created by David Kelly and Howard Stearns on 2017/06/08
// Copyright 2017 High Fidelity, Inc.

// Distributed under the Apache License, Version 2.0
// See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#pragma once
#ifndef hifi_ResourceImageItem_h
#define hifi_ResourceImageItem_h

#include "Application.h"

#include <QtGlobal>
#if defined(Q_OS_IOS)
#include <QQuickItem>
using ResourceImageItemBase = QQuickItem;
#else
#include <gl/Config.h>
#include <QQuickFramebufferObject>
#include <QQuickWindow>
#include <QTimer>
using ResourceImageItemBase = QQuickFramebufferObject;
#endif

#include <TextureCache.h>

#if !defined(Q_OS_IOS)
class QOpenGLFramebufferObject;
class QOpenGLShaderProgram;

class ResourceImageItemRenderer : public QObject, public QQuickFramebufferObject::Renderer {
    Q_OBJECT
public:
    ResourceImageItemRenderer();
    QOpenGLFramebufferObject* createFramebufferObject(const QSize& size) override;
    void synchronize(QQuickFramebufferObject* item) override;
    void render() override;
private:
    bool _ready{ false };
    QString _url;
    bool _visible{ false };

    NetworkTexturePointer _networkTexture;
    QQuickWindow* _window{ nullptr };
    QMutex _fboMutex;
    uint32_t _vao{ 0 };
    QOpenGLFramebufferObject* _copyFbo { nullptr };
    QOpenGLShaderProgram* _shader{ nullptr };
    GLsync _fenceSync { 0 };
    QTimer _updateTimer;
public slots:
    void onUpdateTimer();
};
#endif

class ResourceImageItem : public ResourceImageItemBase {
    Q_OBJECT
    Q_PROPERTY(QString url READ getUrl WRITE setUrl)
    Q_PROPERTY(bool ready READ getReady WRITE setReady)
public:
    ResourceImageItem();
    QString getUrl() const { return m_url; }
    void setUrl(const QString& url);
    bool getReady() const { return m_ready; }
    void setReady(bool ready);
#if !defined(Q_OS_IOS)
    QQuickFramebufferObject::Renderer* createRenderer() const override { return new ResourceImageItemRenderer; }
#endif

private:
    QString m_url;
    bool m_ready { false };

};

#endif // hifi_ResourceImageItem_h
