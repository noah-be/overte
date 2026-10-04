// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {x11ProbeDiagnostic} from './x11-probe-diagnostics.mjs';
function reply(text,status=0){const body=Buffer.from(text);const head=Buffer.alloc(8);head[0]=status;head[1]=body.length;return Buffer.concat([head,body]);}
test('observed X11 setup failure exports a fixed reason without private bytes',()=>{
 assert.deepEqual(x11ProbeDiagnostic('setup',reply('Invalid MIT-MAGIC-COOKIE-1 key')), {kind:'setup',status:'refused',reason:'invalid-cookie',reasonBytes:30,incomplete:false});
 const unknown=x11ProbeDiagnostic('setup',reply('synthetic-private-cookie-and-host'));
 assert.equal(unknown.reason,'unrecognized');assert.ok(!JSON.stringify(unknown).includes('synthetic'));
 assert.deepEqual(x11ProbeDiagnostic('setup',Buffer.from([1])),{kind:'setup',status:'accepted'});
 const actualInline=vm.runInNewContext('('+x11ProbeDiagnostic.toString()+')',{Buffer,Map});
 assert.equal(actualInline('setup',reply('Invalid MIT-MAGIC-COOKIE-1 key')).reason,'invalid-cookie');
 assert.equal(actualInline('socket-error',{code:'EACCES'}).errno,'EACCES');
 assert.equal(x11ProbeDiagnostic('setup',reply('No protocol specified',2)).status,'authenticate');
 assert.equal(x11ProbeDiagnostic('setup',Buffer.from([0,255])).incomplete,true);
 assert.equal(x11ProbeDiagnostic('setup',Buffer.from([9])).status,'invalid');
});
test('X11 socket errors and original timeout export only fixed enums',()=>{
 for(const code of ['EACCES','EPERM','ENOENT','ECONNREFUSED','ECONNRESET','EPIPE']) assert.equal(x11ProbeDiagnostic('socket-error',{code,message:'private'}).errno,code);
 assert.deepEqual(x11ProbeDiagnostic('socket-error',{code:'private-secret'}),{kind:'socket-error',errno:'other-error'});
 assert.deepEqual(x11ProbeDiagnostic('timeout'),{kind:'timeout'});
 assert.deepEqual(x11ProbeDiagnostic('setup',null),{kind:'invalid-observation'});
});
