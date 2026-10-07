// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import {recoverReviewedAvatarSource,readReviewedAvatarSource as readHistoricalAvatarSource} from './fixtures/avatar-delivery-source-fixture.mjs';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { mkdtemp, mkdir, writeFile, chmod, symlink, link, readFile, rm, stat } from 'node:fs/promises';
import { readFileSync as readCurrentFileSync } from 'node:fs';
import {recoverCaptureV25Input} from './integration/capture-delivery-angle-source-fixture.mjs';
const workflowURL=new URL('../../.github/workflows/browser-client.yml',import.meta.url),reviewedWorkflow=await recoverCaptureV25Input('.github/workflows/browser-client.yml',readCurrentFileSync(workflowURL));
const readFileSync=(input,encoding)=>input instanceof URL&&input.href===workflowURL.href?(encoding===undefined?reviewedWorkflow:reviewedWorkflow.toString(encoding)):readCurrentFileSync(input,encoding);
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { projectAvatarTail, readAvatarLog, collectAvatarSamples, writeAvatarSamples } from '../tools/curate-avatar-samples.mjs';
import {prepareAvatarV26HistoryReaders} from './integration/capture-software-managed-source-fixture.mjs';
import {prepareAvatarV27ProjectionHistoryReaders} from './integration/capture-avatar-flow-source-fixture.mjs';
const originalReaders=await prepareAvatarV26HistoryReaders(readCurrentFileSync,readHistoricalAvatarSource,recoverReviewedAvatarSource);
const {readReviewedAvatarSource}=await prepareAvatarV27ProjectionHistoryReaders(originalReaders.readFileSync,originalReaders.readReviewedAvatarSource,recoverReviewedAvatarSource);
const marker = 'BROWSER_AVATAR_SAMPLE ';
const producer = readFileSync(new URL('../gateway/native-avatar-sample-diagnostics.js', import.meta.url), 'utf8');
function produced() {
    const lines = [], context = {};
    vm.runInNewContext(producer + '\nthis.create=createNativeAvatarSampleDiagnostics;', context);
    let time = 1000;
    const diag = context.create({ now: () => time, current: () => true, authority: () => 'private-authority',
        avatarList: { getAvatarUpdateRate: (_id, key) => key ? 12 : 30 },
        stats: { myAvatarSendRate: 9, avatarMixerOutPps: 10 }, print: line => lines.push(line + '\n') });
    diag.beginBatch(); const row = diag.beginAvatar(); diag.poseSampled(row); time += 40;
    diag.completed(row, { id: '11111111-2222-3333-4444-555555555555', displayName: 'Native-Lab-Participant',
        position: { x: 0, y: 0, z: 0 }, private: 'PRIVATE_URL_OR_SECRET' }, false, { position: { x: 1, y: 0, z: 0 } });
    diag.published(); diag.authorObservation(); diag.stop();
    return lines;
}
async function fixture(fn) {
    const root = await mkdtemp(join(tmpdir(), 'overte-avatar-curation-'));
    await chmod(root, 0o700); await mkdir(join(root, 'logs'), { mode: 0o755 });
    try { await fn(root); } finally { await rm(root, { recursive: true, force: true }); }
}
test('actual full native producer feeds unchanged projector and exports only its fixed sample/author DTOs', () => {
    const result = projectAvatarTail(Buffer.from(produced().join('')));
    assert.equal(result.rows.length, 2); assert.equal(result.rejectedMarkerLines, 0);
    assert.equal(result.rows[0].postPublicationPoseDeltaMeters, 1);
    assert.equal(result.rows[0].publishedPoseAgeMs, 40); assert.equal(result.rows[0].peerPacketRateHz, 30);
    assert.equal(result.rows[1].cachedMyAvatarSendRateHz, 9);
    assert(!JSON.stringify(result).includes('PRIVATE')); assert(!JSON.stringify(result).includes('11111111'));
});
test('native Qt decorated author line and already normalized gateway line both use real projector', () => {
    const [sample, author] = produced();
    const result = projectAvatarTail(Buffer.from('[native] ' + JSON.stringify(author.trimEnd()) + '\n' + sample));
    assert.deepEqual(result.rows.map(row => row.kind), ['author-transmission', 'sample']);
});
test('unknown fields, malformed JSON, private exception prose, multiple markers and invalid UTF8 do not escape', () => {
    const value = JSON.parse(produced()[0].slice(marker.length)); value.url = 'PRIVATE_SECRET';
    const data = Buffer.concat([Buffer.from('PRIVATE_LOG\n' + marker + JSON.stringify(value) + '\n' + marker + '{PRIVATE_SECRET}\n'
        + marker + marker + '{}\n'), Buffer.from([255]), Buffer.from(marker + '{}\n')]);
    const out = projectAvatarTail(data); assert.equal(out.rows.length, 0); assert.equal(out.rejectedMarkerLines, 4);
    assert(!JSON.stringify(out).includes('PRIVATE')); assert(!JSON.stringify(out).includes('url'));
});
test('one-MiB input, production 512-row cap, oversize lines and complete-line tail boundaries are explicit', () => {
    const line = produced()[0];
    const out = projectAvatarTail(Buffer.from(line.repeat(513)));
    assert.equal(out.rows.length, 512); assert.equal(out.rowBudgetReached, true); assert.equal(out.unprocessedCompleteLines, 1);
    const long = projectAvatarTail(Buffer.from(marker + 'x'.repeat(16384) + '\n'));
    assert.equal(long.rejectedMarkerLines, 1); assert.equal(long.rows.length, 0);
    const tail = projectAvatarTail(Buffer.from(line + line + line.trimEnd()), true);
    assert.equal(tail.rows.length, 1); assert.equal(tail.prefixDiscarded, true); assert.equal(tail.incompleteSuffixDiscarded, true);
    assert.throws(() => projectAvatarTail(Buffer.alloc(1024 * 1024 + 1)), /input-refused/);
});
test('real own regular logs feed collector, missing source stays unobserved and output is exclusive0600', async () => fixture(async root => {
    await writeFile(join(root, 'logs/native.log'), produced().join(''), { mode: 0o644 });
    const report = await collectAvatarSamples(root, 'a'.repeat(40));
    assert.equal(report.status, 'projected'); assert.equal(report.logs[0].rows.length, 2); assert.equal(report.logs[1].status, 'missing');
    assert.equal(report.interpretation.nativePacketDeliveryEstablished, false);
    const filename = join(root, 'safe.json'); await writeAvatarSamples(filename, report);
    assert.equal((await stat(filename)).mode & 0o777, 0o600);
    assert.deepEqual(JSON.parse(await readFile(filename, 'utf8')), report);
    await assert.rejects(writeAvatarSamples(filename, report), { code: 'EEXIST' });
}));
test('actual oversized file remains a bounded censored tail and never exports raw prefix', async () => fixture(async root => {
    await writeFile(join(root, 'logs/native.log'), 'PRIVATE'.repeat(180000) + '\n' + produced()[0], { mode: 0o600 });
    const out = await readAvatarLog(root, 'native'); assert.equal(out.status, 'read'); assert.equal(out.bytesRead, 1024 * 1024);
    assert.equal(out.tailTruncated, true); assert.equal(out.rows.length, 1); assert(!JSON.stringify(out).includes('PRIVATE'));
}));
test('symlink, hardlink, writable file and nonregular log are refused without opening their content', async () => fixture(async root => {
    const file = join(root, 'logs/native.log'), target = join(root, 'target'); await writeFile(target, produced()[0], { mode: 0o600 });
    await symlink(target, file); assert.equal((await readAvatarLog(root, 'native')).status, 'refused'); await rm(file);
    await link(target, file); assert.equal((await readAvatarLog(root, 'native')).reason, 'file-refused'); await rm(file);
    await writeFile(file, produced()[0], { mode: 0o666 }); await chmod(file, 0o666);
    assert.equal((await readAvatarLog(root, 'native')).status, 'refused'); await rm(file);
    await mkdir(file); assert.equal((await readAvatarLog(root, 'native')).status, 'refused');
}));
test('private root and nonalias logs boundary are required and only exact two source names are accepted', async () => fixture(async root => {
    await chmod(root, 0o755); assert.equal((await readAvatarLog(root, 'native')).status, 'refused'); await chmod(root, 0o700);
    await rm(join(root, 'logs'), { recursive: true }); await mkdir(join(root, 'other')); await symlink(join(root, 'other'), join(root, 'logs'));
    assert.equal((await readAvatarLog(root, 'native')).status, 'refused');
    await assert.rejects(readAvatarLog(root, '../secret'), /source-refused/);
    await assert.rejects(collectAvatarSamples(root, 'PRIVATE_SHA'), /commit-refused/);
}));
test('actual CLI fixed root produces only safe missing DTO and keeps original refusal nonzero without exception prose', async () => fixture(async root => {
    const cli = new URL('../tools/curate-avatar-samples.mjs', import.meta.url).pathname;
    const output = join(root, 'output'); await mkdir(output, { mode: 0o700 });
    const result = spawnSync(process.execPath, [cli, '--output', output, '--commit-sha', 'a'.repeat(40)], { cwd: root, encoding: 'utf8' });
    assert.equal(result.status, 0); const report = JSON.parse(await readFile(join(output, 'native-avatar-samples.json'), 'utf8'));
    assert.equal(report.status, 'not-observed'); assert.equal(report.logs.length, 2);
    const duplicate = spawnSync(process.execPath, [cli, '--output', output, '--commit-sha', 'a'.repeat(40)], { cwd: root, encoding: 'utf8' });
    assert.equal(duplicate.status, 1); assert.equal(duplicate.stderr.trim(), 'Native avatar diagnostic collection refused.');
}));

