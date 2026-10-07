// SPDX-License-Identifier: Apache-2.0
import {visitorAddress} from '../shared/visitor-preferences.mjs';
import type {Pose} from './world-data';
export interface NavigationAttempt { readonly domain:string; readonly serial:number; readonly index?:number }

/** Visitor-local history. Admission failures never change the committed cursor. */
export class NavigationHistory {
    private entries:string[] = [];
    private cursor = -1;
    private serial = 0;
    private pending?:NavigationAttempt;

    get state() { return {canGoBack:this.cursor > 0, canGoForward:this.cursor >= 0 && this.cursor < this.entries.length - 1}; }
    /** Native AddressManager stores the actual viewpoint when leaving a place. */
    rememberDeparture(pose:Pick<Pose,'position'|'orientation'>):boolean {
        if (this.cursor < 0) return false;
        const {position,orientation} = pose;
        if (![position.x,position.y,position.z,orientation.x,orientation.y,orientation.z,orientation.w].every(Number.isFinite)) return false;
        try {
            const address = new URL(visitorAddress(this.entries[this.cursor]));
            address.pathname = `/${position.x},${position.y},${position.z}/${orientation.x},${orientation.y},${orientation.z},${orientation.w}`;
            this.entries[this.cursor] = visitorAddress(address.href);
            return true;
        } catch { return false; }
    }
    begin(domain:string):NavigationAttempt {
        return this.pending = {domain, serial:++this.serial};
    }
    traverse(direction:'back'|'forward'):NavigationAttempt | undefined {
        const index = this.cursor + (direction === 'back' ? -1 : 1);
        if (index < 0 || index >= this.entries.length) return;
        return this.pending = {domain:this.entries[index], serial:++this.serial, index};
    }
    commit(attempt:NavigationAttempt):boolean {
        if (this.pending !== attempt) return false;
        this.pending = undefined;
        if (attempt.index !== undefined) this.cursor = attempt.index;
        else if (this.entries[this.cursor] !== attempt.domain) {
            this.entries.splice(this.cursor + 1);
            this.entries.push(attempt.domain);
            if (this.entries.length > 50) this.entries.shift();
            this.cursor = this.entries.length - 1;
        }
        return true;
    }
    cancel():void { this.pending = undefined; }
}
