//
//  TouchscreenVirtualPadDevice.cpp
//  input-plugins/src/input-plugins
//
//  Created by Triplelexx on 01/31/16.
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//
#include "TouchscreenVirtualPadDevice.h"
#include "KeyboardMouseDevice.h"

#include <QtGui/QTouchEvent>
#include <QGestureEvent>
#include <QGuiApplication>
#include <QWindow>
#include <QScreen>

#include <controllers/UserInputMapper.h>
#include <PathUtils.h>
#include <NumericalConstants.h>
#include <SettingHandle.h>
#include <ui/TabletScriptingInterface.h>
#include "VirtualPadManager.h"

#include <cmath>

#if defined(Q_OS_IOS)
#include <shared/IOSRuntimeLogging.h>
#endif

const char* TouchscreenVirtualPadDevice::NAME = "TouchscreenVirtualPad";

namespace {
const QList<OverteTouchPoint>& touchPoints(const QTouchEvent* event) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    return event->points();
#else
    return event->touchPoints();
#endif
}

QPointF touchPosition(const OverteTouchPoint& point) {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    return point.position();
#else
    return point.pos();
#endif
}

QSize touchViewportSize() {
    if (auto* window = qApp->focusWindow()) {
        const QSize size = window->size();
        if (!size.isEmpty()) {
            return size;
        }
    }
    if (auto* screen = qApp->primaryScreen()) {
        return screen->availableSize();
    }
    return {};
}
}

