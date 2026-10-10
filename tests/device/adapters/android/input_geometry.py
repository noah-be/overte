"""Aim a bounded native grip gesture using the observed tracking transform."""
import math


def _multiply(a, b):
    x, y, z, w = a
    X, Y, Z, W = b
    return [w*X+x*W+y*Z-z*Y, w*Y-x*Z+y*W+z*X,
            w*Z+x*Y-y*X+z*W, w*W-x*X-y*Y-z*Z]


def _axis(axis, angle):
    return [*(value * math.sin(angle / 2) for value in axis), math.cos(angle / 2)]


def primary_grip_pose(observation, process_id, now_ms):
    """Convert the controlled fixture target into current STAGE coordinates.

    This produces only pose input; the native pointer and the entity script
    independently determine whether the gesture hits and activates the target.
    """
    if (not isinstance(observation, dict)
            or observation.get('schemaVersion') != 1
            or observation.get('source') != 'native-avatar-input-geometry'
            or type(observation.get('processId')) is not int
            or observation['processId'] != process_id
            or type(observation.get('updatedEpochMs')) is not int
            or not 0 <= now_ms - observation['updatedEpochMs'] <= 5000):
        raise ValueError('Native input geometry is unavailable, stale, or from another process')
    matrix = observation.get('sensorToWorld')
    avatar = observation.get('avatarPosition')
    if (not isinstance(matrix, list) or len(matrix) != 16
            or not isinstance(avatar, dict) or set(avatar) != {'x', 'y', 'z'}
            or not all(type(v) in (int, float) and math.isfinite(v)
                       for v in matrix + list(avatar.values()))):
        raise ValueError('Native input geometry is malformed')
    # A tracking transform is affine with a positive uniform scale and an
    # orthonormal basis. Reject shear/reflections rather than guessing an aim.
    columns = [matrix[index:index+3] for index in (0, 4, 8)]
    scales = [math.sqrt(sum(v*v for v in column)) for column in columns]
    scale = scales[0]
    if (not .1 <= scale <= 10 or any(abs(v-scale) > .001 for v in scales)
            or any(abs(sum(a*b for a, b in zip(columns[i], columns[j]))) > .001
                   for i, j in ((0, 1), (0, 2), (1, 2)))
            or any(abs(matrix[i]) > .0001 for i in (3, 7, 11))
            or abs(matrix[15]-1) > .0001):
        raise ValueError('Native tracking transform is not a supported affine transform')
    x, y, z = columns
    determinant = (x[0]*(y[1]*z[2]-y[2]*z[1])
                   - y[0]*(x[1]*z[2]-x[2]*z[1])
                   + z[0]*(x[1]*y[2]-x[2]*y[1]))
    if determinant <= 0:
        raise ValueError('Native tracking transform reverses handedness')
    translation = matrix[12:15]

    def stage(world):
        relative = [a-b for a, b in zip(world, translation)]
        return [sum(a*b for a, b in zip(column, relative)) / (scale*scale)
                for column in columns]

    # The catalog owns this fixed target. Aim from a comfortable point in
    # front of the actual avatar; never teleport or alter the target entity.
    origin = stage([avatar['x'], 1.6, avatar['z']-.35])
    target = stage([0, 1.6, 2.5])
    direction = [a-b for a, b in zip(target, origin)]
    length = math.sqrt(sum(v*v for v in direction))
    if length < .2 or any(abs(v) > 3 for v in origin):
        raise ValueError('Controlled target is outside the bounded grip gesture')
    dx, dy, dz = [v/length for v in direction]
    desired = [dz, 0, -dx, 1+dy]
    norm = math.sqrt(sum(v*v for v in desired))
    if norm < .01:
        raise ValueError('Controlled target requires an unsupported grip orientation')
    desired = [v/norm for v in desired]
    # Match OpenXrInputPlugin's grip-to-hand calibration (right hand). The
    # dispatcher ray uses the corrected hand's +Y axis, not the raw grip -Z.
    rotation = _multiply(_axis([0, 0, 1], math.pi/2), _axis([1, 0, 0], math.pi/4))
    inverse = [-rotation[0], -rotation[1], -rotation[2], rotation[3]]
    correction = _multiply(_axis([1, 0, 0], -math.pi/8),
        _multiply(inverse, _multiply(_axis([0, 1, 0], math.pi), _axis([1, 0, 0], math.pi/2))))
    inverse = [-correction[0], -correction[1], -correction[2], correction[3]]
    raw = _multiply(desired, inverse)
    return {'positionMeters': origin, 'orientation': raw}
