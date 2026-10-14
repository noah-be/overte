<!-- Copyright 2026 Overte e.V. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# World web video capture: investigation and physical observation

Issue [#1179](https://github.com/noah-be/overte/issues/1179) remains open.
This is a preparation procedure, not a device result or a universal browser fix.
The reviewed client checkpoint is
`947c04ee587e1f72556b13f511f9295b1732544b`, tree
`ed0f870f08a370aae4406ac283c2578519406856`. A later integrated candidate must
replace these identities with its actual producer receipts. No SDK build,
installation, device job or remote change was performed for this investigation.

## Actual capture boundary

`IOSWebView.mm` creates one `WKWebView` for the source and keeps the existing
document epoch, source-origin grant, DOM input and real EventBridge. For a world
surface it inserts the view behind Qt in the active root view controller.
`WKWebSnapshot.mm` requests `takeSnapshotWithConfiguration:completionHandler:`
with `afterScreenUpdates = NO`, then converts the returned `UIImage.CGImage`
to a bounded logical-size `QImage`. `IOSWebView::paint` draws that image into
the Qt offscreen surface used by the world entity. There is no independent
video decoder or pixel-buffer composition in this path.

The capture state permits one outstanding operation, at most one new capture
per 100 ms, with a two-second deadline and 2048-pixel edge limit. Source
replacement, navigation and inactive foreground/window state invalidate pending
work. Those protections establish capture ownership; neither a nonempty image
nor advancing snapshots establish that its video rectangle contains video.

`openNative()` presents the same page as a native browser. It is useful for
trusted controls, but a native view displayed over the app does not demonstrate
video in the entity's world texture. The normal native tablet remains useful
independently of this unresolved world capture boundary.

## Public API findings, inspected 2026-10-13

- [WebKit bug 280824](https://bugs.webkit.org/show_bug.cgi?id=280824) remains
  `NEW`, without a linked fix. Its report describes missing HTML video in WK
  snapshots on iOS 17.5 and 18.0. This is relevant prior evidence, not a measured
  result for our candidate or every later OS. A contributor reports that a
  UIKit snapshot view includes video while conversion to a bitmap still fails;
  this is a report, not an Apple API guarantee or a validated Overte workaround.
- The inspected WebKit source is pinned to
  `ec3d95f1d71b2324fbe87bb0cbcdd2372efb8031`:
  [public WK snapshot implementation](https://github.com/WebKit/WebKit/blob/ec3d95f1d71b2324fbe87bb0cbcdd2372efb8031/Source/WebKit/UIProcess/API/Cocoa/WKWebView.mm#L1443)
  and [iOS snapshot implementation](https://github.com/WebKit/WebKit/blob/ec3d95f1d71b2324fbe87bb0cbcdd2372efb8031/Source/WebKit/UIProcess/API/ios/WKWebViewIOS.mm#L4622).
  iOS dispatches through its internal snapshot operation; a window-attached
  branch uses a private Core Animation render-server capture, with a software
  fallback. The hardware-exclusion comment in the Cocoa file describes its
  AppKit branch, not a proof that iOS always takes a software snapshot. WebKit
  main is not the WebKit binary shipped in an arbitrary iPadOS release. These
  private functions cannot be called as a public app-level fix.
- Apple's [afterScreenUpdates contract](https://developer.apple.com/documentation/webkit/wksnapshotconfiguration/afterscreenupdates)
  specifies incorporation of pending screen changes. Changing this flag can
  affect timing; it does not promise inclusion of externally hosted video
  layers. An untested flag change would not close this issue.
- UIKit's [snapshotView](https://developer.apple.com/documentation/uikit/uiview/snapshotview(afterscreenupdates:))
  returns a view representing rendered appearance, rather than the image needed
  by our texture pipeline. [drawHierarchy](https://developer.apple.com/documentation/uikit/uiview/drawhierarchy(in:afterscreenupdates:))
  renders into a graphics context and can report missing hierarchy image data.
  Neither contract establishes reliable WK video bitmap extraction for our
  behind-Qt arrangement. A UIKit overlay is not world composition or occlusion.
- [AVPlayerItemVideoOutput](https://developer.apple.com/documentation/avfoundation/avplayeritemvideooutput)
  exposes frames from a player item owned by that API. Our WK page does not
  expose its player item through the public WK interface. Re-fetching a DOM
  video URL in a second player would need new ownership, authentication,
  synchronization, layout and lifecycle behavior and would not preserve general
  page semantics merely by using this API.
- [ReplayKit](https://developer.apple.com/documentation/replaykit) documents
  incompatibility with AVPlayer content. Screen recording is not a demonstrated
  WK video-texture source and also captures the app rather than its hidden
  individual world web surface.
- A cooperative page can draw video into a canvas using public web APIs
  ([WebKit canvas documentation](https://webkit.org/blog/12058/wide-gamut-2d-graphics-using-html-canvas/)).
  That is a possible separate experiment, not validation of the existing HTML
  video path. Replacing arbitrary pages' videos, layout or controls with injected
  canvas content is not a proven generic fix. Do not alter the reference page
  to conceal the original media-capture failure.

No publicly documented, verified replacement satisfying the same world surface,
normal DOM/input/EventBridge and iOS 17 was established by this review. This
does not prove that no such implementation can exist. The smallest useful next
step is the following comparison in the actual full IPA on the target OS.

## Freeze the candidate and laboratory prerequisites

1. The coordinator first completes the required parent reconciliation, trusted
   workflow gates and actual Apple SDK full-client build. Record actual source
   SHA, tree SHA, ordered source parents, producing workflow/run/attempt, build
   configuration, Qt version and inputs, Xcode/iphoneos SDK and deployment floor,
   IPA SHA256, package verification and any subsequent signing association.
   A GitHub synthetic PR merge SHA must be identified separately from its head.
2. Use the existing private installation and installed-code identity workflow;
   retain its source/IPA binding and observed app version. Record an anonymous
   device reference and actual iPadOS version/build. Historical signed IPAs,
   host receipts or an archive hash without installed-code association cannot
   fill this prerequisite. Keep device selectors and account/provider data
   outside public logs.
3. Reserve the existing iPad laboratory with its normal exclusive ownership.
   Read-only inspection confirmed Jenkins job `overte-ipad` exposes `RUN_MODE`
   choices `readiness`, `full-e2e`, `focused-e2e`, plus `MODULE_IDS` and
   `RESUME_BUILD`. Its public entry does not itself declare source/IPA pins.
   Use `overte-jenkins` for supported Jenkins operations; never invent a world
   video module ID or claim an existing catalog run covers this observation.
   The coordinator must associate this focused observation with the verified
   candidate and existing runner's private artifact context. No job is started
   by this document. A focused diagnostic is not complete catalog qualification.
4. Run the unchanged [shared reference](../../tests/device/fixture/parity/README.md)
   from the exact candidate checkout. The fixture startup verifies its movie.
   Start its documented server only when the coordinator owns the lab. Load
   `webParity.scriptUrl` from ready metadata through normal Running Scripts,
   preserving existing consent. The script makes one local world entity and
   the `WEB TEST` tablet entry; it does not modify domain content.

The distributed MP4 is 50,750 bytes, SHA256
`dbfe374cd12fcd3ad6d4da651b250453b8ec44c4febc7b5c358cc6f7f4675e9b`.
It contains 72 encoded frames at 12 fps, 192 by 108 pixels, H.264 Baseline video
and mono AAC with a 440 Hz tone. Every frame contains an encoded number and a
moving white square. Frames 000-023 are red, 024-047 green, and 048-071 blue.
Use these original bytes, not a canvas rewrite, transcoded file or alternate
stream. Record ready-metadata and fixture source digests as well as the MP4 hash.

## Observe actual world pixels and the native control

1. Keep the world entity visible with surrounding world geometry. Scroll the
   page to its encoded video section and hold a stable view. Use its existing
   `Play with sound` button in the world surface. Record whether the action
   works, any visible `Play failed`/media error, and whether the video rectangle
   is blank, black, static or moving. Do not force successful playback by
   altering autoplay policy or opening a native overlay before this first test.
2. Observe at least three complete six-second loops. In the video rectangle,
   verify red/green/blue transitions, changing **encoded** 000-071 numbers and
   the moving white square. Capture at least two different encoded frames in
   one color phase, plus green and blue frames. Frame loss at our capture rate
   is expected; all 72 frames need not be displayed. Browser time and outside
   DOM status are supporting diagnostics only.
3. Press `Pause` in the world surface. The encoded image must settle and remain
   stable. Press `Seek to blue (4 s)` and allow the pending capture to update;
   the paused video rectangle must show a blue encoded frame, independently
   of the media-status text. Resume and verify continued changes, including
   wrap to red. Record tone separately; audible playback cannot pass pixels.
4. In the same run and IPA, use `WEB TEST` to open the native tablet and perform
   the same movie actions. Keep outcomes separate. Native tablet success with
   world black/static pixels isolates a composition problem; failure on both
   requires investigating playback/transport/input first. Close the tablet
   and repeat the world observation. Opening the world's native browser may
   help diagnose trusted-input behavior, but never substitutes for steps 1-3.
5. Return to DOM input and the real script echo after playback. Check actual
   world pointer/Unicode entry, source `scriptURL` injection, same-origin echo,
   foreign-origin bridge rejection and Back/Reload restoration using the
   shared procedure. Then play, hide/replace/background and resume, and stop
   the reference script. Verify silence, no stale bridge/input/capture work,
   and correct fresh world pixels after restoration. Preserve the existing
   origin, document-epoch and foreground fences throughout.

## Evidence and disposition

Record a private timeline with observation ID, monotonic time, source/IPA/run
receipt references, process continuity, surface (`world` or `tablet`), action,
visible encoded frame/color/square position, playback/input error and audio
observation. Capture the complete display so that the world plane and its
surroundings identify the surface. A crop alone could be native tablet output.
The existing physical Appium adapter advertises `artifact.screenshot`; its
implementation writes `screenshot.png`, overwriting that file on another call.
Use a distinct private artifact directory for each step, retain original bytes
and SHA256, and bind them to the same installed candidate/session. This is an
available capture operation, not an implemented world-video assertion suite.

A recording may supplement the timeline, but recording APIs can omit media.
If a screenshot or recording is blank where a human sees moving video, compare
with an external camera recording of the same controlled physical display
before attributing the blank region to the client. Keep unrelated private UI
out of captured content. Save original evidence and hashes privately; publish
only approved sanitized results and necessary artifact references.

- **Not performed:** any missing candidate, installed-code, lab or observation
  prerequisite. This is the current outcome.
- **World playback blocked:** world Play fails or neither surface plays. Record
  the visible cause; pixel composition remains unmeasured.
- **World composition failed:** tablet displays the encoded movie, while world
  pixels stay black, absent or frozen despite established playback and live DOM.
  Retain world and tablet evidence from the same version and reopen technical
  work using that exact OS/SDK result.
- **World pixels observed:** same world plane shows encoded frame/square motion,
  color phases, pause/seek/resume and preserved input/bridge/lifecycle. Scope the
  result to this unprotected H.264/AAC reference, device OS and exact IPA. It
  does not certify DRM, arbitrary authenticated applications, other codecs,
  unrelated browser layouts or every iOS 17 device.

No disposition automatically completes an issue. An SDK build, a DOM animation,
HTTP request, `currentTime`, nonempty WK snapshot, native fullscreen video or
synthetic host image is insufficient for world-video acceptance.
