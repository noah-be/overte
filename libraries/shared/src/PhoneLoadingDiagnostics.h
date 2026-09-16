// Local opt-in loading diagnostics: numeric records only, no URLs or identifiers.
#pragma once
#if defined(ANDROID_APP_PHONE_INTERFACE)
#include <QDebug>
#include <QString>
#include <sys/system_properties.h>
inline bool phoneLoadingDiagnosticsEnabled() {
    static const bool enabled = [] {
        char value[PROP_VALUE_MAX] {};
        return __system_property_get("debug.overte.loading", value) > 0 && value[0] == '1';
    }();
    return enabled;
}
#define PHONE_LOADING(...) do { if (phoneLoadingDiagnosticsEnabled()) { \
    qInfo().noquote() << "OVT_PHONE_LOADING" << QString::asprintf(__VA_ARGS__); } } while (false)
#else
#define PHONE_LOADING(...) do {} while (false)
#endif
