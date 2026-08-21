import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.3
import controlsUit 1.0 as HifiControls

ScrollView {
	width: parent.width
	height: parent.height
	y: header.height
	id: root

	HifiControls.TouchUiMetrics { id: touchMetrics }

	ScrollBar.vertical: HifiControls.ScrollBar { }

	function revealFocusedControl() {
		if (!touchMetrics.directTouch || !root.contentItem || !root.Window.window) {
			return
		}
		var focusedItem = root.Window.window.activeFocusItem
		if (focusedItem) {
			touchMetrics.ensureVisible(root.contentItem, focusedItem)
		}
	}

	Connections {
		target: root.Window.window
		function onActiveFocusItemChanged() {
			Qt.callLater(root.revealFocusedControl)
		}
	}

	ColumnLayout {
		width: parent.width
		anchors.horizontalCenter: parent.horizontalCenter
		spacing: 0
	}

	// Append children made using this custom element to the ColumnLayout.
	Component.onCompleted: {
		if (root.contentItem) {
			root.contentItem.pressDelay = touchMetrics.pressDelay
			root.contentItem.flickDeceleration = touchMetrics.flickDeceleration
			root.contentItem.maximumFlickVelocity = touchMetrics.maximumFlickVelocity
		}
		while (root.contentChildren.length > 1){
			root.contentChildren[2].parent = root.contentChildren[0]
		}
	}
}
