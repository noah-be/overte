// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Read-only, bounded Chrome CPU sampling. No heap, request, object or packet values.
import { readFile, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { resolve, sep } from 'node:path';
import { SourceMap } from 'node:module';

const pause = milliseconds => new Promise(resolvePause => setTimeout(resolvePause, milliseconds));
const safeURL = source => {
    if (!source) return '';
    if (source.startsWith('data:')) return source.split(';', 1)[0];
    if (source.startsWith('blob:')) return 'blob:[identifier omitted]';
    try { const url = new URL(source); url.username = ''; url.password = ''; url.search = ''; url.hash = ''; return url.toString(); }
    catch { return String(source).slice(0, 512); }
};

export async function captureCPUProfile(page, directory, bundle, observe) {
    const session = await page.context().newCDPSession(page);
    const started = new Date().toISOString(), before = await observe();
    let running = false;
    try {
        await session.send('Profiler.enable'); await session.send('Profiler.setSamplingInterval', { interval: 1000 });
        await session.send('Profiler.start'); running = true;
        await pause(10000);
        const { profile: actual } = await session.send('Profiler.stop'); running = false;
        const after = await observe(), MAX_NODES = 8192, MAX_SAMPLES = 100000;
        const nodes = actual.nodes.slice(0, MAX_NODES).map(node => ({ id: node.id,
            callFrame: { functionName: String(node.callFrame.functionName).slice(0, 512), scriptId: node.callFrame.scriptId,
                url: safeURL(node.callFrame.url), lineNumber: node.callFrame.lineNumber, columnNumber: node.callFrame.columnNumber },
            hitCount: node.hitCount || 0, children: (node.children || []).slice(0, MAX_NODES) }));
        const profile = { nodes, startTime: actual.startTime, endTime: actual.endTime,
            samples: (actual.samples || []).slice(0, MAX_SAMPLES), timeDeltas: (actual.timeDeltas || []).slice(0, MAX_SAMPLES) };
        const retained = new Map(nodes.map(node => [node.id, node])), parents = new Map(), self = new Map(), inclusive = new Map();
        for (const node of nodes) for (const child of node.children) parents.set(child, node.id);
        let retainedSampleTimeMs = 0;
        for (let index = 0; index < profile.samples.length; index++) {
            const id = profile.samples[index], duration = (profile.timeDeltas[index] || 0) / 1000;
            retainedSampleTimeMs += duration; self.set(id, (self.get(id) || 0) + duration);
            let ancestor = id, depth = 0;
            while (ancestor !== undefined && depth++ < 256) { inclusive.set(ancestor, (inclusive.get(ancestor) || 0) + duration); ancestor = parents.get(ancestor); }
        }
        const sourceMaps = new Map();
        async function sourceFor(node) {
            if (!node?.callFrame.url || node.callFrame.lineNumber < 0) return undefined;
            let path;
            try { const url = new URL(node.callFrame.url); if (url.origin !== 'http://127.0.0.1:46106') return undefined;
                path = resolve(bundle, `.${decodeURIComponent(url.pathname)}.map`); } catch { return undefined; }
            if (!path.startsWith(`${resolve(bundle)}${sep}`) || !existsSync(path)) return undefined;
            if (!sourceMaps.has(path)) sourceMaps.set(path, (async () => new SourceMap(JSON.parse(await readFile(path, 'utf8'))))());
            const original = (await sourceMaps.get(path)).findEntry(node.callFrame.lineNumber, node.callFrame.columnNumber);
            if (!original.originalSource) return undefined;
            return { source: safeURL(original.originalSource), line: original.originalLine + 1, column: original.originalColumn + 1,
                ...(original.name ? { name: original.name } : {}) };
        }
        async function top(values) {
            const rows = [...values].sort((left, right) => right[1] - left[1]).slice(0, 30);
            return Promise.all(rows.map(async ([id, durationMs]) => {
                const node = retained.get(id); return { id, durationMs,
                    percentOfRetainedSampleTime: retainedSampleTimeMs ? durationMs / retainedSampleTimeMs * 100 : 0,
                    callFrame: node?.callFrame, original: await sourceFor(node) };
            }));
        }
        const summary = { started, finished: new Date().toISOString(), requestedWallMs: 10000,
            actualProfileDurationMs: (actual.endTime - actual.startTime) / 1000, retainedSampleTimeMs,
            samplingIntervalMicroseconds: 1000, originalNodeCount: actual.nodes.length, retainedNodes: nodes.length,
            originalSampleCount: actual.samples?.length || 0, retainedSamples: profile.samples.length,
            truncatedNodes: actual.nodes.length > MAX_NODES, truncatedSamples: (actual.samples?.length || 0) > MAX_SAMPLES,
            scope: 'Chrome main-thread sampled call stacks/function source locations only. Includes native/V8 program/idle entries; no heap, request bodies, packets or object values. Diagnostic sampling overhead is present; not a benchmark case.',
            before, after, topSelf: await top(self), topInclusive: await top(inclusive) };
        await writeFile(resolve(directory, 'cpu-profile.json'), `${JSON.stringify(profile)}\n`, { mode: 0o600 });
        await writeFile(resolve(directory, 'cpu-profile-summary.json'), `${JSON.stringify(summary, null, 2)}\n`, { mode: 0o600 });
        return { requestedWallMs: summary.requestedWallMs, actualProfileDurationMs: summary.actualProfileDurationMs,
            summary: 'cpu-profile-summary.json', profile: 'cpu-profile.json', scope: summary.scope,
            topSelf: summary.topSelf.slice(0, 8), truncatedNodes: summary.truncatedNodes, truncatedSamples: summary.truncatedSamples };
    } finally {
        if (running) await session.send('Profiler.stop').catch(() => undefined);
        await session.send('Profiler.disable').catch(() => undefined); await session.detach().catch(() => undefined);
    }
}
