//
//  Created by Gabriel Calero & Cristian Duarte on 01/16/2018
//  Copyright 2018 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#pragma once
#include <stdint.h>
#include <DependencyManager.h>

#include <GLMHelpers.h>
#if defined(ANDROID_APP_PHONE_INTERFACE)
#include "PhoneVirtualPadLayout.h"
#endif

namespace VirtualPad {
    class Instance {
    public:
        virtual bool isBeingTouched();
        virtual void setBeingTouched(bool touched);
        virtual void setFirstTouch(glm::vec2 point);
        virtual glm::vec2 getFirstTouch();
        virtual void setCurrentTouch(glm::vec2 point);
        virtual glm::vec2 getCurrentTouch();
        virtual bool isShown();
        virtual void setShown(bool show);
    private:
#if defined(ANDROID_APP_PHONE_INTERFACE)
        bool _isBeingTouched { false };
        glm::vec2 _firstTouch { 0.0f };
        glm::vec2 _currentTouch { 0.0f };
        bool _shown { false };
#else
        bool _isBeingTouched;
        glm::vec2 _firstTouch;
        glm::vec2 _currentTouch;
        bool _shown;
#endif
    };

    class Manager : public QObject, public Dependency {
        Q_OBJECT
        SINGLETON_DEPENDENCY
        Manager();
        Manager(const Manager& other) = delete;
    public:
        static Manager& instance();
        Instance* getLeftVirtualPad();
        bool isEnabled();
        void enable(bool enable);
        bool isHidden();
        void hide(bool hide);
        int extraBottomMargin();
        void setExtraBottomMargin(int margin);

        enum Button {
            JUMP,
            HANDSHAKE
        };

        glm::vec2 getButtonPosition(Button button);
        void setButtonPosition(Button button, glm::vec2 point);

        void requestHapticFeedback(int duration);
#if defined(ANDROID_APP_PHONE_INTERFACE)
        void publishPhoneLayout(const PhoneLayout& layout) { _phoneLayout.publish(layout); }
        PhoneLayout getPhoneLayout() const { return _phoneLayout.read(); }
#endif

        static const float DPI;
        static const float BASE_DIAMETER_PIXELS;
        static const float BASE_MARGIN_PIXELS;
        static const float STICK_RADIUS_PIXELS;
        static const float BTN_TRIMMED_RADIUS_PIXELS;
        static const float BTN_FULL_PIXELS;
        static const float BTN_BOTTOM_MARGIN_PIXELS;
        static const float BTN_RIGHT_MARGIN_PIXELS;

    signals:
        void hapticFeedbackRequested(int duration);

    private:
        Instance _leftVPadInstance;
        bool _enabled { true };
        bool _hidden;
        int _extraBottomMargin { 0 };
        std::map<Button, glm::vec2> _buttonsPositions;
#if defined(ANDROID_APP_PHONE_INTERFACE)
        PhoneLayoutMailbox _phoneLayout;
#endif
    };
}