bool TouchscreenVirtualPadDevice::isSupported() const {
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    for (const auto* touchDevice : QInputDevice::devices()) {
        if (touchDevice->type() == QInputDevice::DeviceType::TouchScreen) {
#else
    for (auto touchDevice : QTouchDevice::devices()) {
        if (touchDevice->type() == QTouchDevice::TouchScreen) {
#endif
            return true;
        }
    }
#if defined(Q_OS_ANDROID) || defined(Q_OS_IOS)
    // Mobile Qt can enumerate the physical touchscreen after plugin discovery.
    // The platform itself is sufficient evidence that this device is supported.
    return true;
#endif
    return false;
}

void TouchscreenVirtualPadDevice::init() {
    _fixedPosition = true; // This should be config
    _viewTouchUpdateCount = 0;

    resize();

    auto& virtualPadManager = VirtualPad::Manager::instance();

    if (_fixedPosition) {
        virtualPadManager.getLeftVirtualPad()->setShown(virtualPadManager.isEnabled() && !virtualPadManager.isHidden()); // Show whenever it's enabled
    }

    KeyboardMouseDevice::enableTouch(false); // Touch for view controls is managed by this plugin
#if defined(Q_OS_IOS)
    logIOSRuntimeMarker(
        "OVERTE_IOS_TOUCH_INPUT_GATE stage=virtual-pad-initialized",
        "enabled=", virtualPadManager.isEnabled(),
        "hidden=", virtualPadManager.isHidden(),
        "fixed_position=", _fixedPosition,
        "dpi=", _screenDPI,
        "screen_center_x=", _screenWidthCenter);
#endif
}

void TouchscreenVirtualPadDevice::resize() {
    QScreen* eventScreen = qApp->primaryScreen();
    if (!eventScreen) {
        return;
    }
    if (_screenDPIProvided != eventScreen->physicalDotsPerInch()) {
        _screenWidthCenter = eventScreen->availableSize().width() / 2;
        _screenDPIScale.x = (float)eventScreen->physicalDotsPerInchX();
        _screenDPIScale.y = (float)eventScreen->physicalDotsPerInchY();
        _screenDPIProvided = eventScreen->physicalDotsPerInch();
        _screenDPI = eventScreen->physicalDotsPerInch();

        _fixedRadius = _screenDPI * 0.5f * VirtualPad::Manager::BASE_DIAMETER_PIXELS / VirtualPad::Manager::DPI;
        _fixedRadiusForCalc = _fixedRadius - _screenDPI * VirtualPad::Manager::STICK_RADIUS_PIXELS / VirtualPad::Manager::DPI;

        _buttonRadius = _screenDPI * VirtualPad::Manager::BTN_TRIMMED_RADIUS_PIXELS / VirtualPad::Manager::DPI;
    }

    auto& virtualPadManager = VirtualPad::Manager::instance();
    setupControlsPositions(virtualPadManager, true);
}

void TouchscreenVirtualPadDevice::setupControlsPositions(VirtualPad::Manager& virtualPadManager, bool force) {
    if (_extraBottomMargin == virtualPadManager.extraBottomMargin() && !force) return; // Our only criteria to decide a center change is the bottom margin

    const QSize viewportSize = touchViewportSize();
    if (viewportSize.isEmpty()) {
        return;
    }
    _extraBottomMargin = virtualPadManager.extraBottomMargin();
    int safeBottomInset { 0 };
#if defined(Q_OS_IOS)
    if (const auto tablet = DependencyManager::get<TabletScriptingInterface>()) {
        const QVariantMap metrics = tablet->getTouchUiRuntimeMetrics();
        if (metrics.value("valid").toBool()) {
            safeBottomInset = std::max(0, metrics.value("safeInsetBottom").toInt());
        }
    }
#endif
    const int effectiveBottomMargin = _extraBottomMargin + safeBottomInset;

    // Movement stick
    float margin = _screenDPI * VirtualPad::Manager::BASE_MARGIN_PIXELS / VirtualPad::Manager::DPI;
    _screenWidthCenter = viewportSize.width() / 2;
    _fixedCenterPosition = glm::vec2( _fixedRadius + margin, viewportSize.height() - margin - _fixedRadius - effectiveBottomMargin);
    _moveRefTouchPoint = _fixedCenterPosition;
    virtualPadManager.getLeftVirtualPad()->setFirstTouch(_moveRefTouchPoint);

    // Jump button
    float btnPixelSize = _screenDPI * VirtualPad::Manager::BTN_FULL_PIXELS / VirtualPad::Manager::DPI;
    float rightMargin = _screenDPI * VirtualPad::Manager::BTN_RIGHT_MARGIN_PIXELS / VirtualPad::Manager::DPI;
    float bottomMargin = _screenDPI * VirtualPad::Manager::BTN_BOTTOM_MARGIN_PIXELS/ VirtualPad::Manager::DPI;
    glm::vec2 jumpButtonPosition = glm::vec2( viewportSize.width() - rightMargin - btnPixelSize, viewportSize.height() - bottomMargin - _buttonRadius - effectiveBottomMargin);
    glm::vec2 rbButtonPosition = glm::vec2( viewportSize.width() - rightMargin - btnPixelSize, viewportSize.height() - 2 * bottomMargin - 3 * _buttonRadius - effectiveBottomMargin);

    // Avoid generating buttons in portrait mode. Keep existing hit targets in
    // sync with the render positions when iOS publishes its final safe-area
    // viewport after plugin initialization.
    if (viewportSize.width() > viewportSize.height()) {
        if (_buttonsManager.buttonsCount() == 0) {
            _buttonsManager.addButton(TouchscreenButton(JUMP, JUMP_BUTTON, _buttonRadius, jumpButtonPosition, _inputDevice ));
            _buttonsManager.addButton(TouchscreenButton(RB, RB_BUTTON, _buttonRadius, rbButtonPosition, _inputDevice ));
        } else if (_buttonsManager.buttonsCount() >= 2) {
            _buttonsManager.buttons[0].buttonPosition = jumpButtonPosition;
            _buttonsManager.buttons[0].buttonRadius = _buttonRadius;
            _buttonsManager.buttons[1].buttonPosition = rbButtonPosition;
            _buttonsManager.buttons[1].buttonRadius = _buttonRadius;
        }
        virtualPadManager.setButtonPosition(VirtualPad::Manager::Button::JUMP, jumpButtonPosition);
        virtualPadManager.setButtonPosition(VirtualPad::Manager::Button::HANDSHAKE, rbButtonPosition);
#if defined(Q_OS_IOS)
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=controls-positioned",
            "viewport=", viewportSize,
            "move=", QStringLiteral("%1,%2").arg(_fixedCenterPosition.x).arg(_fixedCenterPosition.y),
            "jump=", QStringLiteral("%1,%2").arg(jumpButtonPosition.x).arg(jumpButtonPosition.y),
            "handshake=", QStringLiteral("%1,%2").arg(rbButtonPosition.x).arg(rbButtonPosition.y),
            "safe_bottom=", safeBottomInset,
            "button_radius=", _buttonRadius);
#endif
    }

}

float clip(float n, float lower, float upper) {
    return std::max(lower, std::min(n, upper));
}

glm::vec2 TouchscreenVirtualPadDevice::clippedPointInCircle(float radius, glm::vec2 origin, glm::vec2 touchPoint) {
    float deltaX = touchPoint.x - origin.x;
    float deltaY = touchPoint.y - origin.y;

    float distance = sqrt(pow(deltaX, 2) + pow(deltaY, 2));

    // First case, inside the boundaires, just use the distance
    if (distance <= radius) {
        return touchPoint;
    }

    // Second case, purely vertical (avoid division by zero)
    if (deltaX == 0.0f) {
        return vec2(touchPoint.x, clip(touchPoint.y, origin.y-radius, origin.y+radius) );
    }

    // Third case, calculate point in circumference
    // line formula
    float m = deltaY / deltaX;
    float b = touchPoint.y - m * touchPoint.x;

    // quadtratic coefs of circumference and line intersection
    float qa = powf(m, 2.0f) + 1.0f;
    float qb = 2.0f * ( m * b - origin.x - origin.y * m);
    float qc = powf(origin.x, 2.0f) - powf(radius, 2.0f) + b * b - 2.0f * b * origin.y + powf(origin.y, 2.0f);

    float discr = qb * qb - 4.0f * qa * qc;
    float discrSign = deltaX > 0.0f ? 1.0f : - 1.0f;

    float finalX = (-qb + discrSign * sqrtf(discr)) / (2.0f * qa);
    float finalY = m * finalX + b;

    return vec2(finalX, finalY);
}

void TouchscreenVirtualPadDevice::processInputDeviceForMove(VirtualPad::Manager& virtualPadManager) {
    vec2 clippedPoint = clippedPointInCircle(_fixedRadiusForCalc, _moveRefTouchPoint, _moveCurrentTouchPoint);

    _inputDevice->_axisStateMap[controller::LX].value = (clippedPoint.x - _moveRefTouchPoint.x) / _fixedRadiusForCalc;
    _inputDevice->_axisStateMap[controller::LY].value = (clippedPoint.y - _moveRefTouchPoint.y) / _fixedRadiusForCalc;

    virtualPadManager.getLeftVirtualPad()->setFirstTouch(_moveRefTouchPoint);
    virtualPadManager.getLeftVirtualPad()->setCurrentTouch(clippedPoint);
    virtualPadManager.getLeftVirtualPad()->setBeingTouched(true);
    virtualPadManager.getLeftVirtualPad()->setShown(true); // If touched, show in any mode (fixed joystick position or non-fixed)
}

void TouchscreenVirtualPadDevice::processInputDeviceForView() {
    // We use average across how many times we've got touchUpdate events.
    // Using the average instead of the full deltaX and deltaY, makes deltaTime in MyAvatar dont't accelerate rotation when there is a low touchUpdate rate (heavier domains).
    // (Because it multiplies this input value by deltaTime (with a coefficient)).
    float sensitivityScale { 1.0f };
#if defined(Q_OS_IOS)
    sensitivityScale = static_cast<float>(iosRuntimeDiagnosticInt(
        "touchLookSensitivityPercent", 400, 50, 1200)) / 100.0f;
#endif
    _inputDevice->_axisStateMap[controller::RX].value = _viewTouchUpdateCount == 0 ? 0 :
        sensitivityScale * (_viewCurrentTouchPoint.x - _viewRefTouchPoint.x) / _viewTouchUpdateCount;
    _inputDevice->_axisStateMap[controller::RY].value = _viewTouchUpdateCount == 0 ? 0 :
        sensitivityScale * (_viewCurrentTouchPoint.y - _viewRefTouchPoint.y) / _viewTouchUpdateCount;

    // after use, save last touch point as ref
    _viewRefTouchPoint = _viewCurrentTouchPoint;
    _viewTouchUpdateCount = 0;
}

void TouchscreenVirtualPadDevice::processInputDeviceForPinch() {
#if defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)
    if (_pinchOut > 0.0f) {
        _inputDevice->_axisStateMap[PINCH_OUT].value = _pinchOut;
    }
    if (_pinchIn > 0.0f) {
        _inputDevice->_axisStateMap[PINCH_IN].value = _pinchIn;
    }
#endif
    _pinchOut = 0.0f;
    _pinchIn = 0.0f;
}

void TouchscreenVirtualPadDevice::pluginUpdate(float deltaTime, const controller::InputCalibrationData& inputCalibrationData) {
    auto userInputMapper = DependencyManager::get<controller::UserInputMapper>();
    userInputMapper->withLock([&, this]() {
        _inputDevice->update(deltaTime, inputCalibrationData);
    });

    auto& virtualPadManager = VirtualPad::Manager::instance();
    setupControlsPositions(virtualPadManager);

    if (_moveHasValidTouch) {
        processInputDeviceForMove(virtualPadManager);
    } else {
        virtualPadManager.getLeftVirtualPad()->setBeingTouched(false);
        if (_fixedPosition) {
            virtualPadManager.getLeftVirtualPad()->setCurrentTouch(_fixedCenterPosition); // reset to the center
            virtualPadManager.getLeftVirtualPad()->setShown(virtualPadManager.isEnabled() && !virtualPadManager.isHidden()); // Show whenever it's enabled
        } else {
            virtualPadManager.getLeftVirtualPad()->setShown(false);
        }
    }

    if (_viewHasValidTouch) {
        processInputDeviceForView();
    }

    processInputDeviceForPinch();

}

void TouchscreenVirtualPadDevice::InputDevice::update(float deltaTime, const controller::InputCalibrationData& inputCalibrationData) {
    _axisStateMap.clear();
}

bool TouchscreenVirtualPadDevice::InputDevice::triggerHapticPulse(float strength, float duration, uint16_t index) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    virtualPadManager.requestHapticFeedback((int) duration);
    return true;
}


