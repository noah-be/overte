// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import { randomBytes } from 'node:crypto';

// Qt's native WebSocket control-Pong handling is unreliable under real domain
// load. Require a fresh application-level round trip instead; outbound traffic
// and ordinary script heartbeats cannot satisfy this challenge.
export class NativeHeartbeat {
    constructor({ send, now = Date.now, nonce = () => randomBytes(16).toString('hex') }) {
        this.send = send; this.now = now; this.nonce = nonce; this.pending = null;
    }
    receive(message) {
        if (!this.pending || message.type !== 'nativePong' || message.nonce !== this.pending.nonce
            || this.now() >= this.pending.deadline) return false;
        this.pending = null;
        return true;
    }
    tick() {
        if (this.pending) return this.now() < this.pending.deadline;
        this.pending = { nonce: this.nonce(), deadline: this.now() + 30000 };
        this.send({ type: 'nativePing', nonce: this.pending.nonce, deadline: this.pending.deadline });
        return true;
    }
}
