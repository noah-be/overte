// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <string>
#include <vector>

namespace overte { namespace ui {
enum class Product { Desktop, Phone, Pico, IOS, Unknown };
enum class Support { Supported, Tolerated, Hidden };

// Define stacks are mutually exclusive. Unknown Android products have no
// implicit Phone/Pico capabilities; an impossible mixed stack fails closed.
inline Product resolveProduct(bool android, bool ios, const std::string& androidApp) {
    if (android && ios) { return Product::Unknown; }
    if (ios) { return Product::IOS; }
    if (!android) { return Product::Desktop; }
    if (androidApp == "phoneInterface") { return Product::Phone; }
    if (androidApp == "picoInterface") { return Product::Pico; }
    return Product::Unknown;
}
inline std::vector<std::string> profileSelectors(Product product, bool gles) {
    std::vector<std::string> result;
    switch (product) {
        case Product::Phone: result = {"android_phoneInterface", "android_interface"}; break;
        case Product::Pico: result = {"android_picoInterface", "android_questInterface"}; break;
        // Explicit, reviewed presentation reuse: these aliases are not native
        // platform identity or permission to enable Android runtime behavior.
        case Product::IOS: result = {"ios", "mobile", "touch", "android_phoneInterface", "android_interface", "webview"}; break;
        case Product::Unknown: result = {"unsupported_product"}; break;
        default: break;
    }
    if (gles) { result.push_back("gles"); }
    if (product == Product::Desktop) { result.push_back("webengine"); }
    return result;
}
inline Support controlSupport(Product product, const std::string& id) {
    if (product == Product::Unknown) { return Support::Hidden; }
    if (id == "app.settings" || id == "nav.back" || id == "nav.close" || id == "nav.home" ||
        id == "settings.audio" || id == "settings.general" || id == "settings.security") {
        return Support::Supported;
    }
    if (id == "settings.controllers" || id == "settings.hmd-preferences" || id == "settings.vr-render-resolution") {
        return product == Product::Pico || product == Product::Desktop ? Support::Supported : Support::Hidden;
    }
    if (id == "settings.graphics") {
        return product == Product::Desktop ? Support::Supported : Support::Tolerated;
    }
    return Support::Hidden;
}
// Retained Preferences registry, not a grant to arbitrary script/settings APIs.
// Mixed categories stay hidden on touch products until their complete controls
// have a useful implementation. Keep the existing desktop registry extensible.
inline bool preferenceAllowed(Product product, const std::string& category, const std::string& name) {
    if (product == Product::Desktop) { return true; }
    if (product == Product::Unknown) { return false; }
    if (category == "HMD" || category == "VR Movement") {
        return controlSupport(product, "settings.hmd-preferences") == Support::Supported;
    }
    if (category == "Controllers" || (category == "Avatar Tuning" && name == "Dominant Hand")) {
        return controlSupport(product, "settings.controllers") == Support::Supported;
    }
    if (category == "User Interface") { return product == Product::Pico; }
    // Oculus desktop plugin, directory pickers and desktop/no-op privacy
    // switches are not made available by a mobile selector alias.
    if (category == "Plugins" || category == "Snapshots" || category == "Privacy") { return false; }
    return category == "Navigation" || category == "Mouse Sensitivity" ||
        category == "Avatar Basics" || category == "Avatar Tuning" ||
        category == "Desktop Movement" || category == "View" ||
        category == "Audio Buffers" || category == "Networking" ||
        category == "Graphics Quality" || category == "Level of Detail Tuning";
}
}} // namespace overte::ui