void TouchscreenVirtualPadDevice::InputDevice::focusOutEvent() {
}



void TouchscreenVirtualPadDevice::touchBeginEvent(const QTouchEvent* event) {
    // touch begin here is a big begin -> begins both pads? maybe it does nothing
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (!virtualPadManager.isEnabled() || virtualPadManager.isHidden()) {
        return;
    }
#if defined(Q_OS_IOS)
    const int traceLimit = iosRuntimeDiagnosticInt("touchInputTraceLimit", 24, 0, 1000);
    if (_touchDiagnosticEventCount < static_cast<uint32_t>(traceLimit)) {
        ++_touchDiagnosticEventCount;
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=touch-begin",
            "points=", touchPoints(event).count(),
            "event_ordinal=", _touchDiagnosticEventCount);
    }
#endif
}

void TouchscreenVirtualPadDevice::touchEndEvent(const QTouchEvent* event) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (!virtualPadManager.isEnabled() || virtualPadManager.isHidden()) {
        moveTouchEnd();
        viewTouchEnd();
        _buttonsManager.endTouchForAll();
        return;
    }
    // touch end here is a big reset -> resets both pads
    _touchPointCount = 0;
    _unusedTouches.clear();
    moveTouchEnd();
    viewTouchEnd();
    _buttonsManager.endTouchForAll();
    _inputDevice->_axisStateMap.clear();
    _inputDevice->_buttonPressedMap.clear();
    _lastPinchScale = 0.0f;
    _pinchScale = 0.0f;
    _pinchOut = 0.0f;
    _pinchIn = 0.0f;
