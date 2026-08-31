# Troubleshoot the iOS port

## The host check fails

Confirm that the command runs on macOS, Xcode is selected, and the reported
Xcode, SDK, CMake, Python, and Conan versions satisfy the build contract. Run
`bootstrap` before dependency resolution.

## Qt validation fails

Set `OVERTE_IOS_QT_ROOT` to the iOS target installation and
`OVERTE_IOS_QT_HOST_ROOT` to the matching macOS host tools. Do not allow a
Homebrew desktop Qt to enter through an incidental `CMAKE_PREFIX_PATH`. See
[`docs/ios/QT_SETUP.md`](../../ios/QT_SETUP.md).

## Configure or build fails

Match the earliest causal error to `ios/first-run-triage.json`. Record the exact
command, source revision, target, Xcode/SDK versions, and smallest relevant CMake
cache excerpt. Later linker errors are not actionable while an earlier recipe or
compile phase is failing.

## A simulator or device crashes

Retain the crash report, bounded console excerpt, screenshot, and reproduction
sequence. Remove tokens, signing material, usernames, full deep links, and
absolute home paths before sharing evidence.
