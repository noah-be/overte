// Modified for Overte direct browser compatibility; see docs/browser-direct-client/SDK_PORT.md.
//
//  SetAvatarTraits.ts
//
//  Created by Julien Merzoug on 6 Apr 2022.
//  Copyright 2022 Vircadia contributors.
//  Copyright 2022 DigiSomni LLC.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

import AvatarTraits, { SkeletonJoint } from "../../avatars/AvatarTraits";
import { ClientTraitStatus } from "../../avatars/ClientTraitsHandler";
import GLMHelpers from "../../shared/GLMHelpers";
import Vec3 from "../../shared/Vec3";
import PacketTypeValue from "../udt/PacketHeaders";
import NLPacketList from "../NLPacketList";
import assert from "../../shared/assert";


type SetAvatarTraitsDetails = {
    currentTraitVersion: number;
    skeletonModelURL: string;
    skeletonData: SkeletonJoint[];
    traitStatuses: Array<ClientTraitStatus>;
    initialSend: boolean;
};


const SetAvatarTraits = new class {
    // C++ N/A

    /*@devdoc
     *  Information needed for {@link PacketScribe|writing} a {@link PacketType(1)|SetAvatarTraits} packet list.
     *  @typedef {object} PacketScribe.SetAvatarTraitsDetails
     *  @property {number} currentTraitVersion - Trait sending sequence number. This should be incremented for each
     *      <code>SetAvatarTraits</code> packet written.
     *  @property {string} skeletonModelURL - The URL of the avatar's FST, glTF, or FBX model file.
     *  @property {SkeletonJoint[]} skeletonData - The avatar's skeleton.
     *  @property {ClientTraitStatus[]} traitStatuses - The status of each avatar trait.
     *  @property {boolean} initialSend - <code>true</code> to send all traits, <code>false</code> to send only those that have
     *      been updated.
     */


    /*@devdoc
     *  Writes a {@link PacketType(1)|SetAvatarTraits} packet list, ready for sending.
     *  @function PacketScribe.SetAvatarTraits&period;write
     *  @param {PacketScribe.SetAvatarTraitsDetails} info - The information needed for writing the packet list.
     *  @returns {NLPacketList} The packet list, ready for sending.
     */
    write(info: SetAvatarTraitsDetails): NLPacketList {  /* eslint-disable-line class-methods-use-this */
        // C++  ClientTraitsHandler::sendChangedTraitsToMixer()
        //      qint64 AvatarTraits::packTrait(TraitType traitType, ExtendedIODevice& destination, const AvatarData& avatar)
        //      QByteArray AvatarData::packTrait(AvatarTraits::TraitType traitType)

        const packetList = NLPacketList.create(PacketTypeValue.SetAvatarTraits, null, true, true);

        packetList.writePrimitive(info.currentTraitVersion, 4);  // eslint-disable-line @typescript-eslint/no-magic-numbers

        for (const [index, traitStatus] of info.traitStatuses.entries()) {
            if (info.initialSend || traitStatus === ClientTraitStatus.Updated) {
                const traitType = index;
                if (traitType === AvatarTraits.SkeletonModelURL) {
                    this.#packSkeletonModelURL(info.skeletonModelURL, packetList);
                } else if (traitType === AvatarTraits.SkeletonData) {
                    this.#packSkeletonData(info.skeletonData, packetList);
                }
            }
        }

        return packetList;
    }


    // eslint-disable-next-line class-methods-use-this
    #packSkeletonModelURL(skeletonModelURL: string, packetList: NLPacketList) {
        // C++  QByteArray AvatarData::packSkeletonModelURL()
        const textEncoder = new TextEncoder();

        packetList.writePrimitive(AvatarTraits.SkeletonModelURL, 1);
        const encodedURL = textEncoder.encode(skeletonModelURL);
        if (encodedURL.byteLength > 32767) throw new RangeError("Native avatar trait exceeds its int16 wire size");
        packetList.writePrimitive(encodedURL.length, 2);
        packetList.write(encodedURL);
    }

    // eslint-disable-next-line class-methods-use-this
    #packSkeletonData(skeletonData: SkeletonJoint[], packetList: NLPacketList) {
        // C++  QByteArray AvatarData::packSkeletonData()
        const TRANSLATION_COMPRESSION_RADIX = 14;

        // Calculate header.
        let maxScaleDimension = 0.0;
        let maxTranslationDimension = 0.0;
        const numJoints = Math.min(skeletonData.length, 255);
        let stringTableLength = 0;
        const defaultScales: number[] = [];
        const translations: Array<{ x: number, y: number, z: number }> = [];
        const encodedNames: Uint8Array[] = [];
        const textEncoder = new TextEncoder();
        for (let i = 0; i < numJoints; i++) {
            const skeletonJoint = skeletonData[i];
            assert(skeletonJoint !== undefined);
            let encodedName = textEncoder.encode(skeletonJoint.jointName);
            if (encodedName.byteLength > 255 || encodedName.byteLength > 65535 - stringTableLength) {
                encodedName = new Uint8Array();
            }
            encodedNames.push(encodedName);
            stringTableLength += encodedName.byteLength;
            const source = skeletonJoint.defaultTranslation;
            const translation = [source.x, source.y, source.z].every(Number.isFinite) ? source : Vec3.ZERO;
            translations.push(translation);
            maxTranslationDimension = Math.max(maxTranslationDimension,
                Math.abs(translation.x), Math.abs(translation.y), Math.abs(translation.z));
            const scale = Number.isFinite(skeletonJoint.defaultScale) && skeletonJoint.defaultScale > 0
                ? skeletonJoint.defaultScale : 1;
            maxScaleDimension = Math.max(maxScaleDimension, scale);
            defaultScales.push(scale);
        }
        if (maxTranslationDimension <= 0) maxTranslationDimension = 1;
        if (maxScaleDimension <= 0) maxScaleDimension = 1;

        // Write trait info.
        const HEADER_DATA_SIZE = 11;
        const JOINT_DATA_SIZE = 22;
        const traitSize = HEADER_DATA_SIZE + numJoints * JOINT_DATA_SIZE + stringTableLength;
        if (traitSize > 32767) throw new RangeError("Native avatar trait exceeds its int16 wire size");
        packetList.writePrimitive(AvatarTraits.SkeletonData, 1);
        packetList.writePrimitive(traitSize, 2);

        // Write header.
        packetList.writeFloat(maxTranslationDimension);
        packetList.writeFloat(maxScaleDimension);
        packetList.writePrimitive(numJoints, 1);
        packetList.writePrimitive(stringTableLength, 2);

        // Write joint data.
        let stringStart = 0;
        const twoByteArray = new Uint8Array(2);
        const twoByteDataView = new DataView(twoByteArray.buffer);
        const sixByteArray = new Uint8Array(6);  // eslint-disable-line @typescript-eslint/no-magic-numbers
        const sixByteDataView = new DataView(sixByteArray.buffer);
        const invMaxTranslationDimension = 1.0 / maxTranslationDimension;
        for (let i = 0; i < numJoints; i++) {
            const skeletonJoint = skeletonData[i]!;  // eslint-disable-line @typescript-eslint/no-non-null-assertion
            const encodedName = encodedNames[i]!;
            packetList.writePrimitive(stringStart, 2);
            packetList.writePrimitive(encodedName.byteLength, 1);
            stringStart += encodedName.byteLength;
            packetList.writePrimitive(skeletonJoint.boneType, 1);
            GLMHelpers.packFloatVec3ToSignedTwoByteFixed(sixByteDataView, 0,
                Vec3.multiply(invMaxTranslationDimension, translations[i]!), TRANSLATION_COMPRESSION_RADIX);
            packetList.write(sixByteArray);
            GLMHelpers.packOrientationQuatToSixBytes(sixByteDataView, 0, skeletonJoint.defaultRotation);
            packetList.write(sixByteArray);
            GLMHelpers.packFloatRatioToTwoByte(twoByteDataView, 0, defaultScales[i]! / maxScaleDimension);
            packetList.write(twoByteArray);
            packetList.writePrimitive(i, 2);
            packetList.writePrimitive(skeletonJoint.parentIndex, 2);
        }

        // Write string table.
        for (const encodedName of encodedNames) packetList.write(encodedName);
    }

}();

export default SetAvatarTraits;
export type { SetAvatarTraitsDetails };
