// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// These applications execute locally in the browser; their inputs are DOM controls.
import type { Avatar, Entity } from './world-data';
import type { BrowserIdentity, ConnectionState, SessionPermissions } from './session-contract';
import type { BrowserGraphicsSettings } from '../shared/browser-graphics.mjs';
import { browserIdentity, domainEndpoint } from './local-tablet-data';

type AppName = 'Domain' | 'People' | 'Avatar' | 'Audio' | 'Graphics' | 'Snapshot';
export interface LocalTabletOptions {
    connect(endpoint: string): Promise<void>;
    leave(): void;
    reconnect(): Promise<void>;
    identity(identity: BrowserIdentity): void;
    microphone(enabled: boolean): Promise<boolean>;
    sound(enabled: boolean): void;
    graphics(): BrowserGraphicsSettings;
    applyGraphics(settings: BrowserGraphicsSettings): void;
    snapshot(): Promise<Blob>;
    thirdPerson(enabled: boolean): void;
    visible(visible: boolean): void;
    onStatus(message: string, kind?: string): void;
}

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text = ''): HTMLElementTagNameMap[K] {
    const result = document.createElement(tag); result.className = className; result.textContent = text; return result;
}

export class LocalTablet {
    private readonly abort = new AbortController();
    private readonly pages = new Map<AppName, HTMLElement>();
    private readonly tabs = new Map<AppName, HTMLButtonElement>();
    private readonly state = element('p', 'tablet-state', 'Disconnected');
    private readonly people = element('ul', 'people-list');
    private readonly selection = element('p', 'selection-info', 'Aim at a world object and press E to inspect it.');
    private readonly domain = element('input');
    private readonly join = element('button', 'primary', 'Join domain');
    private readonly leaveButton = element('button', '', 'Leave');
    private readonly reconnectButton = element('button', '', 'Reconnect');
    private readonly displayName = element('input');
    private readonly avatarURL = element('input');
    private readonly avatarScale = element('input');
    private readonly selfView = element('input');
    private readonly microphoneButton = element('button', 'primary', 'Enable microphone');
    private readonly sound = element('input');
    private readonly audioNotice = element('p', 'muted-text', 'Microphone is off.');
    private connected = false;
    private muted = true;
    private shown = true;
    private disposed = false;
    private current: AppName = 'Domain';
    private selectedID?: string;
    private downloadURLs = new Set<string>();

    constructor(readonly container: HTMLElement, private readonly options: LocalTabletOptions, initial: BrowserIdentity, endpoint = '') {
        const heading = element('div', 'tablet-heading');
        heading.append(element('div', '', 'Tablet'));
        const close = element('button', 'icon-button', '×'); close.type = 'button'; close.setAttribute('aria-label', 'Close tablet');
        this.listen(close, 'click', () => this.show(false)); heading.append(close);
        const nav = element('nav', 'tablet-nav'); nav.setAttribute('aria-label', 'Tablet applications');
        const content = element('div', 'tablet-content');
        for (const name of ['Domain', 'People', 'Avatar', 'Audio', 'Graphics', 'Snapshot'] as AppName[]) {
            const button = element('button', 'tablet-tab', name); button.type = 'button';
            button.setAttribute('aria-controls', `tablet-${name.toLowerCase()}`);
            this.listen(button, 'click', () => this.open(name)); nav.append(button); this.tabs.set(name, button);
            const page = element('section', 'tablet-page'); page.id = `tablet-${name.toLowerCase()}`;
            page.append(element('h1', '', name)); this.pages.set(name, page); content.append(page);
        }
        container.replaceChildren(heading, nav, content, this.state);
        this.buildDomain(endpoint);
        this.buildPeople();
        this.buildAvatar(initial);
        this.buildAudio();
        this.buildGraphics();
        this.buildSnapshot();
        this.setConnection('disconnected');
        this.open('Domain');
    }

