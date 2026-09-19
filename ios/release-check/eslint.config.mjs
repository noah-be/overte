// SPDX-License-Identifier: Apache-2.0
// Runtime-injected Overte globals are intentional. Avoid desktop-global noise.
export default [{
    files: ["**/*.js"],
    languageOptions: {ecmaVersion: "latest", sourceType: "script"},
    rules: {"no-unreachable": "error", "valid-typeof": "error"}
}];
