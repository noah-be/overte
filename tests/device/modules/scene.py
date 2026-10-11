#!/usr/bin/env python3
"""Load the controlled scene and verify the in-client probe reaches ready state."""

from __future__ import annotations

import os
import hashlib
import time

from module_support import (ARTIFACT_DIR, assert_foreground, assert_process, fail,
                            module_main, operation, process_identity, write_json)
from adapters.pico4.fixture_image import inspect_fixture_image
from overte_session import OverteSession


def main() -> None:
    session = OverteSession()
    screenshot_required = os.environ.get("OVERTE_E2E_REQUIRE_FIXTURE_SCREENSHOT") == "1"
    identity = process_identity()
    # Preserve an image even when semantic readiness fails. A live renderer
    # or blue horizon alone is never evidence that the fixture loaded.
    try:
        snapshot = session.ensure_controlled_scene()
        samples = session.verify_pico_fixture(snapshot)
        if screenshot_required:
            session.assert_render_health()
    finally:
        if screenshot_required:
            capture = operation("artifact.screenshot", {})
            image_path = ARTIFACT_DIR / capture["artifact"]
            if image_path.parent != ARTIFACT_DIR or not image_path.is_file():
                fail("controlled scene screenshot artifact is unavailable")
            content = image_path.read_bytes()
            image = inspect_fixture_image(content)
            image["screenshotSha256"] = hashlib.sha256(content).hexdigest()
            image["capturedEpochMs"] = int(time.time()*1000)
            image["artifact"] = capture["artifact"]
            write_json("fixture-image-observation.json", image)
    if screenshot_required:
        assert_process(identity, "controlled scene image capture")
        assert_foreground("controlled scene image capture")
        if not image["fixtureVisible"]:
            fail("controlled scene image does not show fixture geometry in both eyes")
    print(f"Controlled scene became ready with {snapshot['scene']['entityCount']} entities "
          f"and {len(samples)} stable sample(s).")


module_main(main)