#if defined(Q_OS_IOS)
    const int traceLimit = iosRuntimeDiagnosticInt("touchInputTraceLimit", 24, 0, 1000);
    if (_touchDiagnosticEventCount < static_cast<uint32_t>(traceLimit)) {
        ++_touchDiagnosticEventCount;
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=touch-end",
            "event_ordinal=", _touchDiagnosticEventCount);
    }
#endif
}

void TouchscreenVirtualPadDevice::processUnusedTouches(std::map<int, TouchType> unusedTouchesInEvent) {
    std::vector<int> touchesToDelete;
    for (auto const& touchEntry : _unusedTouches) {
        if (!unusedTouchesInEvent.count(touchEntry.first)) {
            touchesToDelete.push_back(touchEntry.first);
        }
    }
    for (int touchToDelete : touchesToDelete) {
        _unusedTouches.erase(touchToDelete);
    }

    for (auto const& touchEntry : unusedTouchesInEvent) {
        if (!_unusedTouches.count(touchEntry.first)) {
            _unusedTouches[touchEntry.first] = touchEntry.second;
        }
    }

}

void TouchscreenVirtualPadDevice::touchUpdateEvent(const QTouchEvent* event) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (!virtualPadManager.isEnabled() || virtualPadManager.isHidden()) {
        moveTouchEnd();
        viewTouchEnd();
        return;
    }
    const auto& tPoints = touchPoints(event);
    _touchPointCount = tPoints.count();

    bool moveTouchFound = false;
    bool viewTouchFound = false;

    int idxMoveStartingPointCandidate = -1;
    int idxViewStartingPointCandidate = -1;

    _buttonsManager.resetEventValues();

    glm::vec2 thisPoint;
    int thisPointId;
    std::map<int, TouchType> unusedTouchesInEvent;

    for (int i = 0; i < _touchPointCount; ++i) {
        const auto position = touchPosition(tPoints[i]);
        thisPoint.x = position.x();
        thisPoint.y = position.y();
        thisPointId = tPoints[i].id();

        if (!moveTouchFound && _moveHasValidTouch && _moveCurrentTouchId == thisPointId) {
            // valid if it's an ongoing touch
            moveTouchFound = true;
            moveTouchUpdate(thisPoint);
            continue;
        }

        if (!viewTouchFound && _viewHasValidTouch && _viewCurrentTouchId == thisPointId) {
            // valid if it's an ongoing touch
            viewTouchFound = true;
            viewTouchUpdate(thisPoint);
            continue;
        }

        if (_buttonsManager.processOngoingTouch(thisPoint, thisPointId)) {
            continue;
        }

        if (!moveTouchFound && idxMoveStartingPointCandidate == -1 && moveTouchBeginIsValid(thisPoint) &&
                (!_unusedTouches.count(thisPointId) || _unusedTouches[thisPointId] == MOVE )) {
            idxMoveStartingPointCandidate = i;
            continue;
        }

        if (!viewTouchFound && idxViewStartingPointCandidate == -1 && viewTouchBeginIsValid(thisPoint) &&
                (!_unusedTouches.count(thisPointId) || _unusedTouches[thisPointId] == VIEW )) {
            idxViewStartingPointCandidate = i;
            continue;
        }

        if (_buttonsManager.findStartingTouchPointCandidate(thisPoint, thisPointId, i, _unusedTouches)) {
            continue;
        }

        if (moveTouchBeginIsValid(thisPoint)) {
            unusedTouchesInEvent[thisPointId] = MOVE;
        } else if (viewTouchBeginIsValid(thisPoint))  {
            unusedTouchesInEvent[thisPointId] = VIEW;
        } else {
            _buttonsManager.saveUnusedTouches(unusedTouchesInEvent, thisPoint, thisPointId);
        }

    }

    processUnusedTouches(unusedTouchesInEvent);

    if (!moveTouchFound) {
        if (idxMoveStartingPointCandidate != -1) {
            _moveCurrentTouchId = tPoints[idxMoveStartingPointCandidate].id();
            _unusedTouches.erase(_moveCurrentTouchId);
            const auto position = touchPosition(tPoints[idxMoveStartingPointCandidate]);
            thisPoint.x = position.x();
            thisPoint.y = position.y();
            moveTouchBegin(thisPoint);
        } else {
            moveTouchEnd();
        }
    }
    if (!viewTouchFound) {
        if (idxViewStartingPointCandidate != -1) {
            _viewCurrentTouchId = tPoints[idxViewStartingPointCandidate].id();
            _unusedTouches.erase(_viewCurrentTouchId);
            const auto position = touchPosition(tPoints[idxViewStartingPointCandidate]);
            thisPoint.x = position.x();
            thisPoint.y = position.y();
            viewTouchBegin(thisPoint);
        } else {
            viewTouchEnd();
        }
    }

    _buttonsManager.processBeginOrEnd(thisPoint, tPoints, _unusedTouches);

