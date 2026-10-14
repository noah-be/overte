# iOS snapshot export

The native `Overte.iOS 1.0 IOSSnapshotAdapter` is selected by the logical
`controls/SnapshotPlatformBackend.qml` component. Capture, preview and upload
remain owned by the shared Snapshot service and review.

`request(canonicalPath, action)` returns a ticket for `save` or `share` and emits
`completed(ticket, status, error)` once. Only existing files authorized by
`overte::snapshot::exportPath` are accepted. There is no QML storage-root setter.
Original still, animated GIF, panorama and cubemap files remain available after
export. The adapter sends file URLs, preserving their original bytes.

Save requests explicit add-only Photos permission and reports the real Photos
transaction result. Cancellation before commitment prevents saving; cancellation
after commitment waits for its result and does not claim a rollback. A pending
system permission prompt keeps its lease until the user answers.

Share uses the system activity controller with an iPad popover anchor. Success
means the activity controller reported completion, not that a recipient stored
the file. Cancellation dismisses the chooser; it cannot withdraw bytes already
received by an external service. Backgrounding cancels pending operations.
The adapter retains its busy lease until the native operation returns, and
queues exactly one current-ticket result to the Qt owner.

The Core operation fixture and actual bundle-template checks run in the iOS
host gate. They do not compile UIKit/Photos Objective-C++ or establish SDK,
physical iPad permission, GIF import, share-sheet, or device lifecycle evidence.
Those require the coordinated full iOS build and physical-device qualification.
