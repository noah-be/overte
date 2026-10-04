// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import * as T from 'three';

export const drawRevisionRefusals = ['revision-admission-or-unsettled','revision-scene-identity',
  'revision-owner-map-size','revision-entity-map-size','revision-root-identity','revision-root-status',
  'revision-root-signature','revision-entity-record','revision-scene-transform'] as const;
export type DrawRevisionRefusal = typeof drawRevisionRefusals[number];
export function checkedDrawRevisionRefusal(value:unknown):DrawRevisionRefusal|undefined {
  return typeof value==='string'&&(drawRevisionRefusals as readonly string[]).includes(value)?value as DrawRevisionRefusal:undefined;
}
const lights=[T.Light,T.AmbientLight,T.DirectionalLight,T.HemisphereLight,T.PointLight,T.SpotLight,T.RectAreaLight].map(value=>value.prototype);
const cameras=[T.Camera,T.PerspectiveCamera,T.OrthographicCamera].map(value=>value.prototype);
/** Diagnostic only: exact prototypes give fixed classes, never labels, model
 * values, getters, constructor names or class-based admission exceptions. */
export function unsupportedDrawNodeReason(node:object,phase:'node'|'transform',failure:unknown):string {
  if(failure==='unsupported-accessor')return phase==='node'?'unsupported-node-own-accessor':'unsupported-node-transform-accessor';
  if(failure==='unsupported-object-field-bound')return phase==='node'?'unsupported-node-field-bound':'unsupported-node-transform-field-bound';
  if(failure!=='unsupported-object-prototype')return 'unsupported-node-unclassified';
  if(phase==='transform')return 'unsupported-node-transform-prototype';
  try {
    const prototype=Object.getPrototypeOf(node);
    if(lights.includes(prototype))return 'unsupported-node-known-light-prototype';
    if(cameras.includes(prototype))return 'unsupported-node-known-camera-prototype';
    if(prototype===T.Sprite.prototype)return 'unsupported-node-known-sprite-prototype';
  } catch { /* A foreign object cannot publish its private failure detail. */ }
  return 'unsupported-node-other-prototype';
}
