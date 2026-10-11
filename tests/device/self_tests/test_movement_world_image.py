"""A moving avatar cannot substitute for a visible rendered fixture."""
from io import BytesIO
from pathlib import Path
import sys
import os
import tempfile
import unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {'OVERTE_DEVICE_ADAPTER_MANIFEST':'unused.json',
                            'OVERTE_DEVICE_TARGET_SELECTOR':'owned-test-alias',
                            'OVERTE_DEVICE_ARTIFACT_DIR':'unused-artifacts'}):
    from overte_session import OverteSession


def fixture_png(blank_right=False, empty=False, wall_only=False):
    frame = Image.new('RGB', (800,400), 'black')
    draw = ImageDraw.Draw(frame)
    for start in (0,400):
        if wall_only:
            draw.rectangle((start,0,start+399,399), fill=(180,80,180))
        elif empty or (start == 400 and blank_right):
            draw.rectangle((start,190,start+399,210), fill=(30,100,230))
        else:
            draw.rectangle((start+60,60,start+340,300), fill=(190,190,190))
            draw.rectangle((start+120,120,start+280,200), fill=(180,80,180))
            draw.rectangle((start+180,100,start+220,140), fill=(255,150,40))
    content = BytesIO();frame.save(content, format='PNG');return content.getvalue()


class MovementWorldImageTest(unittest.TestCase):
    def exercise(self, content, *, entry='capture', stale=False, missing_fixture=False,
                 frame_epoch=None, frozen_frames=False, unhealthy=False, ongoing=False,
                 window_focused=True):
        session = OverteSession();session.pico_openxr = True
        probe = {'sampleEpochMs': 10000, 'sampleSequence': 9,
                 'application': {'foreground': window_focused},
                 'render': {'frameCount': 77, 'lastFrameEpochMs': 7000 if stale else 9900},
                 'scene': {'ready': True, 'spawnValidated': True, 'fixtureMarkerCount': 5,
                           'fixtureMarkers': [] if missing_fixture else list(session.FIXTURE_MARKERS)}}
        if frame_epoch is not None:
            probe['render']['lastFrameEpochMs'] = frame_epoch
        session.snapshot = Mock(return_value=probe)
        if frozen_frames:
            session._movement_world_native_sequence = 8
            session._movement_world_renderer_count = 77
        elif ongoing:
            session._movement_world_native_sequence = 7
            session._movement_world_renderer_count = 76
        session.vertical_ground_snapshot = Mock(return_value={})
        session.assert_spawn_grounded = Mock(return_value={})
        session.ensure_controlled_scene = Mock(return_value={
            'scene': {'spawnLocationObserved': True, 'avatarAboveFloor': True},
            'avatar': {'inAir': False, 'flying': False}})
        session.input_neutral_snapshot = Mock(return_value={})
        session._invoke = Mock(return_value={'frameSequence': 8, 'hardwareAccelerated': True,
                                            'surfaceVisible': not unhealthy, 'blackFrame': False})
        with tempfile.TemporaryDirectory(prefix='movement-world-image-') as directory:
            root=Path(directory);(root/'screenshot.png').write_bytes(content)
            with patch('overte_session.ARTIFACT_DIR',root), \
                 patch('overte_session.process_identity',return_value='same-process'), \
                 patch('overte_session.assert_process') as same_process, \
                 patch('overte_session.assert_foreground'), \
                 patch('overte_session.operation',return_value={'artifact':'screenshot.png'}), \
                 patch('overte_session.write_json') as receipt:
                try:
                    if entry == 'capture': session.assert_visible_movement_world('jump-before')
                    elif entry == 'move': session.move('forward')
                    elif entry == 'look': session.look('left')
                    elif entry == 'collision': session.assert_collision_wall()
                    else: getattr(session,entry)()
                    self.assertEqual((root/'jump-before-world.png').read_bytes(),content)
                    self.assertTrue(receipt.call_args.args[1]['geometryVisible' if ongoing else 'fixtureVisible'])
                    same_process.assert_called_once_with('same-process','movement world capture')
                finally:
                    session._invoke.assert_called_once_with('render.snapshot', {})

    def test_preserves_actual_image_and_binds_same_live_process(self):
        self.exercise(fixture_png())

    def test_frame_presented_during_probe_collection_is_current(self):
        self.exercise(fixture_png(), frame_epoch=10061)

    def test_excessively_future_frame_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            self.exercise(fixture_png(), frame_epoch=13000)

    def test_frozen_or_hidden_renderer_cannot_pass(self):
        for options in ({'frozen_frames': True}, {'unhealthy': True}):
            with self.subTest(options=options), self.assertRaises(RuntimeError):
                self.exercise(fixture_png(), **options)

    def test_unfocused_application_cannot_pass_with_world_behind_menu(self):
        with self.assertRaisesRegex(RuntimeError, 'window to have focus'):
            self.exercise(fixture_png(), window_focused=False)

    def test_near_wall_requires_previously_verified_complete_fixture(self):
        self.exercise(fixture_png(wall_only=True), ongoing=True)
        with self.assertRaisesRegex(RuntimeError, 'both eyes'):
            self.exercise(fixture_png(wall_only=True))

    def test_empty_or_missing_eye_still_fails_after_initial_fixture(self):
        for options in ({'empty':True}, {'blank_right':True}):
            with self.subTest(options=options), self.assertRaisesRegex(RuntimeError, 'both eyes'):
                self.exercise(fixture_png(**options), ongoing=True)

    def test_black_blue_horizon_blocks_all_locomotion_before_input(self):
        for entry in ('jump','fly','move','look','collision'):
            with self.subTest(entry=entry), self.assertRaisesRegex(RuntimeError,'both eyes'):
                self.exercise(fixture_png(empty=True),entry=entry)

    def test_missing_right_eye_is_not_a_loaded_world(self):
        with self.assertRaisesRegex(RuntimeError,'both eyes'):
            self.exercise(fixture_png(blank_right=True))

    def test_stale_renderer_and_missing_geometry_cannot_pass(self):
        for options in ({'stale':True},{'missing_fixture':True}):
            with self.subTest(options=options), self.assertRaises(RuntimeError):
                self.exercise(fixture_png(),**options)


if __name__ == '__main__': unittest.main()
