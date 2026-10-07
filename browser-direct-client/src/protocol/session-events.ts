// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { SessionEvent } from '../session-contract';

export type SessionDelivery = {
    type: 'event'; ticket: number; generation: string;
    authority: { admitted: boolean; connected: boolean }; event: SessionEvent;
};

/** Only one event crosses to the renderer before acknowledgment. Snapshots and
 * repeated unsent entity properties coalesce. Deletions and lifecycle barriers
 * retain their order. Native receive/ACK processing continues independently. */
export class SessionEventOutbox {
    private pending: Omit<SessionDelivery, 'ticket' | 'type'>[] = [];
    private outstanding?: number;
    private nextTicket = 0;
    static readonly LIMIT = 32;
    static readonly ENTITY_LIMIT = 65536;
    constructor(private readonly send: (message: SessionDelivery) => void) {}

    enqueue(generation: string, authority: SessionDelivery['authority'], event: SessionEvent): boolean {
        if ((event.type === 'remove' && !event.ids.length) || (event.type === 'upserts' && !event.entities.length)) return true;
        if (event.type === 'upserts') {
            if (event.entities.length > SessionEventOutbox.ENTITY_LIMIT) return false;
            // Only unsent updates may merge, and only across independent avatar
            // and permission snapshots. A real removal, full snapshot or any
            // lifecycle event is a barrier, including delete/recreate of an ID.
            const previous = this.pending.slice().reverse().find(item => !['avatars', 'permissions'].includes(item.event.type));
            if (previous?.generation === generation && previous.event.type === 'upserts') {
                const entities = new Map(previous.event.entities.map(entity => [entity.id, entity]));
                for (const entity of event.entities) entities.set(entity.id, entity);
                if (entities.size > SessionEventOutbox.ENTITY_LIMIT) return false;
                previous.event = { type: 'upserts', entities: [...entities.values()] };
                previous.authority = { ...authority };
                return true;
            }
        }
        if (['avatars', 'permissions'].includes(event.type)) {
            const previous = this.pending.findIndex(item => item.generation === generation && item.event.type === event.type);
            if (previous >= 0) {
                // Keep a live snapshot's turn among independent world updates.
                // Moving every replacement to the tail can starve it forever
                // when entity edits keep arriving behind a slow renderer.
                const independent = this.pending.slice(previous + 1).every(item => item.generation === generation
                    && ['upserts', 'avatars', 'permissions'].includes(item.event.type));
                if (independent) {
                    this.pending[previous] = { generation, authority: { ...authority }, event };
                    return true;
                }
                // A newer snapshot must follow a real deletion, full snapshot
                // or lifecycle barrier; retain the existing retirement order.
                this.pending.splice(previous, 1);
            }
        }
        if (this.pending.length >= SessionEventOutbox.LIMIT) return false;
        this.pending.push({ generation, authority: { ...authority }, event });
        this.flush(); return true;
    }

    acknowledge(ticket: number): void {
        if (ticket !== this.outstanding) return;
        this.outstanding = undefined; this.flush();
    }

    /** New joins retire pending old updates. The one already posted is still
     * acknowledged, but the page rejects its old generation before delivery. */
    retire(): void { this.pending = []; }
    get queued(): number { return this.pending.length; }

    private flush(): void {
        if (this.outstanding !== undefined || !this.pending.length) return;
        const item = this.pending.shift()!;
        this.outstanding = ++this.nextTicket;
        this.send({ type: 'event', ticket: this.outstanding, ...item });
    }
}
