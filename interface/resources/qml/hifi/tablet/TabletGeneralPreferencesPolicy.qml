import QtQuick 2.7
import "../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    // Individual hidden controls are still constructed and persisted by the
    // legacy dialog. Admit a whole category only when the selected profile
    // supports its complete behavior.
    readonly property var allowedCategories: {
        var categories = []
        if (profile.navigationPreferencesAvailable) {
            categories.push("Navigation")
        }
        if (profile.userInterfacePreferencesAvailable) {
            categories.push("User Interface")
        }
        categories.push("Mouse Sensitivity")
        if (profile.hmdPreferencesAvailable) {
            categories.push("HMD")
        }
        if (profile.snapshotPreferencesAvailable) {
            categories.push("Snapshots")
        }
        if (profile.privacyPreferencesAvailable) {
            categories.push("Privacy")
        }
        if (profile.pluginPreferencesAvailable) {
            categories.push("Plugins")
        }
        return categories
    }

    readonly property var semanticFeatureIds: profile.hmdPreferencesAvailable
        ? ["settings.hmd-preferences"] : []
    readonly property var categorySemanticIds: profile.hmdPreferencesAvailable
        ? ({ "HMD": "settings.hmd-preferences" }) : ({})

    function admits(category) {
        return typeof category === "string" && allowedCategories.indexOf(category) !== -1
    }
}