const workflowChanges = [
  {
    "before": "        default: false\n\npermissions:",
    "after": "        default: false\n      avatar_sample_diagnostics:\n        description: 'Collect bounded opt-in native avatar diagnostics during the unchanged full journey'\n        type: boolean\n        default: false\n\npermissions:"
  },
  {
    "before": "      OVERTE_LAB_DURATION_SECONDS: '0'\n",
    "after": "      OVERTE_LAB_DURATION_SECONDS: '0'\n      OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS: ${{ github.event_name == 'workflow_dispatch' && inputs.avatar_sample_diagnostics && !inputs.startup_diagnostics && '1' || '' }}\n"
  },
  {
    "before": "      - name: Preserve only curated native core evidence\n",
    "after": "      - name: Collect bounded opt-in native avatar diagnostics\n        if: ${{ always() && github.event_name == 'workflow_dispatch' && inputs.avatar_sample_diagnostics && !inputs.startup_diagnostics }}\n        run: |\n          node browser-client/tools/curate-avatar-samples.mjs \\\n            --output \"$RUNNER_TEMP/overte-native-core-evidence\" --commit-sha \"$GITHUB_SHA\"\n      - name: Preserve only curated native core evidence\n"
  }
];
const unchangedPins = {
  "browser-client/gateway/native-avatar-stdout-projection.mjs": "90c7c18ab0c35e85620bcfa94427253232715da53c0abaf781e817b14515ea3f",
  "browser-client/gateway/native-avatar-sample-diagnostics.js": "cd2f35f8bc04edfdb9c09fcd8b5399d1e03b5b3b40bbbf9a459620b68ad9be49",
  "browser-client/gateway/native-bridge.js": "a0ad9878a10023646aad6ecd3a926cde1d364f441786c8a0cf0969ee536604d9",
  "browser-client/gateway/server.mjs": "e17fae1f721ed162e131309c983041ef824d5688080e5053b6b98f2f9f4722ea",
  "browser-client/lab/manage.py": "84b4426187e078515b77984a3581a63130d2dbc0c5edf4230a66a17ecdbf8e66",
  "browser-client/lab/native-participant.js": "735a5ee9b4327963ea7fb2ebec5e2159c1196aa99d8b6e7fd996809f521b7ede",
  "browser-client/lab/run-core-journey.sh": "9693ae82a858752909988534251b28c81bbc9a7c199328fc63915e77f84e25e4",
  "browser-client/tests/integration/real-session.mjs": "daba35297a9090a29a916ddd7658c11b2713fcf1f25d78894e17d9ac922e915b"
};
test('three exact workflow anchors recover the entire aeb workflow and preserve full/startup failure gates', () => {
    const workflow = readFileSync(new URL('../../.github/workflows/browser-client.yml', import.meta.url), 'utf8');
    let restored = workflow;
    for (const change of [...workflowChanges].reverse()) {
        assert.equal(restored.split(change.after).length - 1, 1);
        restored = restored.replace(change.after, change.before);
    }
    assert.equal(createHash('sha256').update(restored).digest('hex'), "1c35849c3a5dd71bccc7bd90125c12d5df7a1cb805e474be9174f87309cdd8ef");
    assert(!workflow.includes('continue-on-error:'));
    assert(workflow.includes("if: ${{ !cancelled() && !inputs.startup_diagnostics && steps.start.outcome == 'success' }}"));
    assert(workflow.includes("id: start\n        run: python3 browser-client/lab/manage.py start --gateway"));
    assert.equal(workflow.indexOf('OVERTE_LAB_AVATAR_SAMPLE_DIAGNOSTICS:') < workflow.indexOf('manage.py prepare --host-tools system'), true);
});
test('manual full opt-in alone selects full diagnostics; PR/default/startup combinations remain disabled', () => {
    for (const manual of [false, true]) for (const diagnostics of [false, true]) for (const startup of [false, true]) {
        const value = manual && diagnostics && !startup && '1' || '';
        assert.equal(value, manual && diagnostics && !startup ? '1' : '');
    }
    const workflow = readFileSync(new URL('../../.github/workflows/browser-client.yml', import.meta.url), 'utf8');
    assert(workflow.includes("avatar_sample_diagnostics:\n        description: 'Collect bounded opt-in native avatar diagnostics during the unchanged full journey'\n        type: boolean\n        default: false"));
    assert(workflow.includes("github.event_name == 'workflow_dispatch' && inputs.avatar_sample_diagnostics && !inputs.startup_diagnostics && '1' || ''"));
});
test('actual producer/projector/manager/author and original movement predicate have exact unchanged source closure', ((readFileSync) => () => {
    for (const [path, sha] of Object.entries(unchangedPins)) {
        const value = readFileSync(new URL('../' + path.replace(/^browser-client\//, ''), import.meta.url));
        assert.equal(createHash('sha256').update(value).digest('hex'), sha, path);
    }
    const journey = readFileSync(new URL('./integration/real-session.mjs', import.meta.url), 'utf8');
    assert(journey.includes('await delay(2800);'));
    assert(journey.includes("'Browser receives second native participant movement'"));
})(readReviewedAvatarSource));
test('actual reader fresh-descriptor mutation/identity exception refuses and closes its sole held descriptor', async () => {
    for (const changed of ['size', 'ino', 'uid', 'mode', 'exception']) {
        let closed = 0, calls = 0;
        const initial = { dev: 1, ino: 2, size: 0, mtimeMs: 1, ctimeMs: 1, uid: process.getuid(), mode: 0o100600, nlink: 1, isFile: () => true };
        const context = { constants: { O_RDONLY: 0, O_NOFOLLOW: 0, O_NONBLOCK: 0 }, Buffer, join,
            own: value => value.uid === process.getuid() && !(value.mode & 0o022),
            stable: (a, b) => ['dev', 'ino', 'size', 'mtimeMs', 'ctimeMs', 'uid', 'mode', 'nlink'].every(key => a[key] === b[key]),
            directory: async () => initial, lstat: async () => initial, MAX_BYTES: 1024 * 1024, projectAvatarTail,
            open: async () => ({ close: async () => { closed++; }, read: async () => ({ bytesRead: 0 }), stat: async () => {
                if (++calls === 1) return initial;
                if (changed === 'exception') throw Error('PRIVATE_FAILURE');
                return { ...initial, [changed]: initial[changed] + 1 };
            } }) };
        const read = vm.runInNewContext('(' + readAvatarLog.toString() + ')', context);
        const out = await read('/own', 'native');
        assert.equal(out.status, 'refused'); assert.equal(closed, 1);
        assert(!JSON.stringify(out).includes('PRIVATE'));
    }
});
