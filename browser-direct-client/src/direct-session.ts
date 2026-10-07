// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import DomainServer, { ConnectionState as NativeState } from './protocol/vircadia/DomainServer';
import AvatarMixer from './protocol/vircadia/AvatarMixer';
import Camera from './protocol/vircadia/Camera';
import NodeList from './protocol/vircadia/domain/networking/NodeList';
import NodeType from './protocol/vircadia/domain/networking/NodeType';
import NodePermissions from './protocol/vircadia/domain/networking/NodePermissions';
import PacketReceiver from './protocol/vircadia/domain/networking/PacketReceiver';
import PacketScribe from './protocol/vircadia/domain/networking/packets/PacketScribe';
import PacketType, { type PacketTypeValue } from './protocol/vircadia/domain/networking/udt/PacketHeaders';
import NLPacket from './protocol/vircadia/domain/networking/NLPacket';
import NLPacketList from './protocol/vircadia/domain/networking/NLPacketList';
import ContextManager from './protocol/vircadia/domain/shared/ContextManager';
import Uuid from './protocol/vircadia/domain/shared/Uuid';
import type Node from './protocol/vircadia/domain/networking/Node';
import type ReceivedMessage from './protocol/vircadia/domain/networking/ReceivedMessage';
import type { BrowserIdentity, DirectSessionClient, SessionCallbacks } from './session-contract';
import type { Avatar, Entity, Pose } from './world-data';
import { BrowserAudioLevels } from './protocol/audio-levels';
import { MAX_ASSET_BYTES, nativeAssetGetBody, nativeAssetMapping, nativeAssetReply } from './protocol/native-assets';
import { answerAssetFetch, type AssetFetchLifecycle } from './protocol/asset-worker-bridge';
import type { BrowserPeerFactory } from './protocol/browser-peer';
import { normalizeEndpoint } from './protocol/endpoint';

export { normalizeEndpoint } from './protocol/endpoint';

const decoder = new TextDecoder();
const encoder = new TextEncoder();
const ZERO = { x: 0, y: 0, z: 0 };
const IDENTITY = { x: 0, y: 0, z: 0, w: 1 };
type PendingAsset = { resolve(data: DataView): void; reject(reason: Error): void; timer: ReturnType<typeof setTimeout> };

/** Explicit page-owned facilities for the same native session inside a
 * DedicatedWorker. DOM, service-worker registration and peer control remain
 * on the page; authentication, ACKs and asset bytes stay with this session. */
export interface DirectSessionEnvironment {
    peerFactory?: BrowserPeerFactory;
    pageURL?: string;
    aspectRatio?: () => number;
    prepareAssetWorker?: () => Promise<void>;
    navigate?: (endpoint: string) => void;
    worker?: boolean;
}

/** Direct native domain admission and independent service DataChannels. No
 * visitor-specific native process or translating server exists in this path. */
export class DirectSession implements DirectSessionClient {
    private readonly domain: DomainServer;
    private readonly nodeList: NodeList;
    private readonly camera: Camera;
    private readonly levels: BrowserAudioLevels;
    private readonly avatars: AvatarMixer;
    private generation: string = crypto.randomUUID();
    private endpoint = '';
    private admitted = false;
    private ready = false;
    private revision = '';
    private entities = new Map<string, Entity>();
    private sequence = 0;
    private lastMicrophone = 0;
    private codec = 'pcm';
    private frameTimer?: ReturnType<typeof setInterval>;
    private audioTimer?: ReturnType<typeof setInterval>;
    private queryTimer?: ReturnType<typeof setInterval>;
    private assetId = 0;
    private readonly pendingAssets = new Map<number, PendingAsset>();
    private readonly assetRequests = new Map<string, Promise<ArrayBuffer>>();
    private readonly assetMappings = new Map<string, Promise<{ hash: string; redirectedPath?: string }>>();
    private connectResolve?: () => void;
    private connectReject?: (reason: Error) => void;
    private connectDeadline?: ReturnType<typeof setTimeout>;
    private pose: Pose = { position: { x: 0, y: 2, z: 0 }, orientation: IDENTITY, velocity: ZERO };
    private identity: BrowserIdentity = { displayName: 'Browser visitor', skeletonModelURL: 'qrc:/meshes/defaultAvatar_full.fst', scale: 1 };
    private assetWorkerReady?: Promise<void>;

