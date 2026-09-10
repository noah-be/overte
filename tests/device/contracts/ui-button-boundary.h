// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QObject>
class TabletBoundary : public QObject {
    Q_OBJECT
public:
    enum Sound { ButtonHover = 1, ButtonClick = 2 };
    Q_ENUM(Sound)
    int actions { 0 }, clicks { 0 };
    Q_INVOKABLE void playSound(int sound) { if (sound == ButtonClick) { ++clicks; } }
    Q_INVOKABLE void action() { ++actions; }
};
