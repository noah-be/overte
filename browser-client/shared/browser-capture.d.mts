// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
export type CaptureField='echoCancellation'|'noiseSuppression'|'autoGainControl'|'inputGainPercent';
export type CaptureChange={field:'inputGainPercent';value:number}|{field:'echoCancellation'|'noiseSuppression'|'autoGainControl';value:boolean};
export interface CaptureState{version:1;active:boolean;controls:Record<CaptureField,boolean>;settings:{echoCancellation:boolean|null;noiseSuppression:boolean|null;autoGainControl:boolean|null;inputGainPercent:number|null;inputGain:number|null}}
export type CaptureRequest={schemaVersion:1;requestId:number;operation:'request'|'cancel'}|({schemaVersion:1;requestId:number;operation:'change'}&CaptureChange);
export type CaptureReason='ok'|'inactive'|'unsupported'|'busy'|'apply-refused'|'readback-mismatch'|'rollback-refused'|'deadline'|'cancelled';
export interface CaptureResult{schemaVersion:1;requestId:number;accepted:boolean;reason:CaptureReason;state:CaptureState}
export const CAPTURE_FIELDS:readonly CaptureField[];
export const CAPTURE_REASONS:readonly CaptureReason[];
export function captureChange(field:unknown,value:unknown):CaptureChange;
export function captureState(value:unknown):CaptureState;
export function captureRequest(value:unknown):CaptureRequest;
export function captureResult(value:unknown):CaptureResult;
export function inactiveCapture():CaptureState;
