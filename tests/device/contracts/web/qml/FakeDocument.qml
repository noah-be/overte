import QtQuick 2.7
Item {
    property var messages: []
    signal sendToScript(var message)
    function fromScript(message) { messages.push(message); }
}
