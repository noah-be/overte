// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// AI-assisted implementation; reviewed changes and validation are recorded in REUSE.md.
import type { Avatar, Entity, Pose, Quat, Vec3 } from './world-data';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';
export interface BrowserIdentity {
    displayName: string;
    skeletonModelURL: string;
    scale: number;
}
export interface SessionPermissions {
    connect: boolean;
    rez: boolean;
    edit: boolean;
}
export type SessionEvent =
    | { type: 'status'; state: ConnectionState; message?: string; endpoint?: string }
    | { type: 'entities'; entities: Entity[] }
    | { type: 'upserts'; entities: Entity[] }
    | { type: 'remove'; ids: string[] }
    | { type: 'avatars'; avatars: Avatar[] }
    | { type: 'localAvatar'; id: string }
    | { type: 'spawn'; position: Vec3; orientation?: Quat }
    | { type: 'permissions'; permissions: SessionPermissions }
    | { type: 'microphoneMuted' }
    | { type: 'navigate'; endpoint: string }
    | { type: 'error'; message: string };

export interface SessionCallbacks {
    event(event: SessionEvent): void;
    /** One 10 ms, 24 kHz, interleaved signed PCM16 stereo mixer frame (960 bytes). */
    audio(frame: ArrayBuffer): void;
}
/** Browser-facing contract implemented by direct-session.ts. Assets are resolved
 * at the actual server component, never a mediator process. The URL resolver
 * must use current session authority and reject unresolved or revoked assets. */
export interface DirectSessionClient {
    readonly connected: boolean;
    connect(endpoint: string): Promise<void>;
    leave(): void;
    reconnect(): Promise<void>;
    sendPose(pose: Pose): void;
    sendInteraction(entityId: string): void;
    sendIdentity(identity: BrowserIdentity): void;
    /** One 10 ms, 24 kHz signed PCM16 mono microphone frame (480 bytes). */
    sendAudio(frame: ArrayBuffer): void;
    assetURL(asset: string): string;
    resolveAssetSource(asset: string): Promise<string>;
    /** Monotonically changed session generation for bounded renderer caches. */
    captureAssetAuthority(): { generation: string; assertCurrent(): void };
}