    private listen(target: EventTarget, type: string, callback: (event: Event) => void): void {
        target.addEventListener(type, callback, { signal: this.abort.signal });
    }
    private label(text: string, input: HTMLElement): HTMLElement {
        const label = element('label', 'field'); label.append(element('span', '', text), input); return label;
    }
    private run(operation: () => Promise<unknown>): void {
        void operation().catch(error => this.options.onStatus(error instanceof Error ? error.message : String(error), 'error'));
    }
    private attempt(operation: () => void): void {
        try { operation(); } catch (error) { this.options.onStatus(error instanceof Error ? error.message : String(error), 'error'); }
    }
    private buildDomain(endpoint: string): void {
        const page = this.pages.get('Domain')!;
        page.append(element('p', 'intro', 'Choose a domain and meet the people there.'));
        const form = element('form');
        this.domain.name = 'endpoint'; this.domain.type = 'url'; this.domain.required = true;
        this.domain.placeholder = 'https://your-domain.example'; this.domain.value = endpoint; this.domain.setAttribute('autocomplete', 'url');
        form.append(this.label('Domain server address', this.domain));
        this.join.type = 'submit'; form.append(this.join);
        this.listen(form, 'submit', event => { event.preventDefault(); this.run(async () => { await this.options.connect(domainEndpoint(this.domain.value)); }); });
        const controls = element('div', 'button-row'); this.leaveButton.type = this.reconnectButton.type = 'button';
        this.listen(this.leaveButton, 'click', () => this.options.leave());
        this.listen(this.reconnectButton, 'click', () => this.run(() => this.options.reconnect()));
        controls.append(this.leaveButton, this.reconnectButton); page.append(form, controls);
        page.append(element('p', 'muted-text', 'The domain must support browser connections. Your world renders on this device.'));
        page.append(element('h2', '', 'Selected object'), this.selection);
    }
    private buildPeople(): void {
        this.pages.get('People')!.append(element('p', 'intro', 'People currently in this domain.'), this.people);
        this.setPeople([]);
    }
    private buildAvatar(initial: BrowserIdentity): void {
        const page = this.pages.get('Avatar')!, form = element('form');
        this.displayName.value = initial.displayName; this.displayName.maxLength = 128; this.displayName.required = true;
        this.avatarURL.value = initial.skeletonModelURL; this.avatarURL.maxLength = 4096;
        this.avatarScale.type = 'number'; this.avatarScale.min = '0.05'; this.avatarScale.max = '20'; this.avatarScale.step = '0.05'; this.avatarScale.value = String(initial.scale);
        form.append(this.label('Display name', this.displayName), this.label('Avatar model or FST address', this.avatarURL), this.label('Avatar scale', this.avatarScale));
        const apply = element('button', 'primary', 'Apply avatar'); apply.type = 'submit'; form.append(apply);
        this.listen(form, 'submit', event => { event.preventDefault(); this.attempt(() => {
            this.options.identity(browserIdentity(this.displayName.value, this.avatarURL.value, Number(this.avatarScale.value)));
        }); });
        this.selfView.type = 'checkbox';
        this.listen(this.selfView, 'change', () => this.options.thirdPerson(this.selfView.checked));
        page.append(form, this.label('View my avatar', this.selfView));
    }
    private buildAudio(): void {
        const page = this.pages.get('Audio')!;
        page.append(element('p', 'intro', 'Talk with people nearby. You control microphone access.'));
        this.microphoneButton.type = 'button';
        this.listen(this.microphoneButton, 'click', () => this.run(async () => {
            await this.options.microphone(this.muted); this.setMicrophone(this.muted);
        }));
        this.sound.type = 'checkbox'; this.sound.checked = true;
        this.listen(this.sound, 'change', () => this.options.sound(this.sound.checked));
        page.append(this.microphoneButton, this.audioNotice, this.label('Hear domain audio', this.sound));
    }
    private buildGraphics(): void {
        const page = this.pages.get('Graphics')!, current = this.options.graphics();
        page.append(element('p', 'intro', 'Adjust how the world looks on your screen.'));
        for (const [field, title, minimum, maximum, step] of [
            ['fieldOfView', 'Field of view', 20, 130, 1], ['resolutionPercent', 'Resolution %', 10, 200, 10],
        ] as const) {
            const slider = element('input'); slider.type = 'range'; slider.min = String(minimum); slider.max = String(maximum); slider.step = String(step); slider.value = String(current[field]);
            const value = element('output', '', slider.value);
            this.listen(slider, 'change', () => this.attempt(() => {
                this.options.applyGraphics({ ...this.options.graphics(), [field]: Number(slider.value) }); value.value = slider.value;
                this.options.onStatus('Graphics setting applied.', 'info');
            }));
            const row = this.label(title, slider); row.append(value); page.append(row);
        }
        for (const [field, title] of [['localLights', 'Local lights'], ['cameraClipping', 'Keep the camera outside walls']] as const) {
            const input = element('input'); input.type = 'checkbox'; input.checked = current[field];
            this.listen(input, 'change', () => this.attempt(() => { this.options.applyGraphics({ ...this.options.graphics(), [field]: input.checked }); }));
            page.append(this.label(title, input));
        }
    }
    private buildSnapshot(): void {
        const page = this.pages.get('Snapshot')!;
        page.append(element('p', 'intro', 'Save a picture of the world from your current view.'));
        const capture = element('button', 'primary', 'Save snapshot'); capture.type = 'button';
        this.listen(capture, 'click', () => this.run(async () => {
            const blob = await this.options.snapshot();
            if (this.disposed) return;
            const url = URL.createObjectURL(blob); this.downloadURLs.add(url);
            const link = element('a'); link.href = url; link.download = `overte-${new Date().toISOString().replace(/[:.]/g, '-')}.png`;
            document.body.append(link); link.click(); link.remove();
            setTimeout(() => { URL.revokeObjectURL(url); this.downloadURLs.delete(url); }, 1000);
            this.options.onStatus('Snapshot saved.', 'info');
        })); page.append(capture);
    }

