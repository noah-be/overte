import QtQuick 2.15
import QtQuick.Controls 2.15
import controlsUit 1.0 as HifiControls

Item {
	height: 60;
	width: parent.width;
	id: root;
	HifiControls.TouchUiMetrics { id: touchMetrics }

	Rectangle {
		anchors.fill: parent;
		color: "black";
	}

	Image {
		source: "../img/back_arrow.png";
		anchors.verticalCenter: parent.verticalCenter;
		height: Math.max(40, touchMetrics.adaptiveMinimumControlHeight);
		width: height;
		x: currentPage == "Settings" ? -40 : 10;

		Behavior on x {
			NumberAnimation {
				duration: 200;
				easing.type: Easing.InOutCubic;
			}
		}

		MouseArea {
			objectName: "nav.back"
			anchors.fill: parent;
			hoverEnabled: touchMetrics.hoverSupported
			activeFocusOnTab: parent.visible
			Accessible.role: Accessible.Button
			Accessible.name: qsTr("Back to settings")
			Accessible.description: qsTr("Return to the settings category list")
			Accessible.onPressAction: currentPage = "Settings"
			onClicked: {
				currentPage = "Settings";
			}
			Keys.onReturnPressed: currentPage = "Settings"
			Keys.onEnterPressed: currentPage = "Settings"
			Keys.onSpacePressed: currentPage = "Settings"
		}
	}

	Text {
		text: currentPage;
		color: "white";
		font.pixelSize: Math.round(26 * touchMetrics.textScale);
		anchors.horizontalCenter: parent.horizontalCenter;
		anchors.verticalCenter: parent.verticalCenter;
		horizontalAlignment: Text.AlignHCenter;
	}
}
