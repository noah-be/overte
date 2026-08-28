//
//  TouchscreenVirtualPadDevice.h
//  input-plugins/src/input-plugins
//
//  Created by Triplelexx on 1/31/16.
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#ifndef hifi_TouchscreenVirtualPadDevice_h
#define hifi_TouchscreenVirtualPadDevice_h

#include <controllers/InputDevice.h>
#include "InputPlugin.h"
#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#include <QtGui/QEventPoint>
#include <QtGui/QInputDevice>
#include <QtGui/QTouchEvent>
using OverteTouchPoint = QEventPoint;
#else
#include <QtGui/qtouchdevice.h>
#include <QtGui/QTouchEvent>
using OverteTouchPoint = QTouchEvent::TouchPoint;
#endif
#include <QtCore/QList>
#include <QtCore/QSize>
#include "VirtualPadManager.h"

class QTouchEvent;
class QGestureEvent;

class TouchscreenVirtualPadDevice : public InputPlugin {
Q_OBJECT
public:

    // Plugin functions
    virtual void init() override;
    virtual void resize();
    virtual bool isSupported() const override;
    virtual const QString getName() const override { return NAME; }

    bool isHandController() const override { return false; }

    virtual void pluginFocusOutEvent() override { _inputDevice->focusOutEvent(); }
    virtual void pluginUpdate(float deltaTime, const controller::InputCalibrationData& inputCalibrationData) override;

    void touchBeginEvent(const QTouchEvent* event);
    void touchEndEvent(const QTouchEvent* event);
    void touchUpdateEvent(const QTouchEvent* event);
    void touchGestureEvent(const QGestureEvent* event);

    static const char* NAME;

    int _viewTouchUpdateCount;
    enum TouchAxisChannel {
        LX,
        LY,
        RX,
        RY,
        PINCH_OUT,
        PINCH_IN
    };

    enum TouchButtonChannel {
        JUMP,
        RB
    };

protected:

    class InputDevice : public controller::InputDevice {
    public:
        InputDevice() : controller::InputDevice("TouchscreenVirtualPad") {}
    private:
        // Device functions
        virtual controller::Input::NamedVector getAvailableInputs() const override;
        virtual QString getDefaultMappingConfig() const override;

        virtual bool triggerHapticPulse(float strength, float duration, uint16_t index) override;
        virtual void update(float deltaTime, const controller::InputCalibrationData& inputCalibrationData) override;
        virtual void focusOutEvent() override;

#if defined(Q_OS_IOS)
        float _jumpReleaseDelayMs { 0.0f };
        bool _jumpReleaseAwaitingMapperSample { false };
#endif

        friend class TouchscreenVirtualPadDevice;

        controller::Input makeInput(TouchAxisChannel axis) const;
        controller::Input makeInput(TouchButtonChannel button) const;
    };

public:
    const std::shared_ptr<InputDevice>& getInputDevice() const { return _inputDevice; }

protected:

    enum TouchType {
        MOVE = 1,
        VIEW,
        JUMP_BUTTON,
        RB_BUTTON
    };

    class TouchscreenButton {
    public:

        TouchscreenButton() {};

        TouchscreenButton(TouchButtonChannel channelIn, TouchType touchTypeIn, float buttonRadiusIn, glm::vec2 buttonPositionIn,
                          std::shared_ptr<InputDevice> inputDeviceIn);

        void touchBegin(glm::vec2 touchPoint);
        void touchUpdate(glm::vec2 touchPoint);
        void touchEnd();
        bool touchBeginIsValid(glm::vec2 touchPoint);

        bool hasValidTouch { false };
        int currentTouchId;

        // per event tmp values
        int _candidatePointIdx { -1 };
        bool _found { false };
        void resetEventValues();

        glm::vec2 buttonPosition;
        float buttonRadius;
        TouchType touchType;
        TouchButtonChannel channel;

        std::shared_ptr<InputDevice> _inputDevice;

    };

    class TouchscreenButtonsManager {
    public:

        TouchscreenButtonsManager();

        QVector<TouchscreenButton> buttons;

        void addButton(TouchscreenButton button);
        int buttonsCount() {
            return buttons.size();
        }

        void resetEventValues();
        bool processOngoingTouch(glm::vec2 thisPoint, int thisPointId);
        bool findStartingTouchPointCandidate(glm::vec2 thisPoint, int thisPointId, int thisPointIdx, std::map<int, TouchType> &globalUnusedTouches);
        void saveUnusedTouches(std::map<int, TouchType> &unusedTouchesInEvent, glm::vec2 thisPoint, int thisPointId);
        void processBeginOrEnd(glm::vec2 thisPoint, const QList<OverteTouchPoint>& tPoints, std::map<int, TouchType> globalUnusedTouches);

        void endTouchForAll();
        bool touchBeginInvalidForAllButtons(glm::vec2 touchPoint);
    };

    float _lastPinchScale { 0.0f };
    float _pinchScale { 0.0f };
    float _pinchOut { 0.0f };
    float _pinchIn { 0.0f };
    float _screenDPI { 0.0f };
    qreal _screenDPIProvided { 0.0 };
    glm::vec2 _screenDPIScale { 0.0f };

    bool _moveHasValidTouch { false };
    glm::vec2 _moveRefTouchPoint;
    glm::vec2 _moveCurrentTouchPoint;
    int _moveCurrentTouchId { -1 };

    bool _viewHasValidTouch { false };
    glm::vec2 _viewRefTouchPoint;
    glm::vec2 _viewCurrentTouchPoint;
    int _viewCurrentTouchId { -1 };

    std::map<int, TouchType> _unusedTouches;

    int _touchPointCount { 0 };
#if defined(Q_OS_IOS)
    uint32_t _touchDiagnosticEventCount { 0 };
#endif
    int _screenWidthCenter { 0 };
    std::shared_ptr<InputDevice> _inputDevice { std::make_shared<InputDevice>() };

    bool _fixedPosition { true };
    glm::vec2 _fixedCenterPosition;
    float _fixedRadius { 0.0f };
    float _fixedRadiusForCalc { 0.0f };
    int _extraBottomMargin {0};
    QSize _controlViewportSize;

    float _buttonRadius { 0.0f };

    TouchscreenButtonsManager _buttonsManager;

    void moveTouchBegin(glm::vec2 touchPoint);
    void moveTouchUpdate(glm::vec2 touchPoint);
    void moveTouchEnd();
    bool moveTouchBeginIsValid(glm::vec2 touchPoint);

    void viewTouchBegin(glm::vec2 touchPoint);
    void viewTouchUpdate(glm::vec2 touchPoint);
    void viewTouchEnd();
    bool viewTouchBeginIsValid(glm::vec2 touchPoint);

    void setupControlsPositions(VirtualPad::Manager& virtualPadManager, bool force = false);

    void processInputDeviceForMove(VirtualPad::Manager& virtualPadManager);
    glm::vec2 clippedPointInCircle(float radius, glm::vec2 origin, glm::vec2 touchPoint);

    void processUnusedTouches(std::map<int, TouchType> unusedTouchesInEvent);

    void processInputDeviceForView();
    void processInputDeviceForPinch();


};

#endif // hifi_TouchscreenVirtualPadDevice_h
