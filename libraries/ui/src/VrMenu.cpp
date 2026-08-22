//
//  VrMenu.cpp
//
//  Created by Bradley Austin Davis on 2015/04/21
//  Copyright 2015 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "VrMenu.h"

#include <QtQml>
#include <QMenuBar>
#include <QDebug>
#include <PathUtils.h>

#include "OffscreenUi.h"
#include "ui/Logging.h"



MenuUserData::MenuUserData(QAction* action, QObject* qmlObject, QObject* qmlParent) {
    _action = action;
    _qml = qmlObject;
    _qmlParent = qmlParent;

    action->setProperty(USER_DATA, QVariant::fromValue(this));
    qmlObject->setProperty(USER_DATA, QVariant::fromValue(this));
    qmlObject->setObjectName(uuid.toString());
    // Make sure we can find it again in the future
    updateQmlItemFromAction();
    _changedConnection = QObject::connect(action, &QAction::changed, [=, this] {
        updateQmlItemFromAction();
    });
    _shutdownConnection = QObject::connect(qApp, &QCoreApplication::aboutToQuit, [=, this] {
        QObject::disconnect(_changedConnection);
    });

    class ExclusionGroupSetter : public QObject {
    public:
        ExclusionGroupSetter(QObject* from, QObject* to, QObject* qmlParent) : QObject(from), _from(from), _to(to), _qmlParent(qmlParent) {
            _from->installEventFilter(this);
        }

        ~ExclusionGroupSetter() {
            _from->removeEventFilter(this);
        }
    protected:
        virtual bool eventFilter(QObject* o, QEvent* e) override {
            if (e->type() == QEvent::DynamicPropertyChange) {
                QDynamicPropertyChangeEvent* dpc = static_cast<QDynamicPropertyChangeEvent*>(e);
                if (dpc->propertyName() == "exclusionGroup") {
                    // unfortunately Qt doesn't support passing dynamic properties between C++ / QML, so we have to use this ugly helper function
                    QMetaObject::invokeMethod(_qmlParent,
                        "addExclusionGroup",
                        Qt::DirectConnection,
                        Q_ARG(QVariant, QVariant::fromValue(_to)),
                        Q_ARG(QVariant, _from->property(dpc->propertyName())));
                }
            }

            return QObject::eventFilter(o, e);
        }

    private:
        QObject* _from;
        QObject* _to;
        QObject* _qmlParent;
    };

    new ExclusionGroupSetter(action, qmlObject, qmlParent);
}

MenuUserData::~MenuUserData() {
    QObject::disconnect(_changedConnection);
    QObject::disconnect(_shutdownConnection);
    _action->setProperty(USER_DATA, QVariant());
    _qml->setProperty(USER_DATA, QVariant());
}

void MenuUserData::updateQmlItemFromAction() {
    _qml->setProperty("checkable", _action->isCheckable());
    _qml->setProperty("enabled", _action->isEnabled());
    QString text = _action->text();
    _qml->setProperty("text", text);
    _qml->setProperty("shortcut", _action->shortcut().toString());
    _qml->setProperty("checked", _action->isChecked());
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
    _qml->setProperty("visible", _action->isVisible());
#endif
}

void MenuUserData::clear() {
    _qml->setProperty("checkable", 0);
    _qml->setProperty("enabled", 0);
    _qml->setProperty("text", 0);
    _qml->setProperty("shortcut", 0);
    _qml->setProperty("checked", 0);
    _qml->setProperty("visible", 0);

    _action->setProperty(USER_DATA, QVariant());
    _qml->setProperty(USER_DATA, QVariant());
}



bool MenuUserData::hasData(QAction* object) {
    if (!object) {
        qWarning() << "Attempted to fetch MenuUserData for null object";
        return false;
    }
    return (nullptr != object->property(USER_DATA).value<MenuUserData*>());
}

MenuUserData* MenuUserData::forObject(QAction* object) {
    if (!object) {
        qWarning() << "Attempted to fetch MenuUserData for null object";
        return nullptr;
    }
    auto result = object->property(USER_DATA).value<MenuUserData*>();
    if (!result) {
        qWarning() << "Unable to find MenuUserData for object " << object;
        if (auto action = dynamic_cast<QAction*>(object)) {
            qWarning() << action->text();
        } else if (auto menu = dynamic_cast<QMenu*>(object)) {
            qWarning() << menu->title();
        }
        return nullptr;
    }
    return result;
}