#if defined(Q_OS_IOS)
    const int traceLimit = iosRuntimeDiagnosticInt("touchInputTraceLimit", 24, 0, 1000);
    if (_touchDiagnosticEventCount < static_cast<uint32_t>(traceLimit)) {
        int activeButtons { 0 };
        for (const auto& button : _buttonsManager.buttons) {
            activeButtons += button.hasValidTouch ? 1 : 0;
        }
        ++_touchDiagnosticEventCount;
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=touch-update",
            "points=", _touchPointCount,
            "move=", _moveHasValidTouch,
            "view=", _viewHasValidTouch,
            "buttons=", activeButtons,
            "unused=", _unusedTouches.size(),
            "event_ordinal=", _touchDiagnosticEventCount);
    }
#endif

}

bool TouchscreenVirtualPadDevice::viewTouchBeginIsValid(glm::vec2 touchPoint) {
    return !moveTouchBeginIsValid(touchPoint) && _buttonsManager.touchBeginInvalidForAllButtons(touchPoint);
}

bool TouchscreenVirtualPadDevice::moveTouchBeginIsValid(glm::vec2 touchPoint) {
    if (_fixedPosition) {
        // inside circle
        return glm::distance2(touchPoint, _fixedCenterPosition) < _fixedRadius * _fixedRadius;
    } else {
        // left side
        return touchPoint.x < _screenWidthCenter;
    }
}

