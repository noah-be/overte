import Hifi 1.0 as Hifi
import QtQuick 2.7
import ".."

Item {
    id: stats
    objectName: "StatsItem"
    property int modality: Qt.NonModal
    implicitWidth: panel.width
    implicitHeight: panel.height
    z: 10000

    anchors.top: parent ? parent.top : undefined
    anchors.horizontalCenter: parent ? parent.horizontalCenter : undefined
    anchors.topMargin: 12

    Hifi.Stats {
        id: root
        objectName: "Stats"
        implicitWidth: panel.width
        implicitHeight: panel.height

        Rectangle {
            id: panel
            width: columns.width + 20
            height: columns.height + 16
            radius: 8
            color: "#d0101216"
            border.color: "#805e6a72"

            MouseArea {
                anchors.fill: parent
                onClicked: root.expanded = !root.expanded
            }

            Row {
                id: columns
                x: 10
                y: 8
                spacing: 18

                Column {
                    spacing: 2
                    StatText { text: "Present: " + root.presentrate.toFixed(1) + " FPS" }
                    StatText { text: "Render: " + root.renderrate.toFixed(1) + " FPS" }
                    StatText { text: "Game: " + root.gameLoopRate + " Hz" }
                    StatText { text: "GPU: " + root.gpuFrameTime.toFixed(1) + " ms" }
                    StatText { text: "Engine: " + root.engineFrameTime.toFixed(1) + " ms" }
                    StatText {
                        visible: root.expanded
                        text: "Stutter: " + root.stutterrate.toFixed(3)
                    }
                    StatText {
                        visible: root.expanded
                        text: "Dropped/long: " + root.appdropped + "/" + root.longframes
                    }
                }

                Column {
                    spacing: 2
                    StatText {
                        text: "Position: " + root.position.x.toFixed(1) + ", " +
                            root.position.y.toFixed(1) + ", " + root.position.z.toFixed(1)
                    }
                    StatText { text: "Speed/Yaw: " + root.speed.toFixed(1) + " / " + root.yaw.toFixed(1) }
                    StatText { text: "Servers/Avatars: " + root.serverCount + "/" + root.avatarCount }
                    StatText { text: "Entities local/server: " + root.localElements + "/" + root.serverElements }
                    StatText {
                        visible: root.expanded
                        text: "Entity ping/in: " + root.entitiesPing + " ms / " +
                            root.entityPacketsInKbps + " kbps"
                    }
                    StatText {
                        visible: root.expanded
                        text: "Packets in/out: " + root.packetInCount + "/" + root.packetOutCount
                    }
                    StatText {
                        visible: root.expanded
                        text: "Mbps in/out: " + root.mbpsIn.toFixed(2) + "/" + root.mbpsOut.toFixed(2)
                    }
                }

                Column {
                    spacing: 2
                    StatText { text: "Drawcalls: " + root.drawcalls }
                    StatText { text: "Triangles: " + root.triangles }
                    StatText { text: "Rendered/considered: " + root.itemRendered + "/" + root.itemConsidered }
                    StatText { text: "Downloads: " + root.downloads + "/" + root.downloadLimit +
                        " pending " + root.downloadsPending }
                    StatText {
                        visible: root.expanded
                        text: "Processing/pending: " + root.processing + "/" + root.processingPending
                    }
                    StatText {
                        visible: root.expanded
                        text: "GPU textures/buffers: " + root.gpuTextures + "/" + root.gpuBuffers
                    }
                    StatText {
                        visible: root.expanded
                        text: "GPU memory tex/buf: " + root.gpuTextureResidentMemory + "/" +
                            root.gpuBufferMemory + " MB"
                    }
                }
            }
        }
    }
}