VrMenu::VrMenu(OffscreenUi* parent) : QObject(parent) {
    _rootMenu = parent->getRootItem()->findChild<QObject*>("rootMenu");
    parent->getSurfaceContext()->setContextProperty("rootMenu", _rootMenu);
#if defined(Q_OS_IOS)
    qInfo().noquote() << "OVERTE_IOS_TOUCH_UI_GATE stage=menu-root-ready"
                      << "root_valid=" << (_rootMenu != nullptr);
#endif
}

QObject* VrMenu::findMenuObject(const QString& menuOption) {
    if (menuOption.isEmpty()) {
        return _rootMenu;
    }
    QObject* result = _rootMenu->findChild<QObject*>(menuOption);
    return result;
}


void VrMenu::addMenu(QMenu* menu) {
    auto* ui = qobject_cast<OffscreenUi*>(parent());
    if (!ui || !ui->getSurfaceContext()) {
        qWarning() << "Unable to create QML menu without an offscreen UI context";
        return;
    }
    auto* engine = ui->getSurfaceContext()->engine();
    Q_ASSERT(!MenuUserData::hasData(menu->menuAction()));
    QObject* parent = menu->parent();
    QObject* qmlParent = nullptr;
    QMenu* parentMenu = dynamic_cast<QMenu*>(parent);
    if (parentMenu && menu->menuAction()) {
        MenuUserData* userData = MenuUserData::forObject(parentMenu->menuAction());
        if (!userData) {
            return;
        }
        qmlParent = findMenuObject(userData->uuid.toString());
    } else if (dynamic_cast<QMenuBar*>(parent)) {
        qmlParent = _rootMenu;
    } else {
        Q_ASSERT(false);
        return;
    }

    QQmlComponent menuComponent(engine);
    menuComponent.loadUrl(PathUtils::qmlUrl("controls/WrappedMenu.qml"));
    if (menuComponent.status() == QQmlComponent::Error) {
        qWarning() << "Unable to load Qt 6 QML menu:" << menuComponent.errorString();
        return;
    }
    QObject* menuObject = menuComponent.create(ui->getSurfaceContext());
    if (!menuObject) {
        qWarning() << "Unable to create QML menu for widget menu:" << menu->title();
        return;
    }
    menuObject->setObjectName(menu->title());
    menuObject->setProperty("title", menu->title());
    menuObject->setParent(qmlParent);
    const bool invokeResult = QMetaObject::invokeMethod(
        qmlParent, "addMenuWrap", Qt::DirectConnection,
        Q_ARG(QVariant, QVariant::fromValue(menuObject)));
    if (!invokeResult) {
        qWarning() << "Unable to attach QML menu to parent:" << menu->title();
        menuObject->deleteLater();
        return;
    }

    // Bind the QML and Widget together
    new MenuUserData(menu->menuAction(), menuObject, qmlParent);
}

void bindActionToQmlAction(QObject* qmlAction, QAction* action, QObject* qmlParent) {
    auto text = action->text();
    if (text == "Login") {
        qDebug(uiLogging) << "Login action " << action;
    }

    new MenuUserData(action, qmlAction, qmlParent);
    QObject::connect(action, &QAction::toggled, [=](bool checked) {
        qmlAction->setProperty("checked", checked);
    });
    QObject::connect(qmlAction, SIGNAL(triggered()), action, SLOT(trigger()));
}

void VrMenu::addAction(QMenu* menu, QAction* action) {
    auto* ui = qobject_cast<OffscreenUi*>(parent());
    if (!ui || !ui->getSurfaceContext()) {
        qWarning() << "Unable to create QML action without an offscreen UI context";
        return;
    }
    auto* engine = ui->getSurfaceContext()->engine();
    Q_ASSERT(!MenuUserData::hasData(action));

    Q_ASSERT(MenuUserData::hasData(menu->menuAction()));
    MenuUserData* userData = MenuUserData::forObject(menu->menuAction());
    if (!userData) {
        return;
    }
    QObject* menuQml = findMenuObject(userData->uuid.toString());
    if (!menuQml) {
        qWarning() << "Unable to find QML parent for action:" << action->text();
        return;
    }

    QQmlComponent menuItemComponent(engine);
    menuItemComponent.loadFromModule("QtQuick.Controls", "MenuItem");
    if (menuItemComponent.status() == QQmlComponent::Error) {
        qWarning() << "Unable to load Qt 6 QML MenuItem:" << menuItemComponent.errorString();
        return;
    }
    QObject* menuItemObject = menuItemComponent.create(ui->getSurfaceContext());
    if (!menuItemObject) {
        qWarning() << "Unable to create QML action:" << action->text();
        return;
    }
    menuItemObject->setObjectName(action->text());
    menuItemObject->setProperty("text", action->text());
    menuItemObject->setParent(menuQml);
    const bool invokeResult = QMetaObject::invokeMethod(
        menuQml, "addItemWrap", Qt::DirectConnection,
        Q_ARG(QVariant, QVariant::fromValue(menuItemObject)));
    if (!invokeResult) {
        qWarning() << "Unable to attach QML action:" << action->text();
        menuItemObject->deleteLater();
        return;
    }
    // Bind the QML and Widget together
    bindActionToQmlAction(menuItemObject, action, _rootMenu);
}

