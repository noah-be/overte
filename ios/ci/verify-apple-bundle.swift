// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0

import Foundation

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data("error: \(message)\n".utf8))
    exit(1)
}

guard CommandLine.arguments.count == 3 else {
    fail("usage: verify-apple-bundle.swift APP_PATH EXPECTED_BUNDLE_ID")
}

let appPath = CommandLine.arguments[1]
let expectedBundleIdentifier = CommandLine.arguments[2]
guard let bundle = Bundle(path: appPath) else {
    fail("Foundation.Bundle cannot open the application bundle")
}
guard bundle.bundleIdentifier == expectedBundleIdentifier else {
    fail("Foundation.Bundle reports an unexpected bundle identifier")
}
guard bundle.object(forInfoDictionaryKey: "CFBundlePackageType") as? String == "APPL" else {
    fail("Foundation.Bundle does not recognize an APPL package")
}
guard let executableURL = bundle.executableURL,
      FileManager.default.isExecutableFile(atPath: executableURL.path) else {
    fail("Foundation.Bundle cannot resolve an executable application binary")
}

print("PASS Apple Foundation recognizes \(expectedBundleIdentifier) as an executable app bundle")