    constructor(private readonly callbacks: SessionCallbacks, private readonly environment: DirectSessionEnvironment = {}) {
        this.domain = new DomainServer([], { peerFactory: environment.peerFactory });
        this.nodeList = ContextManager.get(this.domain.contextID, NodeList) as NodeList;
        this.camera = new Camera(this.domain.contextID);
        ContextManager.set(this.domain.contextID, BrowserAudioLevels);
        this.levels = ContextManager.get(this.domain.contextID, BrowserAudioLevels) as BrowserAudioLevels;
        this.avatars = new AvatarMixer(this.domain.contextID);
        this.nodeList.addSetOfNodeTypesToNodeInterestSet(new Set([
            NodeType.EntityServer, NodeType.AvatarMixer, NodeType.AudioMixer, NodeType.AssetServer, NodeType.EntityScriptServer,
        ]));
        const receiver = this.nodeList.getPacketReceiver();
        // These native records contain variable-size QHostAddress fields. A
        // malformed/unsupported address must fail the session with a visible
        // reason instead of escaping the SDK listener as a page exception.
        for (const [type, process] of [
            [PacketType.DomainList, this.nodeList.processDomainList],
            [PacketType.DomainServerAddedNode, this.nodeList.processDomainServerAddedNode],
        ] as const) {
            receiver.registerListener(type, PacketReceiver.makeUnsourcedListenerReference(message => {
                if (!this.admitted && !this.connectReject) return;
                try { process(message); }
                catch (error) { this.fail(error instanceof Error ? error : new Error('The domain returned an invalid native node record.')); }
            }));
        }
        receiver.registerListener(PacketType.BrowserEntityData, PacketReceiver.makeSourcedListenerReference(this.receiveEntities));
        receiver.registerListener(PacketType.MixedAudio, PacketReceiver.makeSourcedListenerReference(
            (message, node) => this.receiveMixedAudio(message, node)));
        receiver.registerListener(PacketType.SelectedAudioFormat, PacketReceiver.makeSourcedListenerReference(
            (message, node) => this.receiveSelectedAudioFormat(message, node)));
        for (const type of [PacketType.SilentAudioFrame, PacketType.AudioEnvironment, PacketType.AudioStreamStats]) {
            receiver.registerListener(type, PacketReceiver.makeSourcedListenerReference((message, node) => this.receiveMixerControl(message, node)));
        }
        receiver.registerListener(PacketType.AssetMappingOperationReply, PacketReceiver.makeSourcedListenerReference(this.receiveAsset));
        receiver.registerListener(PacketType.AssetGetReply, PacketReceiver.makeSourcedListenerReference(this.receiveAsset));
        receiver.registerListener(PacketType.NoisyMute, PacketReceiver.makeSourcedListenerReference((_message, node) => {
            if (node?.getType() === NodeType.AudioMixer) {
                this.callbacks.event({ type: 'microphoneMuted' });
                this.reportError('The domain audio mixer muted the microphone.');
            }
        }));
        this.nodeList.nodeActivated.connect((node: Node) => {
            if (node.getType() === NodeType.AudioMixer) {
                this.nodeList.sendUnreliablePacket(PacketScribe.NegotiateAudioFormat.write({ codecs: ['pcm'] }), node);
            }
            if (node.getType() === NodeType.EntityServer) this.queryEntities();
        });
        this.nodeList.nodeKilled.connect((node: Node) => {
            if (this.ready && this.admitted && [NodeType.EntityServer, NodeType.AvatarMixer, NodeType.AudioMixer].includes(node.getType())) {
                this.fail(new Error('A required domain service disconnected. Reconnect to continue.'));
            }
        });
        this.nodeList.transportDisconnected.connect(({ nodeType }) => {
            if (!this.admitted && !this.connectReject) return;
            if (nodeType !== null && ![NodeType.DomainServer, NodeType.EntityServer, NodeType.AvatarMixer,
                NodeType.AudioMixer, NodeType.AssetServer].includes(nodeType)) return;
            this.fail(new Error(nodeType === null || nodeType === NodeType.DomainServer
                ? 'The direct domain connection ended. Reconnect to continue.'
                : 'A required domain service disconnected. Reconnect to continue.'));
        });
        this.avatars.myAvatar.locationChangeRequired.connect((position, changed, orientation) => {
            if (!this.admitted) return;
            this.pose = { position, orientation: changed ? orientation : this.pose.orientation, velocity: ZERO };
            this.sendPose(this.pose);
            this.callbacks.event({ type: 'spawn', position, orientation: this.pose.orientation });
        });
        this.domain.onStateChanged = (state, info) => {
            if (state === NativeState.CONNECTED) {
                this.admitted = true;
                this.callbacks.event({ type: 'localAvatar', id: this.domain.sessionUUID.stringify() });
                this.sendIdentity(this.identity);
                this.publishPermissions();
                this.queryEntities();
            } else if ([NativeState.REFUSED, NativeState.ERROR].includes(state)) {
                this.fail(new Error(info || 'The domain refused the direct connection.'));
            } else if (state === NativeState.DISCONNECTED && this.admitted) {
                this.fail(new Error('The connection to the domain ended. Reconnect to continue.'));
            }
        };
        if (!environment.worker) navigator.serviceWorker?.addEventListener('message', this.handleAssetFetch);
    }

