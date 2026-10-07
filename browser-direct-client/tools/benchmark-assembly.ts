// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Isolated reliable-message assembly measurement; not a world/GPU benchmark.
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { performance } from 'node:perf_hooks';
import assert from 'node:assert/strict';
import { MessageAssembler } from '../src/protocol/message-assembler';
import NLPacket from '../src/protocol/vircadia/domain/networking/NLPacket';
import NLPacketList from '../src/protocol/vircadia/domain/networking/NLPacketList';
import PacketType from '../src/protocol/vircadia/domain/networking/udt/PacketHeaders';

const [manifestArgument, outputArgument] = process.argv.slice(2);
if (!manifestArgument || !outputArgument) throw Error('Pass the actual asset provenance manifest and result path.');
const manifestPath = resolve(manifestArgument);
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
const candidates = manifest.records.filter((entry: { sourceURL: string; referenceOnlyAdaptation: boolean }) =>
    /\.fbx(?:[?#]|$)/i.test(entry.sourceURL) && !entry.referenceOnlyAdaptation);
candidates.sort((a: { servedBytes: number }, b: { servedBytes: number }) => b.servedBytes - a.servedBytes);
const asset = candidates[0];
if (!asset) throw Error('No unchanged actual FBX exists in the manifest.');
const source = readFileSync(resolve(dirname(manifestPath), '../assets/files', asset.servedSHA256));
assert.equal(createHash('sha256').update(source).digest('hex'), asset.sourceSHA256);
const packets = NLPacketList.create(PacketType.AssetGetReply, null, true, true);
packets.write(source); packets.closeCurrentPacket(); packets.preparePackets(1);
const fragments = packets.getPackets().map(packet => {
    const data = packet.getMessageData();
    return data.buffer.subarray(NLPacket.totalNLHeaderSize(packet.getType(), true), data.packetSize);
});
const expectedHash = asset.sourceSHA256;
function measure(optimized: boolean) {
    const started = performance.now();
    let copiedBytes = 0, result: Uint8Array;
    if (optimized) {
        const assembly = new MessageAssembler();
        for (const fragment of fragments) assembly.append(fragment);
        result = assembly.finish(); copiedBytes = result.byteLength;
    } else {
        let accumulated = new Uint8Array(0);
        for (const fragment of fragments) {
            const next = new Uint8Array(accumulated.byteLength + fragment.byteLength);
            next.set(accumulated); next.set(fragment, accumulated.byteLength);
            copiedBytes += next.byteLength; accumulated = next;
        }
        result = accumulated;
    }
    const elapsedMs = performance.now() - started;
    assert.equal(createHash('sha256').update(result).digest('hex'), expectedHash);
    return { elapsedMs, copiedBytes, outputSHA256: expectedHash };
}
const repetitions = 5, baseline = [], optimized = [];
for (let index = 0; index < repetitions; index++) {
    // Alternate order to avoid granting only one arm a warm-runtime advantage.
    if (index % 2) { optimized.push(measure(true)); baseline.push(measure(false)); }
    else { baseline.push(measure(false)); optimized.push(measure(true)); }
}
const median = (values: number[]) => [...values].sort((a, b) => a - b)[Math.floor(values.length / 2)];
const report = { scope: 'isolated reliable-message assembly; no world/GPU or join-time claim',
    asset: { sourceURL: asset.sourceURL, sourceSHA256: expectedHash, sourceBytes: source.byteLength },
    fragmentCount: fragments.length, repetitions, baseline, optimized,
    baselineMedianMs: median(baseline.map(item => item.elapsedMs)),
    optimizedMedianMs: median(optimized.map(item => item.elapsedMs)),
    identicalBytesAndQuality: true, nodeVersion: process.version };
writeFileSync(resolve(outputArgument), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify({ sourceBytes: source.byteLength, fragments: fragments.length,
    baselineMedianMs: report.baselineMedianMs, optimizedMedianMs: report.optimizedMedianMs,
    identicalSHA256: expectedHash }));
