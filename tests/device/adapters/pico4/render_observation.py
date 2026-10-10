"""Join native OpenXR submissions with an independent Android image capture."""
import json
from io import BytesIO
import math


def native_presentation(value, pid, now):
    fields = {"schemaVersion", "processId", "updatedEpochMs", "frameSequence",
              "backend", "hardwareAccelerated", "surfaceVisible"}
    if (not isinstance(value, dict) or set(value) != fields
            or type(value["schemaVersion"]) is not int or value["schemaVersion"] != 1
            or value["processId"] != pid or isinstance(value["processId"], bool)
            or not isinstance(value["updatedEpochMs"], (int, float))
            or isinstance(value["updatedEpochMs"], bool)
            or not math.isfinite(value["updatedEpochMs"])
            or not 0 <= now - value["updatedEpochMs"] <= 5000
            or not isinstance(value["frameSequence"], (int, float))
            or isinstance(value["frameSequence"], bool)
            or not math.isfinite(value["frameSequence"])
            or not 0 < value["frameSequence"] <= 2**53-1
            or int(value["frameSequence"]) != value["frameSequence"]
            or not isinstance(value["backend"], str)
            or not value["backend"].startswith("OpenXR / OpenGL ES / ")
            or len(value["backend"]) > 256
            or type(value["hardwareAccelerated"]) is not bool
            or type(value["surfaceVisible"]) is not bool):
        raise RuntimeError("Native OpenXR presentation is stale or belongs to another process")
    return value


def black_frame(content):
    from PIL import Image
    with Image.open(BytesIO(content)) as source:
        source.load()
        if source.format != "PNG" or source.width < 32 or source.height < 32:
            raise RuntimeError("Pico native presentation capture is not a usable PNG")
        # Evaluate both eye interiors separately. A bright system icon or the
        # other eye cannot conceal a black stereoscopic view.
        eyes = []
        for start, end in ((0, source.width//2), (source.width//2, source.width)):
            width = end-start
            crop = source.crop((start+width//5, source.height//5,
                                end-width//5, source.height*4//5)).convert("L").resize((64,64))
            bright = sum(count for level,count in enumerate(crop.histogram()) if level > 12)
            eyes.append(bright/(64*64) < .01)
        return any(eyes)


def render_snapshot(adb, target, package, identity):
    raw = adb.read_debug_app_file(target, package,
                                 "files/overte-e2e/render-presentation.json", attempts=1)
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError("Native OpenXR presentation observation is unavailable") from None
    observed = native_presentation(value, int(identity.split(":",1)[0]),
                                   adb.epoch_milliseconds(target))
    image = adb.execute_bytes(["exec-out", "screencap", "-p"], target=target, timeout=30)
    return {"schemaVersion":1, "backend":observed["backend"],
            "hardwareAccelerated":observed["hardwareAccelerated"],
            "surfaceVisible":observed["surfaceVisible"] and adb.foreground_package(target)==package,
            "blackFrame":black_frame(image), "frameSequence":int(observed["frameSequence"])}
