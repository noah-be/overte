// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import {MAX_PERSONA_BYTES,validateVisitorPersona,type VisitorPersona} from '../shared/visitor-persona.mjs';
const KEY = 'overte.browser.visitor-persona.v1';
const RECOVERY = `${KEY}.recovery`;

/** Visitor-selected avatar data only; native accounts and settings are excluded. */
export class VisitorPersonaStore {
    private value:VisitorPersona = {};
    private preserveInvalidPrimary = false;
    constructor(private storage:Pick<Storage,'getItem'|'setItem'>,private onStatus:(message:string)=>void) {
        let saved:string|null;
        try {saved=storage.getItem(KEY);}
        catch {onStatus('Browser storage is unavailable. Avatar preferences will remain available during this visit.');return;}
        if (!saved) return;
        try {
            if (saved.length>MAX_PERSONA_BYTES || new TextEncoder().encode(saved).length>MAX_PERSONA_BYTES) throw Error('Stored avatar preferences exceed their limit');
            this.value=validateVisitorPersona(JSON.parse(saved));
        } catch {
            try {
                if (saved.length>MAX_PERSONA_BYTES || new TextEncoder().encode(saved).length>MAX_PERSONA_BYTES) this.preserveInvalidPrimary=true;
                else {
                    const recovery=storage.getItem(RECOVERY);
                    if (recovery===null) storage.setItem(RECOVERY,saved);
                    else if (recovery!==saved) this.preserveInvalidPrimary=true;
                }
            } catch {this.preserveInvalidPrimary=true;}
            onStatus('Saved avatar preferences could not be loaded. Their existing browser record has been preserved for recovery.');
        }
    }
    snapshot():VisitorPersona {return validateVisitorPersona(this.value);}
    update(patch:VisitorPersona):void {
        // Omitted favorites mean the native adapter could not export them;
        // preserve the prior supported collection. An explicit [] removes it.
        const clean=validateVisitorPersona(patch);
        let next:VisitorPersona;
        try {next=validateVisitorPersona({...this.value,...clean});}
        catch {
            this.onStatus('Combined avatar preferences exceed the 48 KiB limit. Existing saved choices were preserved; your world remains connected.');
            return;
        }
        if (JSON.stringify(next)===JSON.stringify(this.value)) return;
        this.value=next;
        if (this.preserveInvalidPrimary) {
            this.onStatus('Avatar changes work during this visit. The existing unreadable record cannot be backed up, so it has been preserved.');return;
        }
        try {this.storage.setItem(KEY,JSON.stringify(next));}
        catch {this.onStatus('Avatar changes work during this visit, but browser storage could not save them.');}
    }
}
