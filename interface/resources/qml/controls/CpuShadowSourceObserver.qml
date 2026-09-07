// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.5
import QtQml.Models 2.1

// Observe the retained Text/Image/Rectangle/Canvas source tree. The observer
// lives outside that tree, so painting the shadow cannot trigger itself.
Item {
    id: observer
    property Item source
    property var gradientSource: source && source.gradient ? source.gradient : null
    signal changed(bool invalidate)
    visible: false
    onSourceChanged: changed(true)
    Connections {
        target: observer.source
        ignoreUnknownSignals: true
        function onXChanged() { observer.changed(false) }
        function onYChanged() { observer.changed(false) }
        function onWidthChanged() { observer.changed(false) }
        function onHeightChanged() { observer.changed(false) }
        function onVisibleChanged() { observer.changed(true) }
        function onOpacityChanged() { observer.changed(false) }
        function onRotationChanged() { observer.changed(false) }
        function onScaleChanged() { observer.changed(false) }
        function onChildrenChanged() { observer.changed(true) }
        function onColorChanged() { observer.changed(false) }
        function onGradientChanged() { observer.changed(false) }
        function onRadiusChanged() { observer.changed(false) }
        function onTextChanged() { observer.changed(false) }
        function onFontChanged() { observer.changed(false) }
        function onHorizontalAlignmentChanged() { observer.changed(false) }
        function onVerticalAlignmentChanged() { observer.changed(false) }
        function onWrapModeChanged() { observer.changed(false) }
        function onElideChanged() { observer.changed(false) }
        function onMaximumLineCountChanged() { observer.changed(false) }
        function onTextFormatChanged() { observer.changed(false) }
        function onLineHeightChanged() { observer.changed(false) }
        function onStyleChanged() { observer.changed(false) }
        function onStyleColorChanged() { observer.changed(false) }
        function onSourceChanged() { observer.changed(true) }
        function onStatusChanged() { observer.changed(false) }
        function onCurrentFrameChanged() { observer.changed(false) }
        function onFillModeChanged() { observer.changed(false) }
        function onPainted() { observer.changed(false) }
    }
    Connections {
        target: observer.source && observer.source.border ? observer.source.border : null
        ignoreUnknownSignals: true
        function onColorChanged() { observer.changed(false) }
        function onWidthChanged() { observer.changed(false) }
        function onPenChanged() { observer.changed(false) }
    }
    // Gradient stops have no individual notify signals in the tested Qt
    // runtime. Gradient emits one aggregate update after a stop changes.
    Connections {
        target: observer.gradientSource && typeof observer.gradientSource === "object" ? observer.gradientSource : null
        function onUpdated() { observer.changed(false) }
        function onOrientationChanged() { observer.changed(false) }
    }
    Instantiator {
        model: observer.source ? observer.source.children : []
        delegate: Loader {
            id: childObserver
            property Item observed: modelData
            source: "CpuShadowSourceObserver.qml"
            onLoaded: item.source = observed
            onObservedChanged: if (item) item.source = observed
            Connections {
                target: childObserver.item
                function onChanged(invalidate) { observer.changed(invalidate) }
            }
        }
        onObjectAdded: observer.changed(false)
        onObjectRemoved: observer.changed(false)
    }
}
