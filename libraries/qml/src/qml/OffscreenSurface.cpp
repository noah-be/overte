//
//  Created by Bradley Austin Davis on 2015-05-13
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "OffscreenSurface.h"

#include <unordered_set>
#include <unordered_map>

#include <QtCore/QThread>
#include <QtCore/QPointer>
#include <QtCore/QTimer>
#if defined(Q_OS_IOS)
#include <QtCore/QDir>
#include <QtCore/QFileInfo>
#include <QtCore/QStandardPaths>
#endif
#include <QtQml/QtQml>
#include <QtQml/QQmlEngine>
#include <QtQml/QQmlComponent>
#include <QtQml/QQmlFileSelector>
#include <QtGui/QInputMethodQueryEvent>
#include <QtQuick/QQuickItem>
#include <QtQuick/QQuickWindow>
#include <QtQuick/QQuickRenderControl>

#include <GLMHelpers.h>

#include <shared/ReadWriteLockable.h>
#if defined(Q_OS_IOS)
#include <shared/IOSRuntimeLogging.h>
#endif
#include <NetworkingConstants.h>
#include <MetaverseAPI.h>

#include "Logging.h"
#include "impl/SharedObject.h"
#include "impl/TextureCache.h"

#include "Profile.h"

using namespace hifi::qml;
using namespace hifi::qml::impl;

QmlUrlValidator OffscreenSurface::validator = [](const QUrl& url) -> bool {
    if (url.isRelative()) {
        return true;
    }

    if (url.isLocalFile()) {
        return true;
    }

    if (url.scheme() == URL_SCHEME_QRC) {
        return true;
    }

    // By default, only allow local QML, either from the local filesystem or baked into the QRC
    return false;
};

static uvec2 clampSize(const uvec2& size, uint32_t maxDimension) {
    return glm::clamp(size, glm::uvec2(1), glm::uvec2(maxDimension));
}

static QSize clampSize(const QSize& qsize, uint32_t maxDimension) {
    return fromGlm(clampSize(toGlm(qsize), maxDimension));
}

#if defined(Q_OS_IOS)
static QUrl resolveIOSQmlOverride(const QUrl& source) {
    if (source.scheme() != URL_SCHEME_QRC) {
        return source;
    }

    QDir overrideRoot(QDir(QStandardPaths::writableLocation(QStandardPaths::DocumentsLocation))
        .filePath(QStringLiteral("OverteQmlOverrides")));
    const QFileInfo enableFile(overrideRoot.filePath(QStringLiteral(".enabled")));
    if (!overrideRoot.exists() || !enableFile.isFile() || enableFile.isSymLink()) {
        return source;
    }

    QString relativePath = source.path();
    while (relativePath.startsWith(QLatin1Char('/'))) {
        relativePath.remove(0, 1);
    }
    const QFileInfo candidate(overrideRoot.filePath(relativePath));
    if (!candidate.isFile() || candidate.isSymLink()) {
        return source;
    }

    const QString canonicalRoot = QFileInfo(overrideRoot.absolutePath()).canonicalFilePath();
    const QString canonicalCandidate = candidate.canonicalFilePath();
    if (canonicalRoot.isEmpty() || canonicalCandidate.isEmpty() ||
            !canonicalCandidate.startsWith(canonicalRoot + QDir::separator())) {
        logIOSRuntimeMarker(
            "OVERTE_IOS_QML_OVERRIDE_GATE stage=rejected",
            "requested=", source,
            "candidate=", candidate.absoluteFilePath());
        return source;
    }

    const QUrl resolved = QUrl::fromLocalFile(canonicalCandidate);
    logIOSRuntimeMarker(
        "OVERTE_IOS_QML_OVERRIDE_GATE stage=active",
        "requested=", source,
        "resolved=", resolved);
    return resolved;
}

static void logIOSQmlErrors(const char* stage, const QList<QQmlError>& errors) {
    for (const auto& error : errors) {
        logIOSRuntimeMarker(
            QStringLiteral("OVERTE_IOS_DYNAMIC_QML_GATE stage=%1")
                .arg(QString::fromUtf8(stage)),
            "url=", error.url(),
            "line=", error.line(),
            "column=", error.column(),
            "description=", error.description());
    }
}

