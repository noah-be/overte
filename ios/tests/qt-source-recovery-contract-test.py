#!/usr/bin/env python3
"""Exercise the Qt producer's actual restore/build decisions after cache eviction."""
import itertools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
workflow = (ROOT / '.github/workflows/ios-qt-source.yml').read_text()
bootstrap = (ROOT / '.github/workflows/ios-bootstrap.yml').read_text()


def step(name):
    tail = workflow.split('      - name: ' + name + '\n', 1)[1]
    return tail.split('      - name:', 1)[0]


def condition(name):
    block = step(name)
    match = re.search(r'        if: (.*(?:\n          .*?)*)\n        (?:id:|run:|uses:|shell:|continue-on-error:|env:)', block)
    assert match, name
    return match[1].replace('>-', '').strip().removeprefix('${{').removesuffix('}}').strip()


def evaluate(expression, values):
    expression = re.sub(r'steps\.([\w-]+)\.outputs\.([\w-]+)',
                        lambda m: repr(values.get((m[1], m[2]), '')), expression)
    expression = expression.replace('github.ref_name', repr('ci/ios/parity-runner-v003'))
    expression = expression.replace('inputs.preserve_reusable_data', repr(values.get('preserve', True)))
    expression = re.sub(r'steps\.([\w-]+)\.outcome',
                        lambda m: repr(values.get((m[1], 'outcome'), 'success' if m[1] == 'sccache' else 'skipped')),
                        expression)
    expression = expression.replace('failure()', repr(values.get('failure', True)))
    expression = expression.replace('cancelled()', repr(values.get('cancelled', False)))
    expression = expression.replace('&&', ' and ').replace('||', ' or ')
    expression = re.sub(r'!(?!=)', ' not ', expression)
    return bool(eval('(' + expression + ')', {'__builtins__': {}}, {}))


for flags in itertools.product([False, True], repeat=6):
    values = {}
    for part, offset in [('host', 0), ('ios', 3)]:
        cache, own, trusted = flags[offset:offset + 3]
        values[(part + '-cache', 'cache-hit')] = str(cache).lower()
        values[(part + '-artifact', 'restored')] = str(own).lower()
        values[(part + '-apple-ios-artifact', 'restored')] = str(trusted).lower()
        selection = re.search(part.upper() + r'_RESTORED: \$\{\{ (.*?) \}\}', step('Select validated restored components'))[1]
        restored = evaluate(selection, values)
        assert restored == (own or trusted)
        values[('restored-components', part)] = str(restored).lower()
        fallback = 'Restore trusted apple-ios Qt ' + part + ' checkpoint for build branches'
        assert evaluate(condition(fallback), values) == (not cache and not own)
        command = step(fallback)
        for required in ['--expected-branch apple-ios', '--expected-repository-id "$OVERTE_CHECKPOINT_REPOSITORY_ID"',
                         '--cache-key', '--artifact-prefix', '--kind ' + part]:
            assert required in command
        build = 'Build Qt host tools' if part == 'host' else 'Build Qt iOS target'
        assert evaluate(condition(build), values) == (not (cache or own or trusted))
    cold = not any(flags[:3]) or not any(flags[3:])
    for cold_step in ['Install source-build prerequisites', 'Install pinned compiler cache',
                      'Verify local compiler cache before the long build', 'Restore durable Qt compiler objects']:
        assert evaluate(condition(cold_step), values) == cold
    for restored in [False, True]:
        values[('qt-compiler-artifact', 'restored')] = str(restored).lower()
        assert evaluate(condition('Restore compiler recovery cache'), values) == (cold and not restored)
        assert evaluate(condition('Merge validated Qt compiler objects'), values) == restored

# Snapshot actual attempted compilations after success OR failure, never cache-only
# runs, early setup failures, or cancelled jobs. A failed snapshot cannot be uploaded.
outcomes = ['success', 'failure', 'skipped', 'cancelled']
for host, ios, cancelled in itertools.product(outcomes, outcomes, [False, True]):
    values = {('qt-host-build', 'outcome'): host, ('qt-ios-build', 'outcome'): ios,
              'cancelled': cancelled}
    attempted = host in ['success', 'failure'] or ios in ['success', 'failure']
    for name in ['Stop compiler-cache server before recovery snapshot',
                 'Save durable Qt compiler recovery checkpoint']:
        assert evaluate(condition(name), values) == (attempted and not cancelled)
for outcome, cancelled in itertools.product(outcomes, [False, True]):
    values = {('qt-compiler-create', 'outcome'): outcome, 'cancelled': cancelled}
    assert evaluate(condition('Upload durable Qt compiler recovery checkpoint'), values) == (outcome == 'success' and not cancelled)

restore = step('Restore durable Qt compiler objects')
for required in ['--kind qt-sccache', '--expected-repository-id "$OVERTE_CHECKPOINT_REPOSITORY_ID"',
                 '--expected-branch "$OVERTE_CHECKPOINT_BRANCH"', '--cache-key', '--artifact-prefix']:
    assert required in restore
legacy = step('Restore compiler recovery cache')
for prefix in ['sccache_prefix', 'sccache_toolchain_prefix', 'sccache_legacy_prefix']:
    assert f'steps.cache-key.outputs.{prefix}' in legacy
assert 'actions/cache/restore@' in legacy

# All recovery paths preserve existing reusable data by default, including failure.
for mode in ['workflow_call', 'workflow_dispatch']:
    block = workflow.split('  ' + mode + ':', 1)[1].split('      target_sdk:', 1)[0]
    assert 'preserve_reusable_data:' in block and 'default: true' in block
prune = condition('Prune superseded Qt compiler recovery caches')
assert not evaluate(prune, {'preserve': True})
assert evaluate(prune, {'preserve': False})
for job in ['provision-qt-ios', 'integrated-ios-after-qt']:
    block = re.search(r'^  ' + job + r':\n(.*?)(?=^  [\w-]+:|\Z)', bootstrap, re.M | re.S)[1]
    assert 'preserve_reusable_data: true' in block
print('PASS Qt source recovery: 64 cache/artifact combinations, warm prep skips, outcome-aware durable snapshots, legacy fallback, preservation')
