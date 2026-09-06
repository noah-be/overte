import QtQml

// Test-only visual/provider boundaries. The handlers and loadingSuccess body
// are inserted unchanged from production; Connections is the real Qt type.
QtObject {
    id: root
    property var loggingInBody: root
    property bool linkSteam: false
    property bool linkOculus: false
    property bool withSteam: false
    property bool withOculus: false
    property bool loginDialogPoppedUp: false
    property bool isLoggingInToDomain: true
    property string displayName: "domain receiver fixture"
    property var loggingInSpinner: ({ visible: true })
    property var loggingInGlyph: ({ visible: true })
    property var loggingInText: ({ text: "Logging in" })
    property var avatarBoundary: ({ displayName: "" })
    property int successStarts: 0
    property int failureLoads: 0
    property string lastSource: ""
    property var lastProperties: ({})
    property QtObject successTimer: QtObject {
        function start() { root.successStarts++; }
    }
    property QtObject bodyLoader: QtObject {
        function setSource(source, properties) {
            root.failureLoads++;
            root.lastSource = source;
            root.lastProperties = properties;
        }
    }
    /* ORIGINAL_SUCCESS */
    property Connections terminalConnections: Connections {
        target: loginDialog
        /* ORIGINAL_HANDLERS */
    }
}