static void logIOSQmlItemState(const char* stage, const QUrl& url,
                               QQuickItem* item, bool completeBeforeCallback) {
    if (!item) {
        logIOSRuntimeMarker(
            QStringLiteral("OVERTE_IOS_DYNAMIC_QML_GATE stage=%1")
                .arg(QString::fromUtf8(stage)),
            "url=", url,
            "item=<null>",
            "complete_before_callback=", completeBeforeCallback);
        return;
    }

    const auto descendants = item->findChildren<QQuickItem*>();
    int visibleDescendants { 0 };
    int positiveSizeDescendants { 0 };
    int contentDescendants { 0 };
    for (const auto* descendant : descendants) {
        visibleDescendants += descendant->isVisible() ? 1 : 0;
        positiveSizeDescendants += descendant->width() > 0.0 && descendant->height() > 0.0 ? 1 : 0;
        contentDescendants += descendant->flags().testFlag(QQuickItem::ItemHasContents) ? 1 : 0;
    }

    const QRectF sceneBounds = item->mapRectToScene(item->boundingRect());
    logIOSRuntimeMarker(
        QStringLiteral("OVERTE_IOS_DYNAMIC_QML_GATE stage=%1")
            .arg(QString::fromUtf8(stage)),
        "url=", url,
        "class=", item->metaObject()->className(),
        "object=", item->objectName().isEmpty() ? QStringLiteral("<unnamed>") : item->objectName(),
        "parent=", item->parentItem() && !item->parentItem()->objectName().isEmpty()
            ? item->parentItem()->objectName() : QStringLiteral("<unnamed-or-none>"),
        "size=", QStringLiteral("%1x%2").arg(item->width()).arg(item->height()),
        "position=", QStringLiteral("%1,%2").arg(item->x()).arg(item->y()),
        "scene_bounds=", QStringLiteral("%1,%2,%3x%4")
            .arg(sceneBounds.x()).arg(sceneBounds.y())
            .arg(sceneBounds.width()).arg(sceneBounds.height()),
        "z=", item->z(),
        "opacity=", item->opacity(),
        "visible=", item->isVisible(),
        "enabled=", item->isEnabled(),
        "window=", item->window() != nullptr,
        "direct_children=", item->childItems().size(),
        "descendants=", descendants.size(),
        "visible_descendants=", visibleDescendants,
        "positive_size_descendants=", positiveSizeDescendants,
        "content_descendants=", contentDescendants,
        "complete_before_callback=", completeBeforeCallback);
}
#endif

const QmlContextObjectCallback OffscreenSurface::DEFAULT_CONTEXT_OBJECT_CALLBACK = [](QQmlContext*, QQuickItem*) {};
const QmlContextCallback OffscreenSurface::DEFAULT_CONTEXT_CALLBACK = [](QQmlContext*) {};

QQmlFileSelector* OffscreenSurface::getFileSelector() {
    auto context = getSurfaceContext();
    if (!context) {
        return nullptr;
    }
    auto engine = context->engine();
    if (!engine) {
        return nullptr;
    }

    return QQmlFileSelector::get(engine);
}

void OffscreenSurface::initializeEngine(QQmlEngine* engine) {
    new QQmlFileSelector(engine);
}

using namespace hifi::qml::impl;

size_t OffscreenSurface::getUsedTextureMemory() {
    return SharedObject::getTextureCache().getUsedTextureMemory();
}

bool OffscreenSurface::configureSharedGraphicsContext(const SharedGraphicsContext& context) {
    if (context.backend == SharedGraphicsContext::Backend::Software) {
        SharedObject::setSoftwareRendering();
        return true;
    }
    if (context.backend != SharedGraphicsContext::Backend::OpenGL || !context.handle) {
        return false;
    }

    setSharedContext(static_cast<QOpenGLContext*>(context.handle));
    return true;
}

void OffscreenSurface::setSharedContext(QOpenGLContext* sharedContext) {
    SharedObject::setSharedContext(sharedContext);
}

std::function<void(uint32_t, void*)> OffscreenSurface::getDiscardLambda() {
    return [](uint32_t texture, void* fence) {
        SharedObject::getTextureCache().releaseTexture({ texture, fence });
    };
}