void TouchscreenVirtualPadDevice::moveTouchBegin(glm::vec2 touchPoint) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (virtualPadManager.isEnabled() && !virtualPadManager.isHidden()) {
        if (_fixedPosition) {
            _moveRefTouchPoint = _fixedCenterPosition;
        } else {
            _moveRefTouchPoint = touchPoint;
        }
        _moveCurrentTouchPoint = touchPoint;
        _moveHasValidTouch = true;
    }
}

void TouchscreenVirtualPadDevice::moveTouchUpdate(glm::vec2 touchPoint) {
    _moveCurrentTouchPoint = touchPoint;
}

void TouchscreenVirtualPadDevice::moveTouchEnd() {
    if (_moveHasValidTouch) { // do stuff once
        _moveHasValidTouch = false;
        _inputDevice->_axisStateMap[controller::LX].value = 0;
        _inputDevice->_axisStateMap[controller::LY].value = 0;
    }
}

void TouchscreenVirtualPadDevice::viewTouchBegin(glm::vec2 touchPoint) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (virtualPadManager.isEnabled() && !virtualPadManager.isHidden()) {
        _viewRefTouchPoint = touchPoint;
        _viewCurrentTouchPoint = touchPoint;
        _viewTouchUpdateCount++;
        _viewHasValidTouch = true;
    }
}

void TouchscreenVirtualPadDevice::viewTouchUpdate(glm::vec2 touchPoint) {
    _viewCurrentTouchPoint = touchPoint;
    _viewTouchUpdateCount++;
}

void TouchscreenVirtualPadDevice::viewTouchEnd() {
    if (_viewHasValidTouch) { // do stuff once
        _viewHasValidTouch = false;
        _inputDevice->_axisStateMap[controller::RX].value = 0;
        _inputDevice->_axisStateMap[controller::RY].value = 0;
    }
}

