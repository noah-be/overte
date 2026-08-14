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
let appURL = URL(fileURLWithPath: appPath, isDirectory: true)
let infoURL = appURL.appendingPathComponent("Info.plist", isDirectory: false)
let infoData: Data
do {
    infoData = try Data(contentsOf: infoURL)
} catch {
    fail("Foundation cannot read the application Info.plist")
}
let propertyList: Any
do {
    propertyList = try PropertyListSerialization.propertyList(
        from: infoData, options: [], format: nil)
} catch {
    fail("Foundation cannot parse the application Info.plist")
}
guard let info = propertyList as? [String: Any] else {
    fail("Foundation reports a non-dictionary application Info.plist")
}
guard info["CFBundleIdentifier"] as? String == expectedBundleIdentifier else {
    fail("Foundation reports an unexpected application bundle identifier")
}
guard info["CFBundlePackageType"] as? String == "APPL" else {
    fail("Foundation.Bundle does not recognize an APPL package")
}
guard let executableName = info["CFBundleExecutable"] as? String,
      !executableName.isEmpty,
      !executableName.contains("/") else {
    fail("Foundation reports an invalid application executable name")
}
let executableURL = appURL.appendingPathComponent(executableName)
guard FileManager.default.isExecutableFile(atPath: executableURL.path) else {
    fail("Foundation cannot resolve an executable application binary")
}

print("PASS Apple Foundation parses \(expectedBundleIdentifier) as an executable iOS app bundle")