OffscreenSurface::OffscreenSurface()
    : _sharedObject(new impl::SharedObject()) {
}

OffscreenSurface::~OffscreenSurface() {
    _sharedObject->deleteLater();
}

bool OffscreenSurface::fetchTexture(TextureAndFence& textureAndFence) {
    hifi::qml::impl::TextureAndFence typedTextureAndFence;
    bool result = _sharedObject->fetchTexture(typedTextureAndFence);
    textureAndFence = typedTextureAndFence;
    return result;
}

bool OffscreenSurface::fetchImage(QImage& image) {
    return _sharedObject->fetchImage(image);
}

void OffscreenSurface::resize(const QSize& newSize_) {
    const uint32_t MAX_OFFSCREEN_DIMENSION = 4096;
    _sharedObject->setSize(clampSize(newSize_, MAX_OFFSCREEN_DIMENSION));
}

QQuickItem* OffscreenSurface::getRootItem() {
    return _sharedObject->getRootItem();
}

void OffscreenSurface::clearCache() {
    _sharedObject->getContext()->engine()->clearComponentCache();
}

QPointF OffscreenSurface::mapToVirtualScreen(const QPointF& originalPoint) {
    return _mouseTranslator(originalPoint);
}

///////////////////////////////////////////////////////
//
// Event handling customization
//

bool OffscreenSurface::filterEnabled(QObject* originalDestination, QEvent* event) const {
    if (!_sharedObject || !_sharedObject->getWindow() || _sharedObject->getWindow() == originalDestination) {
        return false;
    }
    // Only intercept events while we're in an active state
    if (_sharedObject->isPaused()) {
        return false;
    }
    return true;
}

