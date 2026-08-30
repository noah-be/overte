import QtQuick 2.7
import "../../controlsUit" as HifiControls

HifiControls.TouchUiMetrics {
    // Pico's concrete HMD preferences are registered in the real
    // "VR Movement" section; the legacy "HMD" category does not exist.
    readonly property var allowedCategories: {
        var categories = []
        // Keep the contract-bearing section inside Pico's initially visible
        // tablet viewport.  The legacy preference dialog does not expose
        // semantic controls for scrolling to an off-screen category.
        if (profile.hmdPreferencesAvailable) {
            categories.push("VR Movement")
        }
        if (profile.userInterfacePreferencesAvailable) {
            categories.push("User Interface")
        }
        categories.push("Mouse Sensitivity")
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
        ? ({ "VR Movement": "settings.hmd-preferences" }) : ({})

    function admits(category) {
        return typeof category === "string" && allowedCategories.indexOf(category) !== -1
    }
}
