//
//  Button.qml
//
//  Created by David Rowe on 16 Feb 2016
//  Copyright 2016 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import QtQuick 2.7
import QtQuick.Controls 2.3 as Original
import TabletScriptingInterface 1.0

import "../stylesUit"

Original.Button {
    id: control;

    property int color: 0
    property int colorScheme: hifi.colorSchemes.light
    property string fontFamily: "Raleway"
    property int fontSize: hifi.fontSizes.buttonLabel
    property bool fontBold: true
    property int radius: hifi.buttons.radius
    property alias implicitTextWidth: buttonText.implicitWidth
    property string buttonGlyph: "";
    property int buttonGlyphSize: 34;
    property int buttonGlyphRightMargin: 0;
    property int fontCapitalization: Font.AllUppercase
    // QML-derived signal handlers do not reliably replace this component's
    // onClicked handler on the Android Qt build.  Let callers that need a
    // guaranteed action route it through the handler that actually receives
    // the signal.
    property var androidClickAction: null

    width: hifi.dimensions.buttonWidth
    height: Math.max(hifi.dimensions.controlLineHeight,
        touchMetrics.adaptiveMinimumControlHeight)
    hoverEnabled: touchMetrics.hoverSupported

    property size implicitPadding: Qt.size(20, 16)
    property int implicitWidth: buttonContentItem.implicitWidth + implicitPadding.width
    property int implicitHeight: buttonContentItem.implicitHeight + implicitPadding.height

    HifiConstants { id: hifi }
    TouchUiMetrics { id: touchMetrics }

    onHoveredChanged: {
        if (hovered) {
            Tablet.playSound(TabletEnums.ButtonHover);
        }
    }

    onFocusChanged: {
        // A controller hover also moves Qt focus. Playing both transitions
        // produces duplicate hover sounds for one visual selection.
        if (focus && Qt.platform.os !== "android") {
            Tablet.playSound(TabletEnums.ButtonHover);
        }
    }

    onClicked: {
        if (Qt.platform.os === "android") {
            console.info("PICO_QML_BUTTON clicked text=" + control.text);
            if (control.androidClickAction) {
                control.androidClickAction();
            }
        }
        Tablet.playSound(TabletEnums.ButtonClick);
    }

    // On mobile VR the controller pose can advance noticeably between the
    // trigger press and release frames. Qt then cancels an AbstractButton
    // press even though the user began the click on the button. Treat that
    // cancellation as activation on Android so tablet buttons remain usable.
    onCanceled: {
        if (Qt.platform.os === "android") {
            console.info("PICO_QML_BUTTON canceled->clicked text=" + control.text);
            control.clicked();
        }
    }

    background: Rectangle {
        radius: control.radius

        border.width: (control.color === hifi.buttons.none ||
                       (control.color === hifi.buttons.noneBorderless && control.hovered) ||
                       (control.color === hifi.buttons.noneBorderlessWhite && control.hovered) ||
                       (control.color === hifi.buttons.noneBorderlessGray && control.hovered)) ? 1 : 0;
        border.color: control.color === hifi.buttons.noneBorderless ? hifi.colors.blueHighlight :
                                                                      (control.color === hifi.buttons.noneBorderlessGray ? hifi.colors.baseGray : hifi.colors.white);

        gradient: Gradient {
            GradientStop {
                position: 0.2
                color: {
                    if (!control.enabled) {
                        hifi.buttons.disabledColorStart[control.colorScheme]
                    } else if (control.pressed) {
                        hifi.buttons.pressedColor[control.color]
                    } else if (control.hovered) {
                        hifi.buttons.hoveredColor[control.color]
                    } else {
                        hifi.buttons.colorStart[control.color]
                    }
                }
            }
            GradientStop {
                position: 1.0
                color: {
                    if (!control.enabled) {
                        hifi.buttons.disabledColorFinish[control.colorScheme]
                    } else if (control.pressed) {
                        hifi.buttons.pressedColor[control.color]
                    } else if (control.hovered) {
                        hifi.buttons.hoveredColor[control.color]
                    } else {
                        hifi.buttons.colorFinish[control.color]
                    }
                }
            }
        }
    }

    contentItem: Item {
        id: buttonContentItem
        implicitWidth: (buttonGlyph.visible ? buttonGlyph.implicitWidth : 0) + buttonText.implicitWidth
        implicitHeight: buttonText.implicitHeight
        TextMetrics {
            id: buttonGlyphTextMetrics;
            font: buttonGlyph.font;
            text: buttonGlyph.text;
        }
        HiFiGlyphs {
            id: buttonGlyph;
            visible: control.buttonGlyph !== "";
            text: control.buttonGlyph === "" ? hifi.glyphs.question : control.buttonGlyph;
            // Size
            size: control.buttonGlyphSize;
            // Anchors
            anchors.right: buttonText.left;
            anchors.rightMargin: control.buttonGlyphRightMargin
            anchors.top: parent.top;
            anchors.bottom: parent.bottom;
            // Style
            color: enabled ? hifi.buttons.textColor[control.color]
                           : hifi.buttons.disabledTextColor[control.colorScheme];
            // Alignment
            horizontalAlignment: Text.AlignHCenter;
            verticalAlignment: Text.AlignVCenter;
        }

        TextMetrics {
            id: buttonTextMetrics;
            font: buttonText.font;
            text: buttonText.text;
        }
        Text {
            id: buttonText;
            width: buttonTextMetrics.width
            anchors.verticalCenter: parent.verticalCenter;
            font.capitalization: control.fontCapitalization
            color: enabled ? hifi.buttons.textColor[control.color]
                           : hifi.buttons.disabledTextColor[control.colorScheme]
            font.family: control.fontFamily
            font.pixelSize: control.fontSize
            font.bold: control.fontBold
            verticalAlignment: Text.AlignVCenter
            horizontalAlignment: Text.AlignHCenter
            text: control.text
            Component.onCompleted: {
                setTextPosition();
            }
            onTextChanged: {
                setTextPosition();
            }
            function setTextPosition() {
                // force TextMetrics to re-evaluate the text field and glyph sizes
                // as for some reason it's not automatically being done.
                buttonGlyphTextMetrics.text = buttonGlyph.text;
                buttonTextMetrics.text = text;
                if (control.buttonGlyph !== "") {
                    buttonText.x = buttonContentItem.width/2 - buttonTextMetrics.width/2 + (buttonGlyphTextMetrics.width + control.buttonGlyphRightMargin)/2;
                } else {
                    buttonText.anchors.centerIn = parent;
                }
            }
        }
    }
}