    get connected(): boolean { return this.ready; }

    async connect(endpoint: string, requestedGeneration?: string): Promise<void> {
        const normalized = normalizeEndpoint(endpoint, this.environment?.pageURL);
        if (requestedGeneration && !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(requestedGeneration)) {
            throw new Error('Invalid browser session generation.');
        }
        this.leave();
        this.endpoint = normalized;
        this.generation = requestedGeneration || crypto.randomUUID();
        const generation = this.generation;
        await this.prepareAssetWorker();
        if (generation !== this.generation) throw new Error('The connection attempt was cancelled.');
        this.callbacks.event({ type: 'status', state: 'connecting', message: 'Joining the domain directly and loading its entities…', endpoint: normalized });
        const pending = new Promise<void>((resolve, reject) => {
            this.connectResolve = resolve;
            this.connectReject = reject;
            this.connectDeadline = setTimeout(() => this.fail(new Error('The domain did not provide its browser world within 25 seconds. Check that the domain and assignment servers support the direct transport.')), 25000);
        });
        this.frameTimer = setInterval(() => {
            if (!this.admitted) return;
            this.camera.position = this.pose.position;
            this.camera.orientation = this.pose.orientation;
            this.camera.aspectRatio = this.environment.aspectRatio?.()
                ?? Math.max(0.1, window.innerWidth / Math.max(1, window.innerHeight));
            this.camera.update();
            this.avatars.update();
            this.publishAvatars();
        }, 33);
        this.audioTimer = setInterval(() => {
            if (!this.admitted || performance.now() - this.lastMicrophone < 15) return;
            const mixer = this.nodeList.soloNodeOfType(NodeType.AudioMixer);
            if (!mixer?.getActiveSocket()) return;
            this.nodeList.sendUnreliablePacket(PacketScribe.SilentAudioFrame.write({
                sequenceNumber: this.sequence++ & 0xffff, codecName: this.codec, numSilentSamples: 240,
                ...this.audioPosition(),
            }), mixer);
        }, 10);
        this.queryTimer = setInterval(() => { this.queryEntities(); this.publishPermissions(); }, 1000);
        this.domain.connect(normalized);
        return pending;
    }

