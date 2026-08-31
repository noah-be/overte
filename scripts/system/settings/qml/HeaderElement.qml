import QtQuick 2.15
import QtQuick.Controls 2.15
import TabletScriptingInterface 1.0
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

	Rectangle {
		id: tabletHomeButton
		visible: currentPage == "Settings"
		height: Math.max(40, touchMetrics.adaptiveMinimumControlHeight)
		width: 96
		x: 10
		anchors.verticalCenter: parent.verticalCenter
		radius: 6
		color: tabletHomeMouseArea.pressed ? "#169c86" : "#1fc6a6"

		Text {
			anchors.centerIn: parent
			text: qsTr("HOME")
			color: "#10252d"
			font.bold: true
			font.pixelSize: Math.round(18 * touchMetrics.textScale)
		}

		MouseArea {
			id: tabletHomeMouseArea
			objectName: "nav.home"
			anchors.fill: parent
			activeFocusOnTab: visible
			Accessible.role: Accessible.Button
			Accessible.name: qsTr("Tablet home")
			Accessible.description: qsTr("Return to the tablet application list")
			function activate() {
				Tablet.getTablet("com.highfidelity.interface.tablet.system").gotoHomeScreen()
			}
			Accessible.onPressAction: activate()
			onClicked: activate()
			Keys.onReturnPressed: activate()
			Keys.onEnterPressed: activate()
			Keys.onSpacePressed: activate()
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

	HifiControls.Button {
		id: semanticHomeButton
		objectName: "nav.home"
		visible: touchMetrics.directTouch && currentPage === "Settings"
		text: qsTr("Home")
		width: Math.max(88, touchMetrics.adaptiveMinimumControlHeight * 2)
		height: Math.max(44, touchMetrics.adaptiveMinimumControlHeight)
		anchors.right: parent.right
		anchors.rightMargin: 10
		anchors.verticalCenter: parent.verticalCenter
		Accessible.role: Accessible.Button
		Accessible.name: qsTr("Tablet home")
		Accessible.description: qsTr("Return to the tablet application list")
		androidClickAction: function() {
			Tablet.getTablet("com.highfidelity.interface.tablet.system").gotoHomeScreen();
		}
	}
}
