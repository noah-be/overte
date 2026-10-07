// SPDX-License-Identifier: Apache-2.0
export interface AvatarWearable {properties:Record<string,unknown> & {type:'Model'}}
export interface AvatarFavorite {name:string;avatarURL:string;avatarScale:number;avatarIcon?:string;avatarEntities?:AvatarWearable[]}
export interface VisitorPersona {displayName?:string;avatarURL?:string;avatarScale?:number;avatarFavorites?:AvatarFavorite[]}
export const MAX_PERSONA_BYTES:number;
export const DEFAULT_AVATAR_URLS:Set<string>;
export const WEARABLE_FIELDS:string[];
export function personaAssetURL(value:unknown):string;
export function validatePersonaWearable(value:unknown):AvatarWearable;
export function validateVisitorPersona(value?:unknown):VisitorPersona;
