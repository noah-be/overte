// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <string>

namespace overte { namespace security {
// Closed runtime annotation schema. Build identity is supplied independently by
// each backend. Never retain arbitrary keys, user/session/device identifiers,
// URLs, paths, plugin text or configuration tokens in the annotation queue.
inline bool allowedCrashAnnotation(const std::string& key, const std::string& value) {
    if (key == "program") {
        return value == "interface" || value == "assignment-client" || value == "domain-server";
    }
    if (key == "assignment-client") { return value == "audio-mixer"; }
    if (key == "shutdown" || key == "deadlock" || key == "steam" || key == "hmd") {
        return value == "0" || value == "1";
    }
    if (key == "type") { return value.size() == 1 && value[0] >= '0' && value[0] <= '7'; }
    // Process-local thread numbers support fault attribution; they are not
    // persistent machine fingerprints or account/session identifiers.
    if (key == "main_thread_id" || key == "render_thread_id" || key == "_mod_faulting_tid" || key == "gpu_memory") {
        return !value.empty() && value.size() <= 20 &&
            (value.size() < 20 || value <= "18446744073709551615") &&
            std::all_of(value.begin(), value.end(), [](char c) { return c >= '0' && c <= '9'; });
    }
    return false;
}
}}