void TouchscreenVirtualPadDevice::touchGestureEvent(const QGestureEvent* event) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (!virtualPadManager.isEnabled() || virtualPadManager.isHidden()) {
        return;
    }
    if (QGesture* gesture = event->gesture(Qt::PinchGesture)) {
        QPinchGesture* pinch = static_cast<QPinchGesture*>(gesture);
        _pinchScale = pinch->totalScaleFactor();
#if defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)
#if defined(ANDROID_APP_PHONE_INTERFACE)
        // Preferences may update this key through a different Setting::Handle.
        // Read the manager-backed value so a saved change takes effect without
        // restarting instead of retaining this device's startup cache.
        Settings settings;
        if (!settings.value("android/phone/pinchZoomEnabled", false).toBool()) {
            _lastPinchScale = 0.0f;
            _pinchOut = 0.0f;
            _pinchIn = 0.0f;
            return;
        }
#endif
        if (pinch->state() == Qt::GestureStarted || _lastPinchScale <= 0.0f) {
            _lastPinchScale = _pinchScale;
            return;
        }

        constexpr float MIN_SCALE_CHANGE = 0.001f;
        float scaleChange = _pinchScale / _lastPinchScale - 1.0f;
        if (scaleChange > MIN_SCALE_CHANGE) {
            _pinchOut += scaleChange;
        } else if (scaleChange < -MIN_SCALE_CHANGE) {
            _pinchIn += -scaleChange;
        }
        _lastPinchScale = _pinchScale;

        if (pinch->state() == Qt::GestureFinished || pinch->state() == Qt::GestureCanceled) {
            _lastPinchScale = 0.0f;
        }
#endif
    }
}

controller::Input TouchscreenVirtualPadDevice::InputDevice::makeInput(TouchscreenVirtualPadDevice::TouchAxisChannel axis) const {
    return controller::Input(_deviceID, axis, controller::ChannelType::AXIS);
}

controller::Input TouchscreenVirtualPadDevice::InputDevice::makeInput(TouchscreenVirtualPadDevice::TouchButtonChannel button) const {
    return controller::Input(_deviceID, button, controller::ChannelType::BUTTON);
}

controller::Input::NamedVector TouchscreenVirtualPadDevice::InputDevice::getAvailableInputs() const {
    using namespace controller;
    QVector<Input::NamedPair> availableInputs{
        Input::NamedPair(makeInput(TouchAxisChannel::LX), "LX"),
        Input::NamedPair(makeInput(TouchAxisChannel::LY), "LY"),
        Input::NamedPair(makeInput(TouchAxisChannel::RX), "RX"),
        Input::NamedPair(makeInput(TouchAxisChannel::RY), "RY"),
        Input::NamedPair(makeInput(TouchAxisChannel::PINCH_OUT), "PinchOut"),
        Input::NamedPair(makeInput(TouchAxisChannel::PINCH_IN), "PinchIn"),
        Input::NamedPair(makeInput(TouchButtonChannel::JUMP), "JUMP_BUTTON_PRESS"),
        Input::NamedPair(makeInput(TouchButtonChannel::RB), "RB")
    };
    return availableInputs;
}

QString TouchscreenVirtualPadDevice::InputDevice::getDefaultMappingConfig() const {
#if defined(ANDROID_APP_PHONE_INTERFACE) || defined(Q_OS_IOS)
    static const QString MAPPING_JSON = PathUtils::resourcesPath() + "/controllers/touchscreenvirtualpad-phone.json";
#else
    static const QString MAPPING_JSON = PathUtils::resourcesPath() + "/controllers/touchscreenvirtualpad.json";
#endif
    return MAPPING_JSON;
}

TouchscreenVirtualPadDevice::TouchscreenButton::TouchscreenButton(
        TouchscreenVirtualPadDevice::TouchButtonChannel channelIn,
        TouchscreenVirtualPadDevice::TouchType touchTypeIn, float buttonRadiusIn,
        glm::vec2 buttonPositionIn, std::shared_ptr<InputDevice> inputDeviceIn) :
    buttonPosition(buttonPositionIn),
    buttonRadius(buttonRadiusIn),
    touchType(touchTypeIn),
    channel(channelIn),
    _inputDevice(inputDeviceIn)
{
}

void TouchscreenVirtualPadDevice::TouchscreenButton::touchBegin(glm::vec2 touchPoint) {
    auto& virtualPadManager = VirtualPad::Manager::instance();
    if (virtualPadManager.isEnabled() && !virtualPadManager.isHidden()) {
        hasValidTouch = true;

        _inputDevice->_buttonPressedMap.insert(channel);
#if defined(Q_OS_IOS)
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=button-pressed",
            "channel=", static_cast<int>(channel),
            "point=", QStringLiteral("%1,%2").arg(touchPoint.x).arg(touchPoint.y),
            "center=", QStringLiteral("%1,%2").arg(buttonPosition.x).arg(buttonPosition.y));
#endif
    }
}

