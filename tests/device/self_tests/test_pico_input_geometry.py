"""Reject unsafe geometry and verify aiming across real tracking rotations."""
import copy
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.android.input_geometry import primary_grip_pose


def rotate(q, v):
    x, y, z, w = q
    X, Y, Z = v
    return [(1-2*y*y-2*z*z)*X + (2*x*y-2*z*w)*Y + (2*x*z+2*y*w)*Z,
            (2*x*y+2*z*w)*X + (1-2*x*x-2*z*z)*Y + (2*y*z-2*x*w)*Z,
            (2*x*z-2*y*w)*X + (2*y*z+2*x*w)*Y + (1-2*x*x-2*y*y)*Z]


class InputGeometryTests(unittest.TestCase):
    def observation(self, yaw=0, scale=1):
        c, s = math.cos(yaw)*scale, math.sin(yaw)*scale
        return {'schemaVersion': 1, 'source': 'native-avatar-input-geometry',
                'processId': 42, 'updatedEpochMs': 10000,
                'sensorToWorld': [c, 0, -s, 0, 0, scale, 0, 0, s, 0, c, 0, 0, 0, 4, 1],
                'avatarPosition': {'x': 0, 'y': 1, 'z': 4}}

    def test_aim_remains_on_the_world_target_after_recenter_and_scale(self):
        # Independently rotate the dispatcher's +Y through the production
        # grip calibration and then the requested raw grip quaternion.
        calibration = [0.6935199226610738, 0.1379496896414715,
                       -0.6935199226610738, -0.13794968964147133]
        corrected_up = rotate(calibration, [0, 1, 0])
        for yaw in [0, .42, -.42, math.pi/2]:
            for scale in [1, 1.25]:
                with self.subTest(yaw=yaw, scale=scale):
                    pose = primary_grip_pose(self.observation(yaw, scale), 42, 10001)
                    stage_direction = rotate(pose['orientation'], corrected_up)
                    c, s = math.cos(yaw), math.sin(yaw)
                    world_direction = [c*stage_direction[0]+s*stage_direction[2],
                        stage_direction[1], -s*stage_direction[0]+c*stage_direction[2]]
                    for observed, expected in zip(world_direction, [0, 0, -1]):
                        self.assertAlmostEqual(observed, expected, places=6)
                    point = pose['positionMeters']
                    world_origin = [scale*(c*point[0]+s*point[2]), scale*point[1],
                                    4+scale*(-s*point[0]+c*point[2])]
                    for observed, expected in zip(world_origin, [0, 1.6, 3.65]):
                        self.assertAlmostEqual(observed, expected, places=6)

    def test_rejects_stale_foreign_or_malformed_geometry(self):
        for change in [{'processId': 43}, {'updatedEpochMs': 4000},
                       {'updatedEpochMs': 10002}, {'source': 'command-input'},
                       {'sensorToWorld': [0]*16}, {'avatarPosition': {'x': math.nan, 'y': 1, 'z': 4}}]:
            value = self.observation(); value.update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                primary_grip_pose(value, 42, 10001)

    def test_rejects_shear_reflection_and_out_of_bounds_pose(self):
        for index, replacement in [(4, .5), (0, -1), (12, 50)]:
            value = copy.deepcopy(self.observation())
            value['sensorToWorld'][index] = replacement
            with self.subTest(index=index), self.assertRaises(ValueError):
                primary_grip_pose(value, 42, 10001)


if __name__ == '__main__':
    unittest.main()