void VrMenu::addSeparator(QMenu* menu) {
    auto* ui = qobject_cast<OffscreenUi*>(parent());
    if (!ui || !ui->getSurfaceContext()) {
        return;
    }
    auto* engine = ui->getSurfaceContext()->engine();
    Q_ASSERT(MenuUserData::hasData(menu->menuAction()));
    MenuUserData* userData = MenuUserData::forObject(menu->menuAction());
    if (!userData) {
        return;
    }
    QObject* menuQml = findMenuObject(userData->uuid.toString());
    if (!menuQml) {
        return;
    }

    QQmlComponent separatorComponent(engine);
    separatorComponent.loadFromModule("QtQuick.Controls", "MenuSeparator");
    if (separatorComponent.status() == QQmlComponent::Error) {
        qWarning() << "Unable to load Qt 6 QML MenuSeparator:" << separatorComponent.errorString();
        return;
    }
    QObject* separatorObject = separatorComponent.create(ui->getSurfaceContext());
    if (!separatorObject) {
        return;
    }
    separatorObject->setParent(menuQml);
    const bool invokeResult = QMetaObject::invokeMethod(
        menuQml, "addItemWrap", Qt::DirectConnection,
        Q_ARG(QVariant, QVariant::fromValue(separatorObject)));
    if (!invokeResult) {
        qWarning() << "Unable to attach QML menu separator";
        separatorObject->deleteLater();
    }
}

void VrMenu::insertAction(QAction* before, QAction* action) {
    auto* ui = qobject_cast<OffscreenUi*>(parent());
    if (!ui || !ui->getSurfaceContext()) {
        return;
    }
    auto* engine = ui->getSurfaceContext()->engine();
    QObject* beforeQml{ nullptr };
    {
        MenuUserData* beforeUserData = MenuUserData::forObject(before);
        Q_ASSERT(beforeUserData);
        if (!beforeUserData) {
            return;
        }
        beforeQml = findMenuObject(beforeUserData->uuid.toString());
    }
    QObject* menu = beforeQml->parent();
    if (!menu) {
        return;
    }

    QQmlComponent menuItemComponent(engine);
    menuItemComponent.loadFromModule("QtQuick.Controls", "MenuItem");
    if (menuItemComponent.status() == QQmlComponent::Error) {
        qWarning() << "Unable to load inserted Qt 6 QML MenuItem:" << menuItemComponent.errorString();
        return;
    }
    QObject* menuItemObject = menuItemComponent.create(ui->getSurfaceContext());
    if (!menuItemObject) {
        return;
    }
    menuItemObject->setObjectName(action->text());
    menuItemObject->setProperty("text", action->text());
    menuItemObject->setParent(menu);
    // FIXME this needs to find the index of the beforeQml item and call insertItem(int, object)
    const bool invokeResult = QMetaObject::invokeMethod(
        menu, "addItemWrap", Qt::DirectConnection,
        Q_ARG(QVariant, QVariant::fromValue(menuItemObject)));
    if (invokeResult) {
        bindActionToQmlAction(menuItemObject, action, _rootMenu);
    } else {
        qWarning() << "Failed to find addItemWrap() method in object" << menu
                   << ". Not inserting action" << action;
        menuItemObject->deleteLater();
    }
}

class QQuickMenuBase;
class QQuickMenu1;

void VrMenu::removeAction(QAction* action) {
    if (!action) {
        qWarning("Attempted to remove invalid menu action");
        return;
    }
    MenuUserData* userData = MenuUserData::forObject(action);
    if (!userData) {
        qWarning("Attempted to remove menu action with no found QML object");
        return;
    }

    userData->clear();
    delete userData;
}
