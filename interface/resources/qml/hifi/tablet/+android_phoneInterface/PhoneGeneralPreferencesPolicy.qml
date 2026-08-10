import QtQuick 2.7

QtObject {
    // Categories are admitted only when their complete behavior is useful on
    // a phone. Individual hidden controls are still loaded and persisted by
    // TabletPreferencesDialog, so this allowlist must stay fail-closed.
    readonly property var allowedCategories: ["Navigation", "Mouse Sensitivity"]

    function admits(category) {
        return typeof category === "string" && allowedCategories.indexOf(category) !== -1
    }
}