bool OffscreenSurface::eventFilter(QObject* originalDestination, QEvent* event) {
    if (!filterEnabled(originalDestination, event)) {
        return false;
    }
#ifdef DEBUG
    // Don't intercept our own events, or we enter an infinite recursion
    {
        auto rootItem = _sharedObject->getRootItem();
        auto quickWindow = _sharedObject->getWindow();
        QObject* recurseTest = originalDestination;
        while (recurseTest) {
            Q_ASSERT(recurseTest != rootItem && recurseTest != quickWindow);
            recurseTest = recurseTest->parent();
        }
    }
#endif

    switch (event->type()) {
        case QEvent::KeyPress:
        case QEvent::KeyRelease: {
            event->ignore();
            QObject* target = _sharedObject->getWindow();
#if defined(Q_OS_IOS)
            // An offscreen QQuickWindow can own an active text item without
            // becoming UIKit's native focus window. Deliver hardware-keyboard
            // events directly to that item; QQuickWindow otherwise discards
            // them while buttons continue to appear fully interactive.
            if (auto* focusItem = _sharedObject->getWindow()->activeFocusItem()) {
                target = focusItem;
            }
#endif
            const bool delivered = QCoreApplication::sendEvent(target, event);
#if defined(Q_OS_IOS)
            static uint32_t keyTraceCount { 0 };
            const int keyTraceLimit = iosRuntimeDiagnosticInt(
                "offscreenKeyTraceLimit", 32, 0, 1000);
            if (event->type() == QEvent::KeyPress &&
                    keyTraceCount < static_cast<uint32_t>(keyTraceLimit)) {
                ++keyTraceCount;
                const auto* keyEvent = static_cast<QKeyEvent*>(event);
                QInputMethodQueryEvent query(Qt::ImEnabled);
                QCoreApplication::sendEvent(target, &query);
                logIOSRuntimeMarker(
                    "OVERTE_IOS_TOUCH_UI_GATE stage=hardware-key-forwarded",
                    "key=", keyEvent->key(),
                    "text_length=", keyEvent->text().size(),
                    "focus=", target->objectName().isEmpty()
                        ? QStringLiteral("<unnamed>") : target->objectName(),
                    "focus_class=", target->metaObject()->className(),
                    "ime_enabled=", query.value(Qt::ImEnabled).toBool(),
                    "delivered=", delivered,
                    "accepted=", event->isAccepted(),
                    "event_ordinal=", keyTraceCount);
            }
#endif
            if (delivered) {
                return event->isAccepted();
            }
            break;
        }

        case QEvent::Wheel: {
            QWheelEvent* wheelEvent = static_cast<QWheelEvent*>(event);
            QPointF transformedPos = mapToVirtualScreen(wheelEvent->position());


            QWheelEvent mappedEvent(transformedPos, wheelEvent->globalPosition(), wheelEvent->pixelDelta(), wheelEvent->angleDelta(),
                wheelEvent->buttons(), wheelEvent->modifiers(), wheelEvent->phase(),
                wheelEvent->inverted(), wheelEvent->source());

            mappedEvent.ignore();
            if (QCoreApplication::sendEvent(_sharedObject->getWindow(), &mappedEvent)) {
                return mappedEvent.isAccepted();
            }
            break;
        }
        case QEvent::MouseMove: {
            QMouseEvent* mouseEvent = static_cast<QMouseEvent*>(event);
            QPointF transformedPos = mapToVirtualScreen(mouseEvent->localPos());
            QMouseEvent mappedEvent(mouseEvent->type(), transformedPos, mouseEvent->screenPos(), mouseEvent->button(),
                                    mouseEvent->buttons(), mouseEvent->modifiers());
            mappedEvent.ignore();
            if (QCoreApplication::sendEvent(_sharedObject->getWindow(), &mappedEvent)) {
                return mappedEvent.isAccepted();
            }
            break;
        }

#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS)
        case QEvent::TouchBegin:
        case QEvent::TouchUpdate:
        case QEvent::TouchEnd: {
            QTouchEvent *originalEvent = static_cast<QTouchEvent *>(event);
            QEvent::Type fakeMouseEventType = QEvent::None;
            // This legacy window-wide compatibility filter intentionally keeps
            // LeftButton on move.  With a Qt 6-conformant NoButton the full-screen
            // desktop root accepts every world drag before Application can route
            // it to camera look.  iOS tablet/address-bar gestures use the explicit
            // OffscreenUi::handleMobilePointerEvent path instead, where MouseMove
            // correctly has NoButton and buttons() carries LeftButton for Flickable.
            Qt::MouseButton fakeMouseButton = Qt::LeftButton;
            Qt::MouseButtons fakeMouseButtons = Qt::NoButton;
            switch (event->type()) {
                case QEvent::TouchBegin:
                    fakeMouseEventType = QEvent::MouseButtonPress;
                    fakeMouseButtons = Qt::LeftButton;
                    break;
                case QEvent::TouchUpdate:
                    fakeMouseEventType = QEvent::MouseMove;
                    fakeMouseButtons = Qt::LeftButton;
                    break;
                case QEvent::TouchEnd:
                    fakeMouseEventType = QEvent::MouseButtonRelease;
                    fakeMouseButtons = Qt::NoButton;
                    break;
                default:
                    Q_UNREACHABLE();
            }
            // Same case as OffscreenUi.cpp::eventFilter: touch events are always being accepted so we now use mouse events and consider one touch, touchPoints()[0].
            QMouseEvent fakeMouseEvent(fakeMouseEventType, originalEvent->touchPoints()[0].pos(), fakeMouseButton, fakeMouseButtons, Qt::NoModifier);
            fakeMouseEvent.ignore();
            if (QCoreApplication::sendEvent(_sharedObject->getWindow(), &fakeMouseEvent)) {
#if defined(Q_OS_IOS)
                static quint64 touchMoveOrdinal { 0 };
                if (event->type() == QEvent::TouchUpdate && ++touchMoveOrdinal % 30 == 0) {
                    logIOSRuntimeMarker(
                        "OVERTE_IOS_TOUCH_UI_GATE stage=filtered-touch-drag-move",
                        "ordinal=", touchMoveOrdinal,
                        "button=", static_cast<int>(fakeMouseButton),
                        "buttons=", static_cast<int>(fakeMouseButtons),
                        "accepted=", fakeMouseEvent.isAccepted());
                }
#endif
                /*qInfo() << __FUNCTION__ << "sent fake touch event:" << fakeMouseEvent.type()
                        << "_quickWindow handled it... accepted:" << fakeMouseEvent.isAccepted();*/
                return fakeMouseEvent.isAccepted();
            }
            break;
        }
        case QEvent::InputMethod:
        case QEvent::InputMethodQuery: {
            auto window = getWindow();
            if (window && window->activeFocusItem()) {
                event->ignore();
                if (QCoreApplication::sendEvent(window->activeFocusItem(), event)) {
                    bool eventAccepted = event->isAccepted();
                    if (event->type() == QEvent::InputMethodQuery) {
                        QInputMethodQueryEvent *imqEvent = static_cast<QInputMethodQueryEvent *>(event);
#if defined(Q_OS_ANDROID)
                        // This block disables the selection cursor in Android
                        // which appears in the top-left corner of the screen.
                        if (imqEvent->queries() & Qt::ImEnabled) {
                            imqEvent->setValue(Qt::ImEnabled, QVariant(false));
                        }
#endif
                    }
                    return eventAccepted;
                }
                return false;
            }
            break;
        }
#endif
        default:
            break;
    }

    return false;
}

