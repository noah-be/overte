// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export interface VisitorBookmark { name:string; address:string }
export interface VisitorPreferences { bookmarks:VisitorBookmark[]; home?:string }
export function viewpointPath(path:string):string;
export function visitorAddress(value:unknown):string;
export function validateVisitorPreferences(value?:unknown):VisitorPreferences;
