// SPDX-License-Identifier: Apache-2.0
import {validateVisitorPreferences,type VisitorPreferences} from '../shared/visitor-preferences.mjs';
const KEY = 'overte.browser.visitor-preferences.v1';
const RECOVERY = `${KEY}.recovery`;

/** Only visitor Places data crosses domains; account/configuration files never do. */
export class VisitorPreferenceStore {
    private value:VisitorPreferences = {bookmarks:[]};
    private preserveInvalidPrimary = false;
    constructor(private storage:Pick<Storage,'getItem'|'setItem'>,private onStatus:(message:string)=>void) {
        let saved:string|null;
        try { saved = storage.getItem(KEY); }
        catch { onStatus('Browser storage is unavailable. Bookmarks will remain available during this visit.'); return; }
        if (!saved) return;
        try {
            if (saved.length > 192 * 1024 || new TextEncoder().encode(saved).length > 192 * 1024) throw Error('Stored preferences exceed the limit');
            this.value = validateVisitorPreferences(JSON.parse(saved));
        } catch {
            // Preserve an invalid existing record before a future valid user
            // change replaces it. Never copy other application/storage keys.
            try {
                if (saved.length > 192 * 1024 || new TextEncoder().encode(saved).length > 192 * 1024) this.preserveInvalidPrimary = true;
                else {
                    const previous = storage.getItem(RECOVERY);
                    if (previous === null) storage.setItem(RECOVERY,saved);
                    else if (previous !== saved) this.preserveInvalidPrimary = true;
                }
            }
            catch { this.preserveInvalidPrimary = true; }
            onStatus('Saved bookmarks could not be loaded. Their existing browser record has been preserved for recovery.');
        }
    }
    snapshot():VisitorPreferences { return validateVisitorPreferences(this.value); }
    update(value:VisitorPreferences):void {
        const next = validateVisitorPreferences(value);
        if (JSON.stringify(next) === JSON.stringify(this.value)) return;
        this.value = next;
        if (this.preserveInvalidPrimary) {
            this.onStatus('Bookmark changes work during this visit. The existing unreadable record cannot be backed up, so it has been preserved.');
            return;
        }
        try { this.storage.setItem(KEY,JSON.stringify(next)); }
        catch { this.onStatus('Bookmark changes work during this visit, but browser storage could not save them.'); }
    }
}