void OffscreenSurface::pause() {
    _sharedObject->pause();
}

void OffscreenSurface::resume() {
    _sharedObject->resume();
}

bool OffscreenSurface::isPaused() const {
    return _sharedObject->isPaused();
}

void OffscreenSurface::setProxyWindow(QWindow* window) {
    _sharedObject->setProxyWindow(window);
}

QObject* OffscreenSurface::getEventHandler() {
    return getWindow();
}

QQuickWindow* OffscreenSurface::getWindow() {
    return _sharedObject->getWindow();
}

QSize OffscreenSurface::size() const {
    return _sharedObject->getSize();
}

QQmlContext* OffscreenSurface::getSurfaceContext() {
    return _sharedObject->getContext();
}

void OffscreenSurface::setMaxFps(uint8_t maxFps) {
    _sharedObject->setMaxFps(maxFps);
}

void OffscreenSurface::setGenerateMips(bool generateMips) {
    _sharedObject->setGenerateMips(generateMips);
}

void OffscreenSurface::load(const QUrl& qmlSource, QQuickItem* parent, const QJSValue& callback) {
    loadFromQml(qmlSource, parent, callback);
}

void OffscreenSurface::loadFromQml(const QUrl& qmlSource, QQuickItem* parent, const QJSValue& callback) {
    loadInternal(qmlSource, false, parent, [callback](QQmlContext* context, QQuickItem* newItem) {
        const QJSValue result = QJSValue(callback).call(
            QJSValueList() << context->engine()->newQObject(newItem));
#if defined(Q_OS_IOS)
        if (result.isError()) {
            logIOSRuntimeMarker(
                "OVERTE_IOS_DYNAMIC_QML_GATE stage=callback-error",
                "message=", result.toString(),
                "stack=", result.property(QStringLiteral("stack")).toString());
        }
#endif
    }, DEFAULT_CONTEXT_CALLBACK,
#if defined(Q_OS_IOS)
    parent && parent->objectName() == QStringLiteral("loader")
#else
    false
#endif
    );
}

void OffscreenSurface::load(const QUrl& qmlSource, bool createNewContext, const QmlContextObjectCallback& callback) {
    loadInternal(qmlSource, createNewContext, nullptr, callback);
}

void OffscreenSurface::loadInNewContext(const QUrl& qmlSource, const QmlContextObjectCallback& callback, const QmlContextCallback& contextCallback) {
    loadInternal(qmlSource, true, nullptr, callback, contextCallback);
}

void OffscreenSurface::load(const QUrl& qmlSource, const QmlContextObjectCallback& callback) {
    load(qmlSource, false, callback);
}

void OffscreenSurface::load(const QString& qmlSourceFile, const QmlContextObjectCallback& callback) {
    return load(QUrl(qmlSourceFile), callback);
}

