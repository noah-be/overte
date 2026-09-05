"""SH-008 bounded offline performance consumer; producer trust stays external."""
# SPDX-License-Identifier: Apache-2.0
import hashlib
import json
import math
from pathlib import Path
import re

DURATION_MS = {'android-phone': 3600000, 'pico4': 3600000,
               'ios-ipad': 1800000, 'ios-iphone': 1800000}
MAX_GAP_MS = 35000
MAX_BYTES = 1024 * 1024
ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).with_name('reference-fixture.json')

class MetricsError(ValueError): pass

def need(value, code):
    if not value: raise MetricsError(code)

def digest(raw): return hashlib.sha256(raw).hexdigest()

def read(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink(), 'METRICS_REGULAR_FILE_REQUIRED')
    with path.open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
    need(0 < len(raw) <= MAX_BYTES, 'METRICS_SIZE')
    def pairs(entries):
        result = {}
        for key, value in entries:
            need(key not in result, 'METRICS_DUPLICATE_KEY')
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(MetricsError('METRICS_NONFINITE')))
    return value, raw

def fields(value, names): need(type(value) is dict and set(value) == set(names), 'METRICS_FIELDS')
def hexvalue(value, count): return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % count, value) is not None
def integer(value, minimum, maximum): return type(value) is int and minimum <= value <= maximum
def number(value, minimum, maximum):
    return type(value) in (int, float) and minimum <= value <= maximum and math.isfinite(value)

def fixture_digest():
    document, raw = read(FIXTURE)
    for relative, expected in document['files'].items():
        need(digest((ROOT / relative).read_bytes()) == expected, 'METRICS_FIXTURE_SOURCE_MISMATCH')
    return digest(raw)