    open(name: AppName): void {
        this.current = name;
        for (const [key, page] of this.pages) page.hidden = key !== name;
        for (const [key, tab] of this.tabs) { tab.classList.toggle('active', key === name); tab.setAttribute('aria-pressed', String(key === name)); }
    }
    show(visible: boolean): void {
        if (this.disposed) return;
        this.shown = visible; this.container.hidden = !visible; this.options.visible(visible);
    }
    toggle(): void { this.show(!this.shown); }
    get visible(): boolean { return this.shown; }
    get activeApp(): AppName { return this.current; }
    get selectedEntityID(): string | undefined { return this.selectedID; }
    setConnection(state: ConnectionState, message = ''): void {
        this.connected = state === 'connected';
        this.state.textContent = message || state[0].toUpperCase() + state.slice(1);
        this.join.disabled = state === 'connecting';
        this.leaveButton.disabled = state === 'disconnected';
        this.reconnectButton.disabled = state === 'connecting' || !this.domain.value;
        this.microphoneButton.disabled = !this.connected;
        if (state === 'disconnected' || state === 'error') { this.selectedID = undefined; this.selection.textContent = 'Aim at a world object and press E to inspect it.'; }
    }
    setMicrophone(muted: boolean): void {
        this.muted = muted;
        this.microphoneButton.textContent = muted ? 'Enable microphone' : 'Mute microphone';
        this.microphoneButton.setAttribute('aria-pressed', String(!muted));
        this.audioNotice.textContent = muted ? 'Microphone is off.' : 'Microphone is on. People in this domain can hear you.';
    }
    setPeople(avatars: readonly Avatar[], selfId = ''): void {
        const rows = avatars.map(avatar => element('li', 'person', `${avatar.displayName || 'Participant'}${avatar.id === selfId ? ' · You' : ''}`));
        if (!rows.length) rows.push(element('li', 'muted-text', this.connected ? 'No other participants yet.' : 'Join a domain to see its people.'));
        this.people.replaceChildren(...rows);
    }
    setPermissions(permissions: SessionPermissions): void {
        this.container.dataset.canEdit = String(permissions.edit);
    }
    selectEntity(entity: Entity): void {
        this.selectedID = entity.id;
        this.selection.textContent = `${entity.name || entity.type} · ${entity.type}${entity.description ? ` — ${String(entity.description).slice(0, 300)}` : ''}`;
        this.open('Domain'); this.show(true);
    }
    dispose(): void {
        if (this.disposed) return;
        this.disposed = true; this.abort.abort();
        for (const url of this.downloadURLs) URL.revokeObjectURL(url);
        this.downloadURLs.clear(); this.container.replaceChildren();
    }
}