    leave(): void {
        this.admitted = false;
        this.ready = false;
        this.levels.clear();
        this.generation = crypto.randomUUID();
        clearInterval(this.frameTimer); clearInterval(this.audioTimer); clearInterval(this.queryTimer);
        clearTimeout(this.connectDeadline);
        this.connectReject?.(new Error('The connection attempt was cancelled.'));
        this.connectResolve = undefined; this.connectReject = undefined;
        for (const pending of this.pendingAssets.values()) { clearTimeout(pending.timer); pending.reject(new Error('The asset session ended.')); }
        this.pendingAssets.clear(); this.assetRequests.clear(); this.assetMappings.clear(); this.entities.clear(); this.revision = '';
        this.domain.disconnect();
        this.callbacks.event({ type: 'entities', entities: [] });
        this.callbacks.event({ type: 'avatars', avatars: [] });
        this.callbacks.event({ type: 'status', state: 'disconnected', message: 'Disconnected', endpoint: this.endpoint });
    }

    reconnect(): Promise<void> {
        if (!this.endpoint) return Promise.reject(new Error('Select a domain first.'));
        return this.connect(this.endpoint);
    }

    sendPose(pose: Pose): void {
        if (![...Object.values(pose.position), ...Object.values(pose.orientation)].every(Number.isFinite)) return;
        this.pose = pose;
        this.avatars.myAvatar.position = pose.position;
        this.avatars.myAvatar.orientation = pose.orientation;
    }

    sendIdentity(identity: BrowserIdentity): void {
        if (identity.displayName.length > 128 || identity.skeletonModelURL.length > 4096 || !Number.isFinite(identity.scale)) return;
        this.identity = identity;
        this.avatars.myAvatar.displayName = identity.displayName;
        this.avatars.myAvatar.skeletonModelURL = identity.skeletonModelURL;
        this.avatars.myAvatar.scale = identity.scale;
    }

