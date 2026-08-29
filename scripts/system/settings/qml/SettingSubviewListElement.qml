import QtQuick 2.15
import QtQuick.Layouts 1.3
import TabletScriptingInterface 1.0
import controlsUit 1.0 as HifiControls

Item {
	id: root;
	objectName: semanticId
	property string semanticId: ""
	property color bgColor: index % 2 === 0 ? "transparent" : Qt.rgba(0.12,0.12,0.12,1);
	property int initialTextXPosition;

	width: parent.width;
	height: Math.max(60, touchMetrics.adaptiveMinimumControlHeight);
	activeFocusOnTab: true;
	Accessible.role: Accessible.Button
	Accessible.name: pageName
	Accessible.description: qsTr("Open %1 settings").arg(pageName)
	Accessible.onPressAction: activate()

	HifiControls.TouchUiMetrics { id: touchMetrics }

	function activate() {
		Tablet.playSound(TabletEnums.ButtonClicked);
		if (targetPage !== "") {
			toScript({type:"switchApp", appUrl: targetPage});
			return;
		}
		currentPage = pageName;
	}

	Rectangle {
		id: backgroundElement;
		width: parent.width;
		height: parent.height;
		color: bgColor;
		anchors.fill: parent;

		Behavior on color {
			ColorAnimation {
				duration: 50
				easing.type: Easing.InOutCubic
			}
		}
	}

	Row {
		width: parent.width - 20;
		height: parent.height;
		anchors.centerIn: parent;

		// Image/Icon container
		Item {
			width: 45;
			height: parent.height;

			Image {
				sourceSize.height: 25;
				source: pageIcon;
				anchors.centerIn: parent;
			}
		}

		// Page name
		Text {
			id: pageNameElement
			text: pageName;
			color: "white";
			font.pixelSize: Math.round(24 * touchMetrics.textScale);
			anchors.verticalCenter: parent.verticalCenter;

			// Set a variable to the initial X position, used for animating it on hover.
			Component.onCompleted: {
				initialTextXPosition = x;
			}

			Behavior on x {
				NumberAnimation {
					duration: 50
					easing.type: Easing.InOutCubic
				}
			}
		}
	}



	MouseArea {
		anchors.fill: parent;
		Accessible.ignored: true
		hoverEnabled: touchMetrics.hoverSupported;

		onClicked: {
			root.activate();
		}

		onEntered: {
			backgroundElement.color = "#333";
			pageNameElement.x = initialTextXPosition + 20;
			Tablet.playSound(TabletEnums.ButtonHover);
		}

		onExited: {
			backgroundElement.color = bgColor;
			pageNameElement.x = initialTextXPosition;
		}
	}

	Keys.onReturnPressed: root.activate()
	Keys.onEnterPressed: root.activate()
	Keys.onSpacePressed: root.activate()
}
