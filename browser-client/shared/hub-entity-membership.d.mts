// SPDX-License-Identifier: Apache-2.0
export type HubMembershipResult={schema:1;status:'complete';entityRows:[string,string][];slotRows:[string,string,boolean,boolean,boolean,boolean][]}|{schema:1;status:'refused';reason:string};
export function projectWorldEntityMembership(entities:Map<string,{type:string}>,objects:Map<string,{userData:Record<string,unknown>}>):HubMembershipResult;
export function collectHubEntityMembership():unknown;
