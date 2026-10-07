// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0

// Visitor-owned bytes only. Every reader still passes HTTP ownership and current
// native permission checks; this cache is never shared between native sessions.
export class SessionAssets {
    constructor({ authority, load, maximumActive = 16, maximumQueued = 128,
        maximumReaders = 512, maximumBytes = 128 * 1024 * 1024, maximumEntries = 256,
        ttl = 30000, readerTimeout = 30000, now = Date.now }) {
        this.authority = authority; this.load = load; this.maximumActive = maximumActive;
        this.maximumQueued = maximumQueued; this.maximumReaders = maximumReaders;
        this.maximumBytes = maximumBytes; this.maximumEntries = maximumEntries;
        this.ttl = ttl; this.readerTimeout = readerTimeout; this.now = now; this.entries = new Map(); this.jobs = new Map();
        this.queue = []; this.active = 0; this.readers = 0; this.bytes = 0;
        this.generation = 0; this.closed = false;
        this.metrics = { loads: 0, hits: 0, shared: 0, downloadedBytes: 0 };
    }
    current(authority, generation) {
        return !this.closed && generation === this.generation && authority !== null && authority === this.authority();
    }
    request(url, signal) {
        const authority = this.authority(), generation = this.generation;
        if (!this.current(authority, generation)) return Promise.reject(Error('Asset service is not connected.'));
        if (signal?.aborted) return Promise.reject(Error('Asset reader cancelled.'));
        if (this.readers >= this.maximumReaders) return Promise.reject(Error('Too many asset readers.'));
        const key = `${authority}\n${url}`;
        const cached = this.entries.get(key);
        if (cached) {
            this.entries.delete(key);
            if (cached.expires > this.now()) { this.entries.set(key, cached); this.metrics.hits++; return Promise.resolve({ ...cached.value, source: 'memory' }); }
            this.bytes -= cached.value.data.length;
        }
        let job = this.jobs.get(key);
        const shared = Boolean(job);
        if (!job) {
            if (this.active >= this.maximumActive && this.queue.length >= this.maximumQueued) return Promise.reject(Error('Too many queued asset requests.'));
            job = { key, url, authority, generation, readers: new Set(), controller: new AbortController(), active: false };
            this.jobs.set(key, job); this.queue.push(job);
        } else this.metrics.shared++;
        const result = new Promise((resolve, reject) => {
            const reader = { resolve, reject, signal, source: shared ? 'shared' : 'download' };
            reader.abort = () => {
                if (!job.readers.delete(reader)) return;
                this.readers--; clearTimeout(reader.timer); signal?.removeEventListener('abort', reader.abort); reject(Error('Asset reader cancelled or timed out.'));
                if (!job.readers.size) {
                    job.controller.abort();
                    if (this.jobs.get(key) === job) this.jobs.delete(key);
                    if (!job.active) { this.queue = this.queue.filter(value => value !== job); this.jobs.delete(key); }
                }
            };
            reader.timer = setTimeout(reader.abort, this.readerTimeout);
            job.readers.add(reader); this.readers++; signal?.addEventListener('abort', reader.abort, { once: true });
        });
        this.drain(); return result;
    }
    drain() {
        while (!this.closed && this.active < this.maximumActive && this.queue.length) {
            const job = this.queue.shift();
            if (!job.readers.size || !this.current(job.authority, job.generation)) { this.finish(job, Error('The asset session changed.')); continue; }
            job.active = true; this.active++; this.metrics.loads++;
            Promise.resolve().then(() => {
                if (!this.current(job.authority, job.generation) || job.controller.signal.aborted) throw Error('The asset session changed.');
                return this.load(job.url, job.controller.signal);
            }).then(value => {
                if (!this.current(job.authority, job.generation) || job.controller.signal.aborted) throw Error('The asset session changed.');
                if (!Buffer.isBuffer(value?.data) || value.data.length > 32 * 1024 * 1024 || typeof value.type !== 'string') throw Error('Invalid or oversized asset.');
                this.metrics.downloadedBytes += value.data.length;
                if (value.data.length <= this.maximumBytes) {
                    this.entries.set(job.key, { value, expires: this.now() + this.ttl }); this.bytes += value.data.length;
                    while (this.bytes > this.maximumBytes || this.entries.size > this.maximumEntries) {
                        const oldest = this.entries.keys().next().value;
                        this.bytes -= this.entries.get(oldest).value.data.length; this.entries.delete(oldest);
                    }
                }
                this.finish(job, null, value);
            }, error => this.finish(job, error)).catch(error => this.finish(job, error));
        }
    }
    finish(job, error, value) {
        if (job.finished) return;
        job.finished = true;
        if (job.active) this.active--;
        if (this.jobs.get(job.key) === job) this.jobs.delete(job.key);
        for (const reader of job.readers) {
            this.readers--; clearTimeout(reader.timer); reader.signal?.removeEventListener('abort', reader.abort);
            if (error) reader.reject(error); else reader.resolve({ ...value, source: reader.source });
        }
        job.readers.clear(); this.drain();
    }
    reset() {
        this.generation++; this.entries.clear(); this.bytes = 0;
        const jobs = [...this.jobs.values()]; this.jobs.clear(); this.queue = [];
        for (const job of jobs) {
            job.controller.abort();
            // Active loaders retain their concurrency slot until they actually stop.
            // ATP callbacks cannot be cancelled in the native Assets scripting API.
            for (const reader of job.readers) {
                this.readers--; clearTimeout(reader.timer); reader.signal?.removeEventListener('abort', reader.abort); reader.reject(Error('The asset session changed.'));
            }
            job.readers.clear(); if (!job.active) job.finished = true;
        }
    }
    close() { this.closed = true; this.reset(); }
}
