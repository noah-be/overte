// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import assert from 'node:assert/strict';
import {BrowserTablet} from '../src/tablet.js';
import {createPeopleFrameAcknowledgement} from './integration/tablet-people-audit.mjs';

function actualCommands(){
 const messages:Record<string,unknown>[]=[];
 const tablet=Object.create(BrowserTablet.prototype);
 Object.assign(tablet,{connected:true,disposed:false,revision:2,sequence:8,
  navigationSequence:8,generation:0,clearPointer(){},options:{send:(value:Record<string,unknown>)=>messages.push(value)}});
 const send=(value:Record<string,unknown>)=>(tablet as unknown as {send:(value:Record<string,unknown>)=>void}).send(value);
 return {send,messages};
}
const frame=(navigationSequence=9,revision=2)=>({type:'tablet',kind:'frame',sequence:4,revision,navigationSequence});

test('actual BrowserTablet navigation and displayed ACK bind the current frame without a nonexistent ACK navigation field',()=>{
 const {send,messages}=actualCommands(),observe=createPeopleFrameAcknowledgement();
 send({action:'open'});send({action:'frameAck',frameSequence:4,displayed:true});
 assert.equal(messages[0].sequence,9);assert.equal(messages[1].sequence,10);
 assert.equal(Object.hasOwn(messages[1],'navigationSequence'),false);
 assert.equal(observe(messages[0],[frame()]),null);const drawn=frame();
 assert.equal(observe(messages[1],[drawn]),drawn);
});

test('actual later navigation invalidates the earlier acknowledged generation and requires exact frame and revision',()=>{
 const {send,messages}=actualCommands(),observe=createPeopleFrameAcknowledgement();
 send({action:'open'});observe(messages.at(-1),[]);
 send({action:'home'});observe(messages.at(-1),[]);
 send({action:'frameAck',frameSequence:4,displayed:true});const ack=messages.at(-1)!;
 assert.equal(observe(ack,[frame(9)]),null);assert.equal(observe(ack,[frame(10,3)]),null);
 assert.equal(observe({...ack,frameSequence:5},[frame(10)]),null);
 const drawn=frame(10);assert.equal(observe(ack,[drawn]),drawn);
});

test('failed draw, unknown navigation, ambiguous capture and stale or contradictory acknowledgements refuse',()=>{
 const {send,messages}=actualCommands(),observe=createPeopleFrameAcknowledgement();
 send({action:'frameAck',frameSequence:4,displayed:true});assert.equal(observe(messages.at(-1),[frame()]),null);
 send({action:'open'});observe(messages.at(-1),[]);
 send({action:'frameAck',frameSequence:4,displayed:true});const ack=messages.at(-1)!,drawn=frame(10);
 for(const changed of [{displayed:false},{revision:0},{frameSequence:0},{sequence:10},{navigationSequence:9}])
  assert.equal(observe({...ack,...changed},[drawn]),null);
 assert.equal(observe(ack,[drawn,{...drawn}]),null);
 assert.equal(observe(ack,Array.from({length:17},()=>drawn)),null);
});
