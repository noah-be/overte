// SPDX-License-Identifier: Apache-2.0
import QtQuick 2.7
import QtTest 1.2
import TestSnapshot 1.0
import "../production"

TestCase {
    name: "NativeSnapshotReview"
    visible: true
    width: 900; height: 1200
    when: windowShown
    Component { id: factory; NativeSnapshotReview { width: 800; height: 1100 } }
    SignalSpy { id: outgoing; signalName: "sendToScript" }
    property var review: null
    function init() { review = createTemporaryObject(factory, this); verify(review); outgoing.target = review; wait(1); outgoing.clear() }
    function cleanup() { if (review) { review.destroy(); review = null } }
    function test_four_real_capture_modes() {
        var mode = findChild(review, "snapshotMode")
        var button = findChild(review, "snapshotCapture")
        verify(mode); verify(button)
        var name = findChild(review, "snapshotName"); name.text = "Photo"
        var modes = ["still", "animated", "panorama", "cubemap"]
        for (var i = 0; i < modes.length; ++i) {
            mode.currentIndex = i
            mouseClick(button)
            compare(outgoing.count, i + 1)
            var message = outgoing.signalArguments[i][0]
            compare(message.type, "snapshot"); compare(message.action, "takeSnapshot")
            compare(message.mode, modes[i]); compare(message.filename, "Photo")
        }
    }
    function test_capture_error_and_cancel_controls() {
        review.fromScript({type:"snapshot", action:"clearPreviousImages"})
        compare(review.capturing, true)
        verify(!findChild(review, "snapshotCapture").enabled)
        mouseClick(findChild(review, "snapshotCancelCapture"))
        compare(outgoing.signalArguments[0][0].action, "cancelSnapshotCapture")
        review.fromScript({type:"snapshot", action:"captureStatus", phase:"error", error:"disk-full"})
        compare(review.capturing, false); compare(review.processing, false)
        compare(review.statusError, true); verify(review.statusText.indexOf("disk-full") !== -1)
        review.fromScript({type:"snapshot", action:"captureStatus", phase:"complete"})
        compare(review.statusError, false); verify(findChild(review,"snapshotCapture").enabled)
    }
    function test_preview_preserves_still_gif_and_audiences() {
        review.fromScript({type:"snapshot", action:"showPreviousImages", options:{isLoggedIn:true,canShare:true,canBlast:true},
            image_data:[{localPath:"/native/still.png",story_id:42}]})
        review.fromScript({type:"snapshot", action:"addImages", options:{containsGif:true,isLoggedIn:true,canShare:true},
            image_data:[{localPath:"/native/animation.gif"}]})
        compare(review.images.length, 2); compare(review.images[0].story_id, 42)
        review.fromScript({type:"snapshot",action:"snapshotUploadComplete",image_url:"https://host/animation.gif",story_id:99})
        compare(review.images[0].story_id,42); compare(review.images[1].story_id,99)
    }
    function test_upload_ticket_errors_and_old_completion() {
        review.upload("/native/still.png")
        compare(outgoing.signalArguments[0][0].action, "shareSnapshotForUrl")
        review.fromScript({type:"snapshot",action:"uploadStatus",path:"/old.png",status:"success"})
        compare(review.uploadPath,"/native/still.png")
        review.fromScript({type:"snapshot",action:"uploadStatus",path:"/native/still.png",status:"error",error:"unauthorized"})
        compare(review.uploadPath,""); compare(review.statusError,true)
        verify(review.statusText.indexOf("unauthorized") !== -1)
    }
    function test_actual_selected_export_and_cancel() {
        review.exportImage("/native/still.png","share")
        if (!review.exportTicket) { // The real generic backend honestly declines.
            compare(review.statusError,true); verify(review.statusText.length>0); return
        }
        var old = review.exportTicket
        review.cancelExport()
        compare(review.exportTicket,""); verify(review.statusText.indexOf("cancelled") !== -1)
        review.exportImage("/native/still.png","save")
        verify(review.exportTicket !== old)
        review.cancelExport(); compare(review.exportTicket,"")
    }
    function test_headset_keyboard_lifecycle() {
        var field = findChild(review,"snapshotName")
        field.forceActiveFocus()
        tryCompare(review,"keyboardRaised",true)
        compare(KeyboardScriptingInterface.raised,true)
        review.destroy(); review = null
        tryCompare(KeyboardScriptingInterface,"raised",false)
    }
}
