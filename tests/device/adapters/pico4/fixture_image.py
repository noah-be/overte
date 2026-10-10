"""Observe authored fixture colors in actual stereoscopic Android captures.

This supplements native scene geometry checks; it does not infer world identity
from arbitrary brightness, a skybox, system chrome, or a synthetic screenshot.
"""
from io import BytesIO


def inspect_fixture_image(content):
    from PIL import Image
    with Image.open(BytesIO(content)) as source:
        source.load()
        if source.format != "PNG" or source.width < 128 or source.height < 64:
            raise RuntimeError("Controlled scene capture is not a usable stereoscopic PNG")
        observations = []
        for start, end in ((0, source.width//2), (source.width//2, source.width)):
            width = end-start
            # Keep the world interior, excluding lens borders and the system
            # toolbar at the bottom. Counts are normalized across resolutions.
            eye = source.crop((start+width//6, source.height//6,
                               end-width//6, source.height*3//4)).convert("RGB")
            eye.thumbnail((320,320))
            pixels = list(eye.get_flattened_data() if hasattr(eye, "get_flattened_data") else eye.getdata())
            orange = sum(r > 65 and 1.25*g < r < 2.6*g and g > 1.7*b
                         for r,g,b in pixels)
            magenta = sum(r > 50 and b > 50 and min(r,b) > 1.5*g
                          and .7 < r/max(b,1) < 1.45 for r,g,b in pixels)
            gray = sum(40 < r < 245 and max(r,g,b)-min(r,g,b) < 16
                       for r,g,b in pixels)
            count = len(pixels)
            observations.append({"orangeFraction": orange/count,
                                 "magentaFraction": magenta/count,
                                 "grayFraction": gray/count,
                                 "geometryVisible": orange/count >= .01 or magenta/count >= .01,
                                 "fixtureVisible": (orange/count >= .0005
                                                    and magenta/count >= .0005
                                                    and gray/count >= .01)})
        return {"schemaVersion":1, "width":source.width, "height":source.height,
                "eyes":observations,
                "geometryVisible":all(eye["geometryVisible"] for eye in observations),
                "fixtureVisible":all(eye["fixtureVisible"] for eye in observations)}
