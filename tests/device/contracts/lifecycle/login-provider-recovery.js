(function() {
    // Explicit loader, visual and activity boundaries; original handlers below.
    var root = {}, loginDialog = {};
    var bodyLoader = {
        calls: [],
        setSource: function(path, arguments) { this.calls.push({path: path, arguments: arguments}); }
    };
    var loggingInBody = {}, loggingInSpinner = {}, loggingInText = {}, okButton = {};
    var UserActivityLogger = { calls: [], logAction: function(event, data) { this.calls.push(data); } };
    /* ORIGINAL_HANDLERS */
    function check(condition) { if (!condition) throw new Error("PROVIDER_RECOVERY_CONTRACT_FAILED"); }
    for (var popup of [false, true]) {
        for (var provider of [false, true]) {
            loggingInBody = {withOculus: provider, withSteam: false, loginDialogPoppedUp: popup};
            bodyLoader.calls = []; UserActivityLogger.calls = [];
            onHandleCreateFailed();
            check(bodyLoader.calls.length === (provider ? 1 : 0));
            check(UserActivityLogger.calls.length === (provider && popup ? 1 : 0));
            if (provider) {
                var created = bodyLoader.calls[0];
                check(created.path === "CompleteProfileBody.qml");
                check(created.arguments.errorString === "Account creation failed. Check your connection and try again.");
                check(created.arguments.loginDialog === loginDialog && created.arguments.root === root);
                check(created.arguments.withOculus === true && created.arguments.withSteam === false);
            }
        }
        for (var linkMode of ["oculus", "steam", "ordinary"]) {
            loggingInBody = {linkOculus: linkMode === "oculus", linkSteam: linkMode === "steam", loginDialogPoppedUp: popup};
            bodyLoader.calls = []; UserActivityLogger.calls = [];
            loggingInSpinner.visible = true; okButton.visible = false; loggingInText.text = "";
            onHandleLinkFailed();
            check(loggingInSpinner.visible === false);
            check(bodyLoader.calls.length === (linkMode === "ordinary" ? 1 : 0));
            check(UserActivityLogger.calls.length === (linkMode !== "ordinary" && popup ? 1 : 0));
            check(okButton.visible === (linkMode === "oculus"));
            if (linkMode === "ordinary") {
                var linked = bodyLoader.calls[0];
                check(linked.path === "LinkAccountBody.qml");
                check(linked.arguments.errorString === "Account linking failed. Check your connection and try again.");
                check(linked.arguments.loginDialog === loginDialog && linked.arguments.bodyLoader === bodyLoader);
                check(linked.arguments.linkOculus === false && linked.arguments.linkSteam === false);
            }
            if (linkMode === "oculus") check(loggingInText.text === "Oculus failed to link");
        }
    }
    return true;
})();
