// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

"use strict";

function validate(message) {
    if (!message || typeof message !== "object" ||
            typeof message.method !== "string" || message.method.length === 0) {
        return null;
    }
    if (message.params !== undefined &&
            (!message.params || typeof message.params !== "object" || Array.isArray(message.params))) {
        return null;
    }
    return {
        method: message.method,
        params: message.params || {}
    };
}

module.exports = validate;
