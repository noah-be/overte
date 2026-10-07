// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { fileURLToPath } from 'node:url';

const run = promisify(execFile);
test('managed datagram framing handles fragmented records and refuses forged endpoints, ports and malformed lengths', async () => {
    const script = `
import socket,sys
sys.path.insert(0,${JSON.stringify(fileURLToPath(new URL('.', import.meta.url)))})
from network_udp import DatagramRelay,HEADER,scope
for value in [{'address':'192.168.1.1','ports':[45102]}, {'address':'127.0.0.2','ports':[True]}, {'address':'127.0.0.2','ports':[0]}]:
    try:scope(value);raise AssertionError('Invalid operator scope accepted')
    except ValueError:pass
server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.2',0));server.settimeout(.1)
port=server.getsockname()[1]
left,right=socket.socketpair();relay=DatagramRelay(left,'127.0.0.2',frozenset([port]));right.settimeout(1)
try:
    packet=HEADER.pack(1,port,33001,5)+b'world'
    right.sendall(packet[:3]);assert relay.step()
    try:server.recvfrom(1024);raise AssertionError('Truncated header reached domain')
    except socket.timeout:pass
    right.sendall(packet[3:]);assert relay.step()
    data,peer=server.recvfrom(1024);assert data==b'world'
    server.sendto(b'authenticated-reply',peer);assert relay.step();assert relay.step()
    response=right.recv(1024);assert response==HEADER.pack(1,port,33001,19)+b'authenticated-reply'
    for address,foreign_port in [('127.0.0.2',0),('127.0.0.3',port)]:
        foreign=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);foreign.bind((address,foreign_port))
        try:
            foreign.sendto(b'forged-reply',peer);assert relay.step();right.settimeout(.1)
            try:right.recv(1024);raise AssertionError('Foreign UDP source reached native session')
            except socket.timeout:pass
        finally:foreign.close()
    for endpoint,target in [(2,port),(1,port+1 if port<65535 else port-1)]:
        right.sendall(HEADER.pack(endpoint,target,33001,6)+b'forged');assert relay.step()
        try:server.recvfrom(1024);raise AssertionError('Forged scope reached domain')
        except socket.timeout:pass
    assert len(relay.sockets)==1
    right.sendall(HEADER.pack(1,port,33001,0));assert not relay.step()
finally:relay.close();right.close();server.close()
print('Bounded managed datagram records and exact scope passed')
`;
    const result = await run('/usr/bin/python3', ['-c', script], { timeout: 5000, maxBuffer: 4096 });
    assert.match(result.stdout, /exact scope passed/);
});

test('managed real wildcard-bound domain replies retain the pinned native endpoint', async () => {
    const script = `
import socket,sys
sys.path.insert(0,${JSON.stringify(fileURLToPath(new URL('.', import.meta.url)))})
from network_udp import DatagramRelay,HEADER
server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('0.0.0.0',0));server.settimeout(1)
port=server.getsockname()[1];left,right=socket.socketpair();right.settimeout(.3)
relay=DatagramRelay(left,'127.0.0.2',frozenset([port]))
try:
    right.sendall(HEADER.pack(1,port,33002,5)+b'guest');assert relay.step()
    data,peer=server.recvfrom(1024);assert data==b'guest'
    server.sendto(b'domain-reply',peer)
    assert relay.step();assert relay.step()
    result=right.recv(1024)
    assert result==HEADER.pack(1,port,33002,12)+b'domain-reply'
finally:relay.close();right.close();server.close()
print('Actual wildcard-bound domain reply passed')
`;
    const result = await run('/usr/bin/python3', ['-c', script], { timeout: 5000, maxBuffer: 4096 });
    assert.match(result.stdout, /wildcard-bound domain reply passed/);
});
