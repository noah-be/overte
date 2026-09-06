import QtQml

// Selected production handler inserted verbatim. Field/focus/dismiss are
// explicit boundaries; this does not claim native UI/IME or full dialog load.
QtObject {
    id: phoneLogin
    property bool domainLogin: true
    property bool waiting: true
    property bool requestSubmitted: true
    property bool closing: false
    property int dismissals: 0
    property int selections: 0
    property int focuses: 0
    function dismiss() { dismissals++; closing = true; }
    property QtObject errorText: QtObject { property string text: "" }
    property QtObject password: QtObject {
        function selectAll() { phoneLogin.selections++; }
        function forceActiveFocus() { phoneLogin.focuses++; }
    }
    property QtObject loginDialog: QtObject { signal handleDomainLoginFailed(string reason) }
    function deliver(reason) { loginDialog.handleDomainLoginFailed(reason); }
    property Connections receiver: Connections {
        target: loginDialog
        /* ORIGINAL_HANDLER */
    }
    function message() { return errorText.text; }
}