    sendInteraction(entityId: string): void {
        const entity = this.entities.get(entityId);
        if (!this.ready || !entity) return;
        if (typeof entity.href === 'string' && /^wss?:\/\//.test(entity.href)) {
            if (this.environment.navigate) this.environment.navigate(entity.href);
            else void this.connect(entity.href).catch((error: Error) => this.reportError(error.message));
            return;
        }
        const server = this.nodeList.soloNodeOfType(NodeType.EntityScriptServer);
        if (!server?.getActiveSocket()) { this.reportError('This entity has no active server interaction service.'); return; }
        // Native QUuid JSON retains braces; normalize only the packet value,
        // keeping the original entity key for current-session lookup and UI.
        const nativeId = entityId.startsWith('{') && entityId.endsWith('}') ? entityId.slice(1, -1) : entityId;
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(nativeId)) {
            this.reportError('The selected entity has an invalid native identifier.'); return;
        }
        const packet = NLPacketList.create(PacketType.EntityScriptCallMethod, null, true, true);
        packet.writePrimitive(new Uuid(nativeId));
        packet.writeString('clickDownOnEntity');
        packet.writePrimitive(0, 2);
        this.nodeList.sendPacketList(packet, server);
    }

    sendAudio(frame: ArrayBuffer): void {
        if (!this.admitted || this.codec !== 'pcm' || frame.byteLength !== 480) return;
        const mixer = this.nodeList.soloNodeOfType(NodeType.AudioMixer);
        if (!mixer?.getActiveSocket()) return;
        this.lastMicrophone = performance.now();
        this.levels.update(frame);
        this.nodeList.sendUnreliablePacket(PacketScribe.MicrophoneAudioNoEcho.write({
            sequenceNumber: this.sequence++ & 0xffff, codecName: 'pcm', isStereo: false,
            audioBuffer: new Uint8Array(frame), ...this.audioPosition(),
        }), mixer);
    }

    private receiveMixedAudio(message: ReceivedMessage, node: Node | null): void {
        if (!this.admitted || node?.getType() !== NodeType.AudioMixer) return;
        try {
            const audio = PacketScribe.MixedAudio.read(message.getMessage());
            if (!['pcm', ''].includes(audio.codecName) || audio.audioBuffer.byteLength !== 960) {
                throw new Error('Unsupported native mixed audio.');
            }
            this.callbacks.audio(audio.audioBuffer.buffer.slice(audio.audioBuffer.byteOffset,
                audio.audioBuffer.byteOffset + audio.audioBuffer.byteLength) as ArrayBuffer);
        } catch {
            this.reportError('The audio mixer returned an invalid or unsupported audio frame.');
        }
    }

    private receiveSelectedAudioFormat(message: ReceivedMessage, node: Node | null): void {
        if (!this.admitted || node?.getType() !== NodeType.AudioMixer) return;
        try {
            const data = message.getMessage();
            if (data.byteLength < 4 || data.getUint32(0, true) !== data.byteLength - 4) {
                throw new Error('Invalid native audio format.');
            }
            const selected = PacketScribe.SelectedAudioFormat.read(data).selectedCodecName;
            if (!['pcm', ''].includes(selected)) throw new Error('Unsupported native audio format.');
            // Native InboundAudioStream explicitly defines empty codec and PCM
            // as equivalent, including the mixer's no-plugin PCM fallback.
            this.codec = 'pcm';
        } catch {
            this.reportError('This browser requires a valid native PCM audio format from the mixer.');
        }
    }

    private receiveMixerControl(message: ReceivedMessage, node: Node | null): void {
        if (!this.admitted || node?.getType() !== NodeType.AudioMixer) return;
        try {
            const data = message.getMessage();
            if (message.getType() === PacketType.SilentAudioFrame) {
                const silence = PacketScribe.SilentAudioFrame.read(data);
                if (!['pcm', ''].includes(silence.codecName) || silence.numSilentSamples !== 480) {
                    throw new Error('Unsupported native mixer silence.');
                }
                this.callbacks.audio(new ArrayBuffer(960));
            } else if (message.getType() === PacketType.AudioEnvironment) {
                // AudioMixerWorker sends bit0 and optional two float32 values.
                // Zone reverb rendering is currently unsupported; consume its
                // valid control packet without claiming that effect is applied.
                if (data.byteLength < 1 || (data.getUint8(0) & ~1) !== 0
                    || data.byteLength !== (data.getUint8(0) ? 9 : 1)) {
                    throw new Error('Invalid native mixer environment.');
                }
            } else if (message.getType() === PacketType.AudioStreamStats) {
                // Native AudioStreamStats has a compile-time 152-byte size.
                // Its START/END flags and count precede the bounded records.
                // Stream IDs and statistics are not retained by this client.
                if (data.byteLength < 3 || (data.getUint8(0) & ~3) !== 0
                    || data.byteLength !== 3 + data.getUint16(1, true) * 152) {
                    throw new Error('Invalid native mixer stream statistics.');
                }
            }
        } catch {
            this.reportError('The audio mixer returned an invalid control frame.');
        }
    }

    assetURL(asset: string): string {
        if (/^atp:/i.test(asset)) {
            if (!this.admitted) throw new Error('ATP assets require an active domain session.');
            const path = asset.replace(/^atp:(?:\/\/)?/i, '').replace(/^\/+/, '');
            if (!path || path.includes('\0') || path.split('/').includes('..')) throw new Error('Invalid ATP asset path.');
            return `${import.meta.env.BASE_URL}_overte-atp/${this.generation}/${path}`;
        }
        const url = new URL(asset, this.environment?.pageURL || location.href);
        if (!['https:', 'http:', 'blob:'].includes(url.protocol)) throw new Error('Unsupported asset URL.');
        return url.toString();
    }

    /** Resolve native baked mappings before model parsing, so relative
     * textures use the server's redirected model directory. */
    async resolveAssetSource(asset: string): Promise<string> {
        if (!/^atp:/i.test(asset)) {
            const page = new URL(this.environment?.pageURL || location.href);
            const url = new URL(asset, page);
            const prefix = `${import.meta.env.BASE_URL}_overte-atp/${this.generation}/`;
            if (url.origin === page.origin && url.pathname.startsWith(prefix)) {
                asset = `atp:/${url.pathname.slice(prefix.length)}${url.search}`;
            }
        }
        if (!/^atp:/i.test(asset)) return asset;
        const generation = this.generation;
        const path = asset.replace(/^atp:(?:\/\/)?/i, '').replace(/^\/+/, '');
        this.assetURL(asset); // Validate the current session and path.
        if (/^([a-f0-9]{64})(?:\.[^/]*)?$/i.test(path)) return asset;
        const mapping = await this.mapATP(path, generation);
        if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
        return mapping.redirectedPath ? `atp:${mapping.redirectedPath}` : asset;
    }

    captureAssetAuthority(): { generation: string; assertCurrent(): void } {
        const generation = this.generation;
        return { generation, assertCurrent: () => {
            if (generation !== this.generation || !this.admitted) throw new Error('The asset session is no longer active.');
        } };
    }

    /** Page mirror contains no native node secrets or transport credentials. */
    assetSessionState(): { admitted: boolean; connected: boolean } {
        return { admitted: this.admitted, connected: this.ready };
    }

    /** The requesting ServiceWorker's transferred port receives the validated
     * result directly, preserving structured cloning for shared fetch bytes. */
    acceptAssetFetch(event: { data: unknown; ports: readonly MessagePort[] }, lifecycle?: AssetFetchLifecycle): boolean {
        return answerAssetFetch(event, (path, generation) => this.getATP(path, generation), lifecycle);
    }

    private audioPosition() {
        return { audioPosition: this.pose.position, audioOrientation: this.pose.orientation,
            avatarBoundingBoxCorner: { x: this.pose.position.x - .3, y: this.pose.position.y - .9, z: this.pose.position.z - .3 },
            avatarBoundingBoxScale: { x: .6, y: 1.8, z: .6 } };
    }

    private queryEntities(): void {
        if (!this.admitted) return;
        const server = this.nodeList.soloNodeOfType(NodeType.EntityServer);
        if (!server?.getActiveSocket()) return;
        this.sendBody(PacketType.BrowserEntityQuery, encoder.encode(JSON.stringify({ version: 1, revision: this.revision })), server);
    }

    private receiveEntities = (message: ReceivedMessage, server: Node | null): void => {
        if (!this.admitted || server?.getType() !== NodeType.EntityServer) return;
        const bytes = message.getMessage();
        if (bytes.byteLength > 16 * 1024 * 1024 + 1024) { this.fail(new Error('The domain entity message exceeds the browser limit.')); return; }
        try {
            const result = JSON.parse(decoder.decode(bytes)) as { version: number; revision: string; entities?: Entity[]; error?: string };
            if (result.error) throw new Error(result.error);
            if (result.version !== 1 || !/^[a-f0-9]{64}$/.test(result.revision)) throw new Error('Unsupported browser entity protocol.');
            if (result.entities) {
                if (!Array.isArray(result.entities) || result.entities.some((e) => typeof e.id !== 'string' || typeof e.type !== 'string')) throw new Error('The domain returned invalid entities.');
                const next = new Map(result.entities.map((entity) => [entity.id, entity]));
                if (!this.ready) this.callbacks.event({ type: 'entities', entities: result.entities });
                else {
                    this.callbacks.event({ type: 'remove', ids: [...this.entities.keys()].filter((id) => !next.has(id)) });
                    this.callbacks.event({ type: 'upserts', entities: result.entities.filter((e) => JSON.stringify(e) !== JSON.stringify(this.entities.get(e.id))) });
                }
                this.entities = next;
            }
            this.revision = result.revision;
            if (!this.ready) {
                this.ready = true;
                clearTimeout(this.connectDeadline);
                this.callbacks.event({ type: 'status', state: 'connected', message: `Connected directly · ${this.entities.size} entities`, endpoint: this.endpoint });
                this.connectResolve?.(); this.connectResolve = undefined; this.connectReject = undefined;
            }
        } catch (error) { this.fail(error instanceof Error ? error : new Error('The domain returned invalid entity data.')); }
    };

    private publishAvatars(): void {
        const avatars: Avatar[] = [];
        for (const id of this.avatars.avatarList.getAvatarIDs()) {
            // The SDK stores its local MyAvatar under a NULL sentinel. The UI
            // supplies the real admitted local avatar separately.
            if (id.isNull()) continue;
            const avatar = this.avatars.avatarList.getAvatar(id);
            const skeleton = avatar.skeleton;
            avatars.push({ id: id.stringify(), displayName: avatar.sessionDisplayName || avatar.displayName,
                position: avatar.position, orientation: avatar.orientation, scale: avatar.scale,
                skeletonModelURL: avatar.skeletonModelURL, jointNames: skeleton.map((joint) => joint.jointName),
                // Native rotations are absolute rig-frame values; translations
                // are parent-relative model coordinates. Null selects the
                // skeleton's actual default pose, never identity/zero.
                jointParents: skeleton.map((joint) => joint.parentIndex),
                jointDefaultRotations: skeleton.map((joint) => ({ ...joint.defaultRotation })),
                jointDefaultTranslations: skeleton.map((joint) => ({ ...joint.defaultTranslation })),
                jointDefaultScales: skeleton.map((joint) => joint.defaultScale),
                jointRotations: avatar.jointRotations.map((q) => q === null ? null : ({ ...q })),
                jointTranslations: avatar.jointTranslations.map((v) => v === null ? null : ({ ...v })) });
        }
        this.callbacks.event({ type: 'avatars', avatars });
    }

    private publishPermissions(): void {
        if (!this.admitted) return;
        const permission = this.nodeList.getPermissions();
        this.callbacks.event({ type: 'permissions', permissions: { connect: permission.can(NodePermissions.Permission.canConnectToDomain),
            rez: permission.can(NodePermissions.Permission.canRezPermanentEntities), edit: permission.can(NodePermissions.Permission.canAdjustLocks) } });
    }

    private sendBody(type: PacketTypeValue, body: Uint8Array, server: Node, reliable = false): void {
        const packet = NLPacket.create(type, -1, reliable);
        const message = packet.getMessageData();
        new Uint8Array(message.data.buffer).set(body, message.dataPosition);
        message.packetSize = message.dataPosition + body.byteLength;
        if (reliable) this.nodeList.sendPacket(packet, server); else this.nodeList.sendUnreliablePacket(packet, server);
    }

    private receiveAsset = (message: ReceivedMessage, server: Node | null): void => {
        if (!this.admitted || server?.getType() !== NodeType.AssetServer) return;
        const data = message.getMessage();
        const offset = message.getType() === PacketType.AssetGetReply ? 32 : 0;
        if (data.byteLength < offset + 5 || data.byteLength > MAX_ASSET_BYTES + 64) return;
        const id = data.getUint32(offset, true);
        const pending = this.pendingAssets.get(id);
        if (!pending) return;
        this.pendingAssets.delete(id); clearTimeout(pending.timer);
        pending.resolve(data);
    };

    private requestAsset(id: number, send: () => void): Promise<DataView> {
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => { this.pendingAssets.delete(id); reject(new Error('The asset server did not answer in time.')); }, 20000);
            this.pendingAssets.set(id, { resolve, reject, timer });
            try { send(); } catch (error) { clearTimeout(timer); this.pendingAssets.delete(id); reject(error); }
        });
    }

    private async getATP(path: string, generation: string): Promise<ArrayBuffer> {
        if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
        const existing = this.assetRequests.get(path);
        if (existing) return existing;
        const request = this.fetchATP(path, generation);
        this.assetRequests.set(path, request);
        // Deduplicate in-flight work without retaining unbounded world asset bytes.
        void request.finally(() => {
            if (this.assetRequests.get(path) === request) this.assetRequests.delete(path);
        }).catch(() => {});
        return request;
    }

    private async fetchATP(path: string, generation: string): Promise<ArrayBuffer> {
        const server = await this.assetServer(generation);
        let hash = path.match(/^([a-f0-9]{64})(?:\.[^/]*)?$/i)?.[1]?.toLowerCase();
        if (!hash) {
            hash = (await this.mapATP(path, generation)).hash;
        }
        if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
        const id = ++this.assetId;
        const body = nativeAssetGetBody(id, hash);
        const reply = await this.requestAsset(id, () => this.sendBody(PacketType.AssetGet, body, server, true));
        const result = nativeAssetReply(reply, id, hash);
        const actual = [...new Uint8Array(await crypto.subtle.digest('SHA-256', result))].map((b) => b.toString(16).padStart(2, '0')).join('');
        if (hash !== actual) throw new Error('The ATP asset did not match its native content hash.');
        if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
        return result;
    }

    private async assetServer(generation: string): Promise<Node> {
        const deadline = performance.now() + 10000;
        while (this.admitted && generation === this.generation && performance.now() < deadline) {
            const server = this.nodeList.soloNodeOfType(NodeType.AssetServer);
            if (server?.getActiveSocket()) return server;
            await new Promise<void>(resolve => setTimeout(resolve, 100));
        }
        if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
        throw new Error('This domain has no connected ATP asset server.');
    }

    private mapATP(path: string, generation: string): Promise<{ hash: string; redirectedPath?: string }> {
        if (!this.admitted || generation !== this.generation) return Promise.reject(new Error('The ATP session has ended.'));
        const existing = this.assetMappings.get(path);
        if (existing) return existing;
        if (this.assetMappings.size >= 4096) return Promise.reject(new Error('This domain exceeds the browser asset mapping limit.'));
        const mapping = (async () => {
            const server = await this.assetServer(generation), id = ++this.assetId;
            const reply = await this.requestAsset(id, () => {
                const packet = NLPacketList.create(PacketType.AssetMappingOperation, null, true, true);
                packet.writePrimitive(id, 4); packet.writePrimitive(0, 1);
                packet.writeString(`/${decodeURIComponent(path)}`);
                this.nodeList.sendPacketList(packet, server);
            });
            if (!this.admitted || generation !== this.generation) throw new Error('The ATP session has ended.');
            const result = nativeAssetMapping(reply, id);
            if (result.redirectedPath && this.assetMappings.size < 4096) {
                this.assetMappings.set(result.redirectedPath.replace(/^\/+/, ''), Promise.resolve({ hash: result.hash }));
            }
            return result;
        })();
        this.assetMappings.set(path, mapping);
        void mapping.catch(() => { if (this.assetMappings.get(path) === mapping) this.assetMappings.delete(path); });
        return mapping;
    }

    private handleAssetFetch = (event: MessageEvent): void => {
        this.acceptAssetFetch(event);
    };

    private prepareAssetWorker(): Promise<void> {
        if (this.environment?.prepareAssetWorker) return this.environment.prepareAssetWorker();
        this.assetWorkerReady ??= (async () => {
            if (!navigator.serviceWorker) throw new Error('Use HTTPS or localhost so domain assets can load in the browser.');
            await navigator.serviceWorker.register(`${import.meta.env.BASE_URL}asset-worker.js`, { scope: import.meta.env.BASE_URL });
            await navigator.serviceWorker.ready;
            if (!navigator.serviceWorker.controller) await new Promise<void>((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error('The browser asset worker did not activate. Reload the page.')), 10000);
                navigator.serviceWorker.addEventListener('controllerchange', () => { clearTimeout(timeout); resolve(); }, { once: true });
            });
        })();
        return this.assetWorkerReady;
    }

    private reportError(message: string): void { this.callbacks.event({ type: 'error', message }); }
    private fail(error: Error): void {
        const reject = this.connectReject;
        this.connectReject = undefined;
        this.leave();
        this.callbacks.event({ type: 'status', state: 'error', message: error.message, endpoint: this.endpoint });
        this.reportError(error.message);
        reject?.(error);
    }
}