def validate(path, source, artifact, platform, expected_fixture, budget_path=None, expected_budget=None):
    need(hexvalue(source, 40) and hexvalue(artifact, 64) and hexvalue(expected_fixture, 64), 'METRICS_EXPECTED_IDENTITY')
    need(platform in DURATION_MS, 'METRICS_PLATFORM')
    need(expected_fixture == fixture_digest(), 'METRICS_WRONG_FIXTURE')
    trace, raw = read(path)
    fields(trace, ('contract', 'sourceRevision', 'artifactSha256', 'platform', 'fixtureSha256', 'samples'))
    need(trace['contract'] == 'overte-sh008-trace-v1', 'METRICS_CONTRACT')
    need(trace['sourceRevision'] == source and trace['artifactSha256'] == artifact and
         trace['platform'] == platform and trace['fixtureSha256'] == expected_fixture, 'METRICS_IDENTITY_MISMATCH')
    samples = trace['samples']
    need(type(samples) is list and 2 <= len(samples) <= 4096, 'METRICS_SAMPLE_COUNT')
    previous = -1
    memory_kind = None
    checkpoint = False
    max_frame, memory_values, queues, batteries = 0, [], [], []
    for sample in samples:
        fields(sample, ('elapsedMs', 'frameP95Ms', 'memory', 'thermal', 'batteryPercent',
                        'processEnergyJoules', 'queueDepth', 'blackFrames', 'degradation', 'checkpoint'))
        elapsed = sample['elapsedMs']
        need(integer(elapsed, 0, DURATION_MS[platform] + MAX_GAP_MS), 'METRICS_TIME_RANGE')
        need((previous == -1 and elapsed == 0) or (previous >= 0 and 0 < elapsed - previous <= MAX_GAP_MS), 'METRICS_SAMPLE_GAP')
        previous = elapsed
        need(number(sample['frameP95Ms'], 0.001, 10000), 'METRICS_FRAME_RANGE')
        max_frame = max(max_frame, sample['frameP95Ms'])
        memory = sample['memory']
        fields(memory, ('kind', 'bytes'))
        permitted = ('ios-physical-footprint',) if platform.startswith('ios-') else ('android-total-pss', 'resident-set')
        need(memory['kind'] in permitted and integer(memory['bytes'], 1, 2**50), 'METRICS_MEMORY_KIND_OR_RANGE')
        if memory_kind is None: memory_kind = memory['kind']
        need(memory_kind == memory['kind'], 'METRICS_MEMORY_KIND_CHANGED')
        memory_values.append(memory['bytes'])
        thermal = sample['thermal']
        need(thermal in ('nominal', 'fair', 'serious', 'critical'), 'METRICS_THERMAL_UNAVAILABLE')
        need(thermal != 'critical', 'STOP_THERMAL_CRITICAL')
        need(sample['degradation'] in ('normal', 'reduced', 'stopped'), 'METRICS_DEGRADATION')
        need(thermal != 'serious' or sample['degradation'] == 'reduced', 'METRICS_DEGRADATION_REQUIRED')
        need(sample['degradation'] != 'stopped', 'STOP_RUN_INCOMPLETE')
        need(sample['processEnergyJoules'] is None, 'METRICS_UNSUPPORTED_PROCESS_ENERGY')
        for key, predicate in [('batteryPercent', lambda v: number(v, 0, 100)),
                               ('queueDepth', lambda v: integer(v, 0, 65535))]:
            need(sample[key] is None or predicate(sample[key]), 'METRICS_OPTIONAL_RANGE')
        need(integer(sample['blackFrames'], 0, 2**31 - 1), 'METRICS_BLACK_FRAME_UNAVAILABLE')
        need(sample['blackFrames'] == 0, 'STOP_BLACK_FRAME')
        need(type(sample['checkpoint']) is bool, 'METRICS_CHECKPOINT_TYPE')
        if sample['checkpoint'] and 1800000 <= elapsed <= 1800000 + MAX_GAP_MS: checkpoint = True
        queues.append(sample['queueDepth']); batteries.append(sample['batteryPercent'])
    need(DURATION_MS[platform] <= previous <= DURATION_MS[platform] + MAX_GAP_MS and checkpoint, 'METRICS_DURATION_OR_CHECKPOINT')
    growth = max(memory_values) - memory_values[0]
    status = 'METRICS_BOUND_BUDGETS_PENDING'
    budget_sha = None
    if budget_path is not None:
        need(hexvalue(expected_budget, 64), 'METRICS_EXPECTED_BUDGET_REQUIRED')
        budget, budget_raw = read(budget_path)
        budget_sha = digest(budget_raw)
        need(budget_sha == expected_budget, 'METRICS_BUDGET_BYTES_MISMATCH')
        fields(budget, ('contract', 'platform', 'fixtureSha256', 'memoryKind', 'maxFrameP95Ms',
                        'maxMemoryGrowthBytes', 'maxQueueDepth', 'minBatteryEndPercent'))
        need(budget['contract'] == 'overte-sh008-budget-v1' and budget['platform'] == platform and
             budget['fixtureSha256'] == expected_fixture and budget['memoryKind'] == memory_kind, 'METRICS_BUDGET_IDENTITY')
        need(number(budget['maxFrameP95Ms'], 0.001, 10000) and integer(budget['maxMemoryGrowthBytes'], 0, 2**50)
             and integer(budget['maxQueueDepth'], 0, 65535) and number(budget['minBatteryEndPercent'], 0, 100), 'METRICS_BUDGET_RANGE')
        need(all(value is not None for value in queues + batteries), 'METRICS_REQUIRED_BUDGET_DATA_MISSING')
        need(max_frame <= budget['maxFrameP95Ms'] and growth <= budget['maxMemoryGrowthBytes'] and
             max(queues) <= budget['maxQueueDepth'] and batteries[-1] >= budget['minBatteryEndPercent'], 'METRICS_BUDGET_EXCEEDED')
        status = 'BUDGETS_CHECKED_NOT_NODE_ACCEPTED'
    else:
        need(expected_budget is None, 'METRICS_BUDGET_FILE_REQUIRED')
    return dict(status=status, traceSha256=digest(raw), fixtureSha256=expected_fixture,
                budgetSha256=budget_sha, sampleCount=len(samples), durationMs=previous,
                maxFrameP95Ms=max_frame, maxMemoryGrowthBytes=growth, memoryKind=memory_kind)
