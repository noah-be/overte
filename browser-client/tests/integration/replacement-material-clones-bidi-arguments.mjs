// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
// Exact registered VM arguments projected into the driver's plain-object realm.
import {types} from 'node:util';
import {cloneVariants} from './replacement-material-clones-registration.mjs';

export function cloneBidiArguments(args){
 if(types.isProxy(args)||!Array.isArray(args)||args.length!==2||typeof args[0]!=='function')throw Error('Clone evaluation signature refused');
 const value=args[1];
 if(!value||typeof value!=='object'||types.isProxy(value)||Array.isArray(value))throw Error('Clone evaluation data refused');
 const fields=Object.getOwnPropertyDescriptors(value),keys=Reflect.ownKeys(fields);
 if(keys.length!==2||!keys.includes('enabled')||!keys.includes('variant')||!('value'in fields.enabled)||!('value'in fields.variant)
  ||typeof fields.enabled.value!=='boolean'||!cloneVariants.includes(fields.variant.value))throw Error('Clone evaluation schema refused');
 return [args[0],{enabled:fields.enabled.value,variant:fields.variant.value}];
}
