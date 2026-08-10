import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3
import "../"

Flickable {
    id: interactionPage
    visible: currentPage === "Pico Interaction"
    width: parent.width
    Layout.fillHeight: true
    y: header.height + 10
    contentWidth: parent.width
    contentHeight: settingsColumn.height
    clip: true

    function value(key, fallback) {
        var candidate = Number(Settings.getValue(key, fallback))
        return isFinite(candidate) && candidate >= 0 && candidate <= 1 ? candidate : fallback
    }

    ScrollBar.vertical: ScrollBar { policy: Qt.ScrollBarAlwaysOn }

    Column {
        id: settingsColumn
        width: parent.width - 30
        anchors.horizontalCenter: parent.horizontalCenter
        spacing: 10

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            color: "white"
            font.pixelSize: 18
            text: "Pico controller thresholds. On and off values use hysteresis. "
                + "Changes take effect after restarting Overte."
        }

        SettingSlider {
            settingText: "Laser visible (white)"
            minValue: 0.1; maxValue: 1.0; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/laserOn", 0.10)
            onSliderValueChanged: Settings.setValue("pico/interaction/laserOn", value)
        }

        SettingSlider {
            settingText: "Target selected (green)"
            minValue: 0.1; maxValue: 1.0; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/farSelectOn", 0.50)
            onSliderValueChanged: Settings.setValue("pico/interaction/farSelectOn", value)
        }

        SettingSlider {
            settingText: "Far Grab (purple)"
            minValue: 0.1; maxValue: 1.0; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/farGrabOn", 0.90)
            onSliderValueChanged: Settings.setValue("pico/interaction/farGrabOn", value)
        }

        SettingSlider {
            settingText: "Trigger release"
            minValue: 0.0; maxValue: 0.9; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/triggerOff", 0.05)
            onSliderValueChanged: Settings.setValue("pico/interaction/triggerOff", value)
        }

        SettingSlider {
            settingText: "Grip grab"
            minValue: 0.1; maxValue: 1.0; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/gripOn", 0.50)
            onSliderValueChanged: Settings.setValue("pico/interaction/gripOn", value)
        }

        SettingSlider {
            settingText: "Grip release"
            minValue: 0.0; maxValue: 0.9; sliderStepSize: 0.05; roundDisplay: 2
            settingValue: interactionPage.value("pico/interaction/gripOff", 0.10)
            onSliderValueChanged: Settings.setValue("pico/interaction/gripOff", value)
        }

        Button {
            text: "Reset defaults"
            onClicked: {
                Settings.setValue("pico/interaction/laserOn", 0.10)
                Settings.setValue("pico/interaction/farSelectOn", 0.50)
                Settings.setValue("pico/interaction/farGrabOn", 0.90)
                Settings.setValue("pico/interaction/triggerOff", 0.05)
                Settings.setValue("pico/interaction/gripOn", 0.50)
                Settings.setValue("pico/interaction/gripOff", 0.10)
                Window.restartApplication(AddressManager.href)
            }
        }

        Button {
            text: "Apply and restart"
            onClicked: Window.restartApplication(AddressManager.href)
        }
    }
}
