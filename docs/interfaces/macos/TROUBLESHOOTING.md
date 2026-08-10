# Troubleshoot the macOS port

## `doctor` reports a missing tool

Install the named prerequisite and ensure it is on `PATH`. Conan must report a
2.x version. When the default Qt source is selected, `aqt` must come from the
active Python virtual environment.

## Dependency resolution fails in `libnode`

The current port contains a macOS-local recipe that maps Conan Debug to Node
Debug and other configurations to Node Release. Confirm that the local recipe
was exported and capture the earliest Node build error. Do not diagnose later
CMake errors until dependency resolution succeeds.

## CMake cannot find the Conan preset

Run `macos/build-macos.sh deps` for the same build type and build directory
before `configure` or `build`. Do not mix an old Conan cache with a changed local
recipe without recording the exact source revision.

## The application builds but does not launch

Run the executable from Terminal, retain the crash report and the smallest
relevant console excerpt, and record the app hash and source revision. Remove
usernames, home paths, tokens, complete URLs, and account data before sharing.