void OffscreenSurface::loadInternal(const QUrl& qmlSource,
                                    bool createNewContext,
                                    QQuickItem* parent,
                                    const QmlContextObjectCallback& callback,
                                    const QmlContextCallback& contextCallback,
                                    bool completeBeforeCallback) {
    PROFILE_RANGE_EX(app, "OffscreenSurface::loadInternal", 0xffff00ff, 0, { std::make_pair("url", qmlSource.toDisplayString()) });
    if (QThread::currentThread() != thread()) {
        qFatal("Called load on a non-surface thread");
    }

    // For desktop toolbar mode window: stop script when window is closed.
    if (qmlSource.isEmpty()) {
        getSurfaceContext()->engine()->quit();
    }

    if (!validator(qmlSource)) {
        qCWarning(qmlLogging) << "Unauthorized QML URL found" << qmlSource;
        return;
    }

    // Synchronous loading may take a while; restart the deadlock timer
    QMetaObject::invokeMethod(qApp, "updateHeartbeat", Qt::DirectConnection);

    if (!getRootItem()) {
        _sharedObject->create(this);
    }

    QUrl finalQmlSource = qmlSource;
    if ((finalQmlSource.isRelative() && !finalQmlSource.isEmpty()) || finalQmlSource.scheme() == QLatin1String("file")) {
        finalQmlSource = getSurfaceContext()->resolvedUrl(finalQmlSource);
    }
#if defined(Q_OS_IOS)
    // Resolve relative application resources first so both qrc:/... callers
    // and paths such as hifi/tablet/TabletHome.qml can use the same reviewed
    // Documents override tree.
    finalQmlSource = resolveIOSQmlOverride(finalQmlSource);
    logIOSRuntimeMarker(
        "OVERTE_IOS_DYNAMIC_QML_GATE stage=load-requested",
        "requested=", qmlSource,
        "resolved=", finalQmlSource,
        "parent=", parent ? parent->objectName() : QStringLiteral("<root>"),
        "new_context=", createNewContext,
        "complete_before_callback=", completeBeforeCallback);
#endif

    if (!getRootItem()) {
        _sharedObject->setObjectName(finalQmlSource.toString());
    }

    auto targetContext = contextForUrl(finalQmlSource, parent, createNewContext);
    contextCallback(targetContext);
    QQmlComponent* qmlComponent;
    {
        PROFILE_RANGE(app, "new QQmlComponent");
        qmlComponent = new QQmlComponent(getSurfaceContext()->engine(), finalQmlSource, QQmlComponent::PreferSynchronous);
    }
    if (qmlComponent->isLoading()) {
        connect(qmlComponent, &QQmlComponent::statusChanged, this,
                [=, this](QQmlComponent::Status) {
                    finishQmlLoad(qmlComponent, targetContext, parent, callback,
                                  completeBeforeCallback);
                });
        return;
    }

    finishQmlLoad(qmlComponent, targetContext, parent, callback,
                  completeBeforeCallback);
}