void TouchscreenVirtualPadDevice::TouchscreenButton::touchUpdate(glm::vec2 touchPoint) {

}

void TouchscreenVirtualPadDevice::TouchscreenButton::touchEnd() {
    if (hasValidTouch) {
        hasValidTouch = false;

        _inputDevice->_buttonPressedMap.erase(channel);
#if defined(Q_OS_IOS)
        logIOSRuntimeMarker(
            "OVERTE_IOS_TOUCH_INPUT_GATE stage=button-released",
            "channel=", static_cast<int>(channel));
#endif
    }
}

bool TouchscreenVirtualPadDevice::TouchscreenButton::touchBeginIsValid(glm::vec2 touchPoint) {
    return glm::distance2(touchPoint, buttonPosition) < buttonRadius * buttonRadius;
}

void TouchscreenVirtualPadDevice::TouchscreenButton::resetEventValues() {
    _candidatePointIdx = -1;
    _found = false;
}

TouchscreenVirtualPadDevice::TouchscreenButtonsManager::TouchscreenButtonsManager() {}

void TouchscreenVirtualPadDevice::TouchscreenButtonsManager::addButton(
        TouchscreenVirtualPadDevice::TouchscreenButton button) {
    buttons.push_back(button);
}

void TouchscreenVirtualPadDevice::TouchscreenButtonsManager::resetEventValues() {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        button.resetEventValues();
    }
}

bool
TouchscreenVirtualPadDevice::TouchscreenButtonsManager::processOngoingTouch(glm::vec2 thisPoint,
                                                                            int thisPointId) {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];

        if (!button._found && button.hasValidTouch && button.currentTouchId == thisPointId) {
            // valid if it's an ongoing touch
            button._found = true;
            button.touchUpdate(thisPoint);
            return true;
        }
    }
    return false;

}

bool TouchscreenVirtualPadDevice::TouchscreenButtonsManager::findStartingTouchPointCandidate(
        glm::vec2 thisPoint, int thisPointId, int thisPointIdx, std::map<int, TouchType> &globalUnusedTouches) {

    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        if (!button._found && button._candidatePointIdx == -1 && button.touchBeginIsValid(thisPoint)) {
            if (!globalUnusedTouches.count(thisPointId) ) {
                button._candidatePointIdx = thisPointIdx;
                return true;
            } else if (globalUnusedTouches[thisPointId] == button.touchType) {
                button._candidatePointIdx = thisPointIdx;
                return true;
            }
        }
    }
    return false;

}

void TouchscreenVirtualPadDevice::TouchscreenButtonsManager::saveUnusedTouches(
        std::map<int, TouchscreenVirtualPadDevice::TouchType> &unusedTouchesInEvent, glm::vec2 thisPoint,
        int thisPointId) {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        if (button.touchBeginIsValid(thisPoint)) {
            unusedTouchesInEvent[thisPointId] = button.touchType;
            return;
        }
    }

}

void TouchscreenVirtualPadDevice::TouchscreenButtonsManager::processBeginOrEnd(
        glm::vec2 thisPoint, const QList<OverteTouchPoint>& tPoints, std::map<int, TouchType> globalUnusedTouches) {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        if (!button._found) {
            if (button._candidatePointIdx != -1) {
                button.currentTouchId = tPoints[button._candidatePointIdx].id();
                globalUnusedTouches.erase(button.currentTouchId);
                const auto position = touchPosition(tPoints[button._candidatePointIdx]);
                thisPoint.x = position.x();
                thisPoint.y = position.y();
                button.touchBegin(thisPoint);
            } else {
                if (button.hasValidTouch) {
                    button.touchEnd();
                }
            }
        }
    }

}

void TouchscreenVirtualPadDevice::TouchscreenButtonsManager::endTouchForAll() {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        button.touchEnd();
    }
}

bool TouchscreenVirtualPadDevice::TouchscreenButtonsManager::touchBeginInvalidForAllButtons(glm::vec2 touchPoint) {
    for(int i = 0; i < buttons.size(); i++) {
        TouchscreenButton &button = buttons[i];
        if (button.touchBeginIsValid(touchPoint)) {
            return false;
        }
    }
    return true;
}
