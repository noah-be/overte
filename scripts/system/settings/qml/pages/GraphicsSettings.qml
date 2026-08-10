import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3
import "../"

Flickable {
    SettingsTouchConfiguration { id: touchConfiguration }

    property var verticalScrollBarWidth: 20;
    property bool hasPresetBeenModified: false;
    property bool isChangingPreset: false;

    id: graphicsPage;
    visible: currentPage == "Graphics";
    width: parent.width;
    Layout.fillHeight: true;
    y: header.height + 10;
    contentWidth: parent.width;
    contentHeight: graphicsPageColumn.height;
    clip: true;
    flickDeceleration: 4000;

    Timer {
        id: verticalScrollBarInitialVisibilityTimer;
        interval: 200;
        running: false;
        repeat: false;

        onTriggered: {
            verticalScrollBarWidth = 15;
        }
    }

    onVisibleChanged: {
        // Set the initial values for the variables.
        verticalScrollBarWidth = 20;

        // We are leaving the page, don't animate. 
        if (!visible) return;

        // We have opened the page
        // Start the visibility effect timers.
        verticalScrollBarInitialVisibilityTimer.running = true;
    }

    ScrollBar.vertical: ScrollBar {
        id: scrollBar;
        policy: Qt.ScrollBarAlwaysOn;

        background: Rectangle {
            implicitWidth: verticalScrollBarWidth;
            color: "transparent";
            radius: 5;
            visible: scrollBar.visible;

            Behavior on implicitWidth {
                NumberAnimation {
                    duration: 300;
                    easing.type: Easing.InOutCubic;
                }
            }
        }
    }

    Column {
        id: graphicsPageColumn;
        width: parent.width - 20;
        anchors.horizontalCenterOffset: -5
        anchors.horizontalCenter: parent.horizontalCenter;
        spacing: 10;

        // Graphics Presets
        SettingComboBox {
            id: graphicsPresetCombobox;
            settingText: "Graphics preset";
            optionIndex: Performance.getPerformancePreset() - 1;
            options: ["Low Power", "Low", "Medium", "High", "Custom"];

            onValueChanged: {
                Performance.setPerformancePreset(index + 1);
                if (index !== 4) switchToAGraphicsPreset();
            }
        }

        // Rendering Effects
        SettingBoolean {
            settingText: "Local Lights";
            settingEnabledCondition: () => { return Render.localLightingEnabled }

            onSettingEnabledChanged: {
                Render.localLightingEnabled = settingEnabled;
            }
        }

        SettingBoolean {
            settingText: "Bloom";
            settingEnabledCondition: () => { return Render.bloomEnabled }

            onSettingEnabledChanged: {
                Render.bloomEnabled = settingEnabled;
            }
        }

        SettingBoolean {
            settingText: "Custom Shaders";
            settingEnabledCondition: () => { return Render.proceduralMaterialsEnabled}

            onSettingEnabledChanged: {
                Render.proceduralMaterialsEnabled = settingEnabled;
            }
        }

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            font.pixelSize: 16
            color: "white"
            text: "Custom shaders are currently always unlit when deferred rendering is disabled."
        }

        SettingBoolean {
            settingText: "Deferred Rendering";
            settingEnabledCondition: function () { return Render.renderMethod === 0; }

            onSettingEnabledChanged: {
                Render.renderMethod = settingEnabled ? 0 : 1;
            }
        }

        Text {
            width: parent.width
            wrapMode: Text.Wrap
            font.pixelSize: 16
            color: "white"
            text: "May affect performance, especially on mobile devices. Not compatible with MSAA. Haze is always enabled when not using deferred rendering."
        }

        // Rendering Effects sub options
        AdvancedOptions {
            id: renderingEffectsAdvancedOptions;
            isEnabled: Render.renderMethod === 0;

            SettingBoolean {
                settingText: "Shadows";
                settingEnabledCondition: () => { return Render.shadowsEnabled }

                onSettingEnabledChanged: {
                    Render.shadowsEnabled = settingEnabled;
                }
            } 

            SettingBoolean {
                settingText: "Ambient Occlusion";
                settingEnabledCondition: () => { return Render.ambientOcclusionEnabled }

                onSettingEnabledChanged: {
                    Render.ambientOcclusionEnabled = settingEnabled;
                }
            }

            SettingBoolean {
                settingText: "Haze";
                settingEnabledCondition: () => { return Render.hazeEnabled }

                onSettingEnabledChanged: {
                    Render.hazeEnabled = settingEnabled;
                }
            }
        }

        SettingSlider {
            settingText: "Field of View";
            sliderStepSize: 1;
            minValue: 20;
            maxValue: 130;
            settingValue: Render.verticalFieldOfView.toFixed(1);
            roundDisplay: 0;

            onSliderValueChanged: {
                Render.verticalFieldOfView = value.toFixed(1);
            }
        }

        SettingSlider {
            settingText: "Resolution scale";
            sliderStepSize: 0.1;
            minValue: 0.1;
            maxValue: 2;
            settingValue: Render.viewportResolutionScale.toFixed(1)

            onSliderValueChanged: {
                Render.viewportResolutionScale = value.toFixed(1)
            }
        }

        SettingComboBox {
            id: picoResolutionScale
            visible: touchConfiguration.showPicoResolutionSettings
            settingText: "Pico render resolution"
            options: ["50%", "60%", "70%", "75%", "80%", "85%", "100%"]
            property var scales: [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 1.00]
            property bool initialized: false
            property int pendingIndex: -1

            function syncFromSettings() {
                var current = Number(Settings.getValue("pico/renderScale", 0.80))
                var closest = 0
                var distance = Math.abs(scales[0] - current)
                for (var i = 1; i < scales.length; ++i) {
                    var candidateDistance = Math.abs(scales[i] - current)
                    if (candidateDistance < distance) {
                        closest = i
                        distance = candidateDistance
                    }
                }
                setOptionIndex(closest)
                initialized = true
            }

            Component.onCompleted: syncFromSettings()

            onValueChanged: {
                if (!initialized || scales[index] ===
                        Number(Settings.getValue("pico/renderScale", 0.80))) {
                    return
                }
                pendingIndex = index
            }
        }

        Column {
            id: picoResolutionConfirmation
            width: parent.width
            spacing: 8
            visible: touchConfiguration.showPicoResolutionSettings && picoResolutionScale.pendingIndex >= 0

            Text {
                width: parent.width
                wrapMode: Text.Wrap
                font.pixelSize: 18
                color: "#ffcc66"
                text: picoResolutionScale.pendingIndex >= 0
                    ? "Apply " + picoResolutionScale.options[picoResolutionScale.pendingIndex]
                        + "? Changing the Pico render resolution restarts the app automatically."
                    : "Changing the Pico render resolution restarts the app automatically."
            }

            Row {
                spacing: 12

                Button {
                    text: "Apply and restart"
                    onClicked: {
                        var selectedIndex = picoResolutionScale.pendingIndex
                        if (selectedIndex < 0) {
                            return
                        }
                        Settings.setValue("pico/renderScale",
                            picoResolutionScale.scales[selectedIndex])
                        Window.restartApplication(AddressManager.href)
                    }
                }

                Button {
                    text: "Cancel"
                    onClicked: {
                        picoResolutionScale.pendingIndex = -1
                        picoResolutionScale.initialized = false
                        picoResolutionScale.syncFromSettings()
                    }
                }
            }
        }

        SettingComboBox {
            settingText: "Anti-aliasing";
            optionIndex: Render.antialiasingMode;
            options: ["None", "TAA", "FXAA"];
            disabled: Render.renderMethod;

            onValueChanged: {
                Render.antialiasingMode = index;
            }

            onDisabledChanged: {
                if (disabled) {
                    options = ["MSAA"];
                }
                else {
                    options = ["None", "TAA", "FXAA"];
                }
            }
        }

        SettingComboBox {
            settingText: "LOD Settings";
            options: ["Low Detail", "Medium Detail",  "High Detail" ];
            optionIndex: LODManager.worldDetailQuality;

            onValueChanged: {
                LODManager.worldDetailQuality = index;
            }

            Component.onCompleted: {
                optionIndex = LODManager.worldDetailQuality;
            }
        }

        SettingComboBox {
            settingText: "Refresh rate";
            options: ["Economical", "Interactive", "Real-Time", "Custom"];
            optionIndex: Performance.getRefreshRateProfile();

            onValueChanged: {
                Performance.setRefreshRateProfile(index);
                fpsAdvancedOptions.isEnabled = index == 3;
            }
        }

        AdvancedOptions {
            id: fpsAdvancedOptions;
            isEnabled: Performance.getRefreshRateProfile() === 3;

            SettingNumber {
                settingText: "Focus Active";
                minValue: 5;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(0)

                onValueChanged: {
                    Performance.setCustomRefreshRate(0, value);
                }
            }

            SettingNumber {
                settingText: "Focus Inactive";
                minValue: 1;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(1)

                onValueChanged: {
                    Performance.setCustomRefreshRate(1, value);
                }
            }

            SettingNumber {
                settingText: "Unfocused";
                minValue: 1;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(2)

                onValueChanged: {
                    Performance.setCustomRefreshRate(2, value);
                }
            }

            SettingNumber {
                settingText: "Minimized";
                minValue: 1;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(3)

                onValueChanged: {
                    Performance.setCustomRefreshRate(3, value);
                }
            }

            SettingNumber {
                settingText: "Startup";
                minValue: 1;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(4)

                onValueChanged: {
                    Performance.setCustomRefreshRate(4, value);
                }
            }

            SettingNumber {
                settingText: "Shutdown";
                minValue: 1;
                maxValue: 9999;
                suffixText: "fps";
                settingValue: Performance.getCustomRefreshRate(5)

                onValueChanged: {
                    Performance.setCustomRefreshRate(5, value);
                }
            }
        }

        // Fullscreen Display
        SettingComboBox {
            settingText: "Fullscreen Display";

            Component.onCompleted: {
                var screens = Render.getScreens();
                var selected = Render.getFullScreenScreen();
                setOptions(screens);

                for (let i = 0; screens.length > i; i++) {
                    if (screens[i] == selected) {
                        optionIndex = i;
                        return;
                    }
                }
            }

            onValueChanged: {
                Render.setFullScreenScreen(optionText);
            }
        }

        // Camera clipping
        SettingBoolean {
            settingText: "Allow camera clipping";
            settingEnabledCondition: () => { return !Render.cameraClippingEnabled }

            onSettingEnabledChanged: {
                Render.cameraClippingEnabled = settingEnabled ? 0 : 1;
            }
        }
    }

    onHasPresetBeenModifiedChanged: {
        if (hasPresetBeenModified === true && isChangingPreset === false){
            graphicsPresetCombobox.setOptionIndex(4);
        }
    }

    function switchToAGraphicsPreset(){
        // We need to disable the event updates from settings to detect if we have changed a preset.
        isChangingPreset = true;

        // Change all of the settings to match the preset 
        recursivelyUpdateAllSettings(graphicsPageColumn);
        hasPresetBeenModified = false;

        // "Unmute" the events listening for a preset change.
        isChangingPreset = false;
    }

    function recursivelyUpdateAllSettings(item){
        // In order to update all settings based on current values, 
        // we need to go through all children elements and re-evaluate their settingEnabled value

        // Update all settings options visually to reflect settings
        for (let i = 0; item.children.length > i; i++) {
            var child = item.children[i];

            child.update();

            // Run this function on all of this elements children.
            recursivelyUpdateAllSettings(child);
        }
    }
}