void OffscreenSurface::finishQmlLoad(QQmlComponent* qmlComponent,
                                     QQmlContext* qmlContext,
                                     QQuickItem* parent,
                                     const QmlContextObjectCallback& callback,
                                     bool completeBeforeCallback) {
    PROFILE_RANGE(app, "finishQmlLoad");
    disconnect(qmlComponent, &QQmlComponent::statusChanged, this, 0);
    if (qmlComponent->isError()) {
#if defined(Q_OS_IOS)
        logIOSRuntimeMarker(
            "OVERTE_IOS_DYNAMIC_QML_GATE stage=component-error",
            "url=", qmlComponent->url(),
            "errors=", qmlComponent->errors().size());
        logIOSQmlErrors("component-error-detail", qmlComponent->errors());
#endif
        for (const auto& error : qmlComponent->errors()) {
            qCWarning(qmlLogging) << error.url() << error.line() << error;
        }
        qmlComponent->deleteLater();
        return;
    }

    QObject* newObject = qmlComponent->beginCreate(qmlContext);
    if (qmlComponent->isError()) {
#if defined(Q_OS_IOS)
        logIOSRuntimeMarker(
            "OVERTE_IOS_DYNAMIC_QML_GATE stage=begin-create-error",
            "url=", qmlComponent->url(),
            "errors=", qmlComponent->errors().size());
        logIOSQmlErrors("begin-create-error-detail", qmlComponent->errors());
#endif
        for (const auto& error : qmlComponent->errors()) {
            qCWarning(qmlLogging) << error.url() << error.line() << error;
        }
        if (!getRootItem()) {
            qFatal("Unable to finish loading QML root");
        }
        qmlComponent->deleteLater();
        return;
    }

    if (!newObject) {
        if (!getRootItem()) {
            qFatal("Could not load object as root item");
            return;
        }
        qCWarning(qmlLogging) << "Unable to load QML item";
        return;
    }

    qmlContext->engine()->setObjectOwnership(this, QQmlEngine::CppOwnership);

    // All quick items should be focusable
    QQuickItem* newItem = qobject_cast<QQuickItem*>(newObject);
    if (newItem) {
        // Make sure we make items focusable (critical for
        // supporting keyboard shortcuts)
        newItem->setFlag(QQuickItem::ItemIsFocusScope, true);
#ifdef DEBUG
        for (auto frame : newObject->findChildren<QQuickItem *>("Frame")) {
            frame->setProperty("qmlFile", qmlComponent->url());
        }
#endif
    }

    bool rootCreated = getRootItem() != nullptr;
#if defined(Q_OS_IOS)
    const QUrl loadedUrl = qmlComponent->url();
    logIOSRuntimeMarker(
        "OVERTE_IOS_DYNAMIC_QML_GATE stage=object-created",
        "url=", loadedUrl,
        "root_created=", rootCreated,
        "item=", newItem ? newItem->metaObject()->className() : "<non-quick-item>",
        "requested_parent=", parent ? parent->objectName() : QStringLiteral("<root>"));
#endif

    // If we already have a root, set ownership and visual ancestry before
    // bindings are evaluated. C++-created windows retain their historical
    // pre-completion callback because it supplies initial properties. QML's
    // dynamic load API completes first on iOS, matching Qt Loader semantics;
    // calling back while the component is only half-created leaves complex
    // Tablet applications with only their root background under Qt 6.
    if (rootCreated) {
        if (!completeBeforeCallback) {
            callback(qmlContext, newItem);
        }
        if (!parent) {
            parent = getRootItem();
        }
        // Allow child windows to be destroyed from JS
        QQmlEngine::setObjectOwnership(newObject, QQmlEngine::JavaScriptOwnership);

        // add object to the manual deletion list
        _sharedObject->addToDeletionList(newObject);

        newObject->setParent(parent);
        newItem->setParentItem(parent);
    } else {
        // The root item is ready. Associate it with the window.
        _sharedObject->setRootItem(newItem);
    }

    onItemCreated(qmlContext, newItem);

    if (!rootCreated) {
        connect(newItem, SIGNAL(sendToScript(QVariant)), this, SIGNAL(fromQml(QVariant)));
        onRootCreated();
        emit rootItemCreated(newItem);
        // Call this callback after rootitem is set, otherwise VrMenu wont work
        callback(qmlContext, newItem);
    }
    qmlComponent->completeCreate();
#if defined(Q_OS_IOS)
    if (qmlComponent->isError()) {
        logIOSQmlErrors("complete-create-error-detail", qmlComponent->errors());
        for (const auto& error : qmlComponent->errors()) {
            qCWarning(qmlLogging) << error.url() << error.line() << error;
        }
    }
#endif
    if (rootCreated && completeBeforeCallback) {
        callback(qmlContext, newItem);
    }

#if defined(Q_OS_IOS)
    logIOSQmlItemState("component-complete", loadedUrl, newItem,
                       completeBeforeCallback);
    const QPointer<QQuickItem> guardedItem(newItem);
    for (const int delayMs : { 0, 250, 1000 }) {
        QTimer::singleShot(delayMs, this,
            [guardedItem, loadedUrl, completeBeforeCallback, delayMs] {
                const QByteArray stage = QByteArray("settled-")
                    + QByteArray::number(delayMs) + QByteArray("ms");
                logIOSQmlItemState(stage.constData(), loadedUrl,
                                   guardedItem.data(), completeBeforeCallback);
            });
    }
#endif
    qmlComponent->deleteLater();
}

QQmlContext* OffscreenSurface::contextForUrl(const QUrl& qmlSource, QQuickItem* parent, bool forceNewContext) {
    QQmlContext* targetContext = parent ? QQmlEngine::contextForObject(parent) : getSurfaceContext();
    if (!targetContext) {
        targetContext = getSurfaceContext();
    }

    if (getRootItem() && forceNewContext) {
        targetContext = new QQmlContext(targetContext, targetContext->engine());
    }

    return targetContext;
}
