// Modified for Overte direct browser compatibility; see docs/browser-direct-client/SDK_PORT.md.
//
//  DomainServerAddedNode.ts
//
//  Created by David Rowe on 19 Aug 2022.
//  Copyright 2021 Vircadia contributors.
//  Copyright 2021 DigiSomni LLC.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import assert from "../../shared/assert";
import { NewNodeInfo } from "../LimitedNodeList";
import { readNativeNodeRecord } from "../../../../native-node-record";

import "../../shared/DataViewExtensions";


type DomainServerAddedNodeDetails = NewNodeInfo;


const DomainServerAddedNode = new class {
    // C++  N/A

    /*@devdoc
     *  Information returned by {@link PacketScribe|reading} a {@link PacketType(1)|DomainServerAddedNode} packet.
     *  @typedef {LimitedNodeList.NewNodeInfo} PacketScribe.DomainServerAddedNodeDetails
     */

    /*@devdoc
     *  Reads a {@link PacketType(1)|DomainServerAddedNode} packet.
     *  @function PacketScribe.DomainServerAddedNode&period;read
     *  @param {DataView} data - The {@link Packets|DomainServerAddedNode} message data to read.
     *  @returns {PacketScribe.DomainServerAddedNodeDetails} Information on the assignment client node added.
     */
    read(data: DataView): DomainServerAddedNodeDetails {  /* eslint-disable-line class-methods-use-this */
        // C++  void NodeList::processDomainServerAddedNode(QSharedPointer<ReceivedMessage> message)
        // C++  void NodeList::parseNodeFromPacketStream(QDataStream& packetStream)


        /* eslint-disable @typescript-eslint/no-magic-numbers */

        const record = readNativeNodeRecord(data, 0);

        /* eslint-enable @typescript-eslint/no-magic-numbers */

        assert(record.next === data.byteLength, "ERROR: Length mismatch reading DomainServerAddedNode message!");

        return record.node;
    }

}();

export default DomainServerAddedNode;
export type { DomainServerAddedNodeDetails };
