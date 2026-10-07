// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0
import type { NewNodeInfo } from './vircadia/domain/networking/LimitedNodeList';
import NodePermissions from './vircadia/domain/networking/NodePermissions';
import type { NodeTypeValue } from './vircadia/domain/networking/NodeType';
import SockAddr from './vircadia/domain/networking/SockAddr';
import { SocketTypeValue } from './vircadia/domain/networking/SocketType';
import Uuid from './vircadia/domain/shared/Uuid';
import './vircadia/domain/shared/DataViewExtensions';

/** Node.cpp writes SocketType separately from SockAddr's QHostAddress+port.
 * Qt writes one signed protocol byte, and no address bytes for Unknown/Any.
 * The standard native STUN fallback therefore has a four-byte socket record.
 * IPv6 node addresses need a wider SDK address representation; reject clearly.
 */
export function readNativeNodeRecord(data: DataView, start: number): { node: NewNodeInfo; next: number } {
    let position = start;
    const requireBytes = (size: number) => {
        if (!Number.isSafeInteger(position) || position < 0 || position + size > data.byteLength) {
            throw new Error('The domain sent a truncated native node record.');
        }
    };
    const u8 = () => { requireBytes(1); return data.getUint8(position++); };
    const u16 = () => { requireBytes(2); const value = data.getUint16(position, false); position += 2; return value; };
    const u32 = () => { requireBytes(4); const value = data.getUint32(position, false); position += 4; return value; };
    const uuid = () => { requireBytes(16); const value = new Uuid(data.getBigUint128(position, false)); position += 16; return value; };
    const socket = () => {
        const type = u8();
        if (type > SocketTypeValue.WebRTC) throw new Error('The domain sent an unsupported native socket type.');
        requireBytes(1); const protocol = data.getInt8(position++);
        let address = 0;
        if (protocol === 0) address = u32();
        else if (protocol === 1) throw new Error('IPv6 node addresses are not supported by this browser client yet.');
        else if (protocol !== -1 && protocol !== 2) throw new Error('The domain sent an unsupported native address protocol.');
        return new SockAddr(type, address, u16());
    };

    const type = String.fromCharCode(u8()) as NodeTypeValue;
    const id = uuid(), publicSocket = socket(), localSocket = socket();
    const permissions = new NodePermissions(); permissions.permissions = u32();
    const isReplicated = u8() !== 0, sessionLocalID = u16(), connectionSecretUUID = uuid();
    return { node: { type, uuid: id, publicSocket, localSocket, permissions, isReplicated, sessionLocalID, connectionSecretUUID }, next: position };
}
