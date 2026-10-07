// Modified for Overte direct browser compatibility; see docs/browser-direct-client/SDK_PORT.md.
//
//  ReceivedMessage.ts
//
//  Created by David Rowe on 10 Jun 2021.
//  Copyright 2021 Vircadia contributors.
//  Copyright 2021 DigiSomni LLC.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import MessageData from "./MessageData";
import NLPacket from "./NLPacket";
import SockAddr from "./SockAddr";
import Packet from "./udt/Packet";
import { PacketTypeValue } from "./udt/PacketHeaders";
import assert from "../shared/assert";
import { MessageAssembler } from "../../../message-assembler";


/*@devdoc
 *  The <code>ReceivedMessage</code> class provides information on a Vircadia protocol message received via one or more Vircadia
 *  protocol packets.
 *  <p>The likes of C++'s <code>readPrimitive()</code> and <code>readString()</code> are not implemented because it's better to
 *  in-line such methods in the packet readers/writers for packet handling speed.</p>
 *  <p>C++: <code>ReceivedMessage : public QObject </code>
 *  @class ReceivedMessage
 *  @param {NLPacket} packet - The first (and possibly only) packet that forms the message.
 */
class ReceivedMessage {
    // C++  ReceivedMessage : public QObject

    #_messageData;
    #_assembler = new MessageAssembler();
    #_assembled: Uint8Array | null = null;


    constructor(packet: NLPacket) {
        // C++  ReceivedMessage(NLPacket& packet)
        this.#_messageData = packet.getMessageData();  // Reference the data already collected; no need to copy it.
        this.#_messageData.packetType = this.#_messageData.type;
        this.#_messageData.numPackets = 1;
        this.#_messageData.isComplete = this.#_messageData.packetPosition === Packet.PacketPosition.ONLY;
        this.#_messageData.firstPacketReceiveTime = this.#_messageData.receiveTime;

        const start = this.#_messageData.dataPosition;
        const data = this.#_messageData.data;
        this.#_assembler.append(new Uint8Array(data.buffer, data.byteOffset + start,
            this.#_messageData.packetSize - start));

    }


    /*@devdoc
     *  Gets a reference to the {@link MessageData} object used to accumulate and share private packet- and message-related data
     *  between the {@link BasePacket}, {@link Packet}, and {@link NLPacket} classes and the "friend" {@link ReceivedMessage}
     *  class plus the packet writing and reading classes provided in {@link Packets}.
     *  <p><strong>Warning:</strong> Do not use except in these friend classes.</p>
     *  @returns {MessageData} Private packet- and message-related data.
     */
    getMessageData(): MessageData {
        // C++  N/A
        return this.#_messageData;
    }

    /*@devdoc
     *  Gets the type of the message.
     *  @returns {PacketType} The type of the packet(s) used to form the message.
     */
    getType(): PacketTypeValue {
        // C++  PacketType getType()
        return this.#_messageData.packetType;
    }

    /*@devdoc
     *  Gets the sender's address.
     *  @returns {SockAddr} The sender's address if known, a null SockAddr if not known.
     */
    getSenderSockAddr(): SockAddr {
        // C++  SockAddr getSenderSockAddr()
        return this.#_messageData.senderSockAddr ? this.#_messageData.senderSockAddr : new SockAddr();
    }

    /*@devdoc
     *  Gets the local ID of the node that is the source of the message.
     *  @returns {number} The ID of the node that is the source of the packet if known (i.e., it is a sourced message),
     *      {@link Node|Node.NULL_LOCAL_ID} if not known.
     */
    getSourceID(): number {
        // C++  NLPacket::LocalID getSourceID()
        return this.#_messageData.sourceID;
    }

    /*@devdoc
     *  Appends the data from a packet to existing message data.
     *  @param {NLPacket} packet - The packet to append.
     */
    appendPacket(packet: NLPacket): void {
        // C++  void appendPacket(NLPacket& packet)
        assert(!this.#_messageData.isComplete, "ReceivedMessage.appendPacket() : Appending packet to a complete message");

        this.#_messageData.numPackets += 1;

        // Append the packet payload.
        const packetMessageData = packet.getMessageData();
        const packetPayloadStart = NLPacket.totalNLHeaderSize(packet.getType(), true);
        const data = packetMessageData.data;
        this.#_assembler.append(new Uint8Array(data.buffer, data.byteOffset + packetPayloadStart,
            packetMessageData.packetSize - packetPayloadStart));
        if (packet.getPacketPosition() === NLPacket.PacketPosition.LAST) {
            this.#_messageData.isComplete = true;
        }

    }

    /*@devdoc
     *  Records and notifies that receipt of the received message has failed.
     */
    setFailed(): void {
    // C++  void setFailed()

        // WEBRTC TODO: Address further C++ code. - Failure state for asset server API.

        this.#_messageData.isComplete = true;

        // WEBRTC TODO: Address further C++ code. - Completed signal state for asset server API.

    }

    /*@devdoc
     *  Gets the raw message data, excluding the Packet and NLPacket protocol headers.
     *  @returns {DataView} The raw message data.
     */
    getMessage(): DataView {
        // C++  QByteArray getMessage()
        if (!this.#_messageData.isComplete) {
            throw new Error("A native message was read before reliable delivery completed.");
        }
        this.#_assembled ??= this.#_assembler.finish();
        return new DataView(this.#_assembled.buffer, this.#_assembled.byteOffset, this.#_assembled.byteLength);
    }

}

export default ReceivedMessage;
