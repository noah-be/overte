#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Real temporary evidence bytes test packet fences, never a device outcome."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

spec = importlib.util.spec_from_file_location('packet', Path(__file__).with_name('packet.py'))
packet = importlib.util.module_from_spec(spec)
spec.loader.exec_module(packet)


class PacketTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.artifact = self.root / 'candidate.apk'
        self.artifact.write_bytes(b'explicit synthetic APK boundary')
        self.sample = self.root / 'evidence.bin'
        self.sample.write_bytes(b'explicit synthetic attachment boundary')
        self.source = 'a' * 40
        self.digest = packet.sha(self.artifact)
        self.record = packet.template(self.source, self.digest, '2026-10-13T18:00:00Z')
        self.record['environment'] = {'osVersion': 'synthetic', 'browserProviderVersion': 'synthetic',
            'buildConfiguration': 'host-test-only', 'referenceMp4Sha256': 'c' * 64}
        self.record['installationBinding'] = self.attachment('installation-binding')

    def attachment(self, kind):
        return {'path': self.sample.name, 'sha256': packet.sha(self.sample), 'kind': kind}

    def review(self, value=None):
        return packet.review(value or self.record, self.artifact, self.source, self.digest, self.root)

    def observe_all(self):
        for journey in packet.journeys():
            for step in journey['steps']:
                self.record['journeys'][journey['id']]['observations'][step['id']] = {
                    'status': 'observed', 'utc': '2026-10-13T18:01:00Z',
                    'note': 'Synthetic completeness test only, no physical device observation.',
                    'evidence': [self.attachment(kind) for kind in step['evidenceKinds']]}

    def test_blank_and_complete_packets_never_establish_device_acceptance(self):
        result = self.review()
        self.assertFalse(result['readyForHumanReview'])
        self.assertFalse(result['deviceAcceptance'])
        self.observe_all()
        result = self.review()
        self.assertTrue(result['readyForHumanReview'])
        self.assertFalse(result['deviceAcceptance'])

    def test_independent_identity_and_changed_actual_bytes_rejected(self):
        self.record['sourceRevisionApp'] = 'b' * 40
        with self.assertRaisesRegex(ValueError, 'expectations'): self.review()
        self.record['sourceRevisionApp'] = self.source
        self.artifact.write_bytes(b'changed actual candidate')
        with self.assertRaisesRegex(ValueError, 'candidate bytes'): self.review()

    def test_attachment_changes_and_symlink_escapes_rejected(self):
        self.sample.write_bytes(b'tampered evidence')
        with self.assertRaisesRegex(ValueError, 'evidence bytes'): self.review()
        outside = self.root.parent / (self.root.name + '-outside')
        outside.write_bytes(b'outside')
        self.addCleanup(outside.unlink)
        self.sample.unlink()
        self.sample.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'escape'): self.review()

    def test_path_traversal_and_parent_symlink_rejected(self):
        self.record['installationBinding']['path'] = '../outside'
        with self.assertRaisesRegex(ValueError, 'path escape'): self.review()
        sub = self.root / 'sub'
        sub.mkdir()
        (sub / 'binding').write_bytes(b'safe bytes')
        (self.root / 'alias').symlink_to(sub, target_is_directory=True)
        self.record['installationBinding'] = {'kind': 'installation-binding', 'path': 'alias/binding',
            'sha256': packet.sha(sub / 'binding')}
        with self.assertRaisesRegex(ValueError, 'symlinked'): self.review()

    def test_missing_journey_observation_or_audio_not_ready(self):
        self.observe_all()
        saved = copy.deepcopy(self.record)
        del self.record['journeys']['snapshot']
        with self.assertRaisesRegex(ValueError, 'journey coverage'): self.review()
        self.record = copy.deepcopy(saved)
        observations = self.record['journeys']['world-web']['observations']
        del observations[next(iter(observations))]
        with self.assertRaisesRegex(ValueError, 'observation coverage'): self.review()
        self.record = saved
        for record in self.record['journeys']['world-web']['observations'].values():
            record['evidence'] = [e for e in record['evidence'] if e['kind'] != 'audio-recording']
        with self.assertRaisesRegex(ValueError, 'evidence kind'): self.review()

    def test_fake_pass_extra_selector_and_missing_installed_binding_rejected(self):
        self.record['deviceAcceptance'] = True
        with self.assertRaisesRegex(ValueError, 'packet fields'): self.review()
        del self.record['deviceAcceptance']
        self.record['environment']['serial'] = 'synthetic-not-a-device'
        with self.assertRaisesRegex(ValueError, 'environment fields'): self.review()
        del self.record['environment']['serial']
        self.record['installationBinding'] = None
        with self.assertRaisesRegex(ValueError, 'installed-artifact'): self.review()

    def test_duplicates_empty_evidence_and_bad_utc_rejected(self):
        p = self.root / 'packet.json'
        p.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): packet.read(p)
        self.sample.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'empty'): self.review()
        self.sample.write_bytes(b'nonempty')
        self.record['installationBinding'] = self.attachment('installation-binding')
        self.record['utcStarted'] = '2026-10-13T18:00:00'
        with self.assertRaisesRegex(ValueError, 'UTC'): self.review()

    def test_original_companion_assets_have_real_geometry_and_two_color_image(self):
        fixtures = Path(__file__).parent / 'fixtures'
        model = fixtures / 'gltf-bundle'
        gltf = json.loads((model / 'main.gltf').read_text())
        data = (model / gltf['buffers'][0]['uri']).read_bytes()
        self.assertEqual(len(data), gltf['buffers'][0]['byteLength'])
        positions = struct.unpack('<9f', data[:36])
        self.assertEqual(positions, (-.5, 0, 0, .5, 0, 0, 0, 1, 0))
        for accessor in gltf['accessors']:
            view = gltf['bufferViews'][accessor['bufferView']]
            self.assertLessEqual(view['byteOffset'] + view['byteLength'], len(data))
        image = (model / gltf['images'][0]['uri']).read_bytes()
        self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
        compressed = b''
        offset = 8
        while offset < len(image):
            length = struct.unpack('>I', image[offset:offset+4])[0]
            kind = image[offset+4:offset+8]
            raw = image[offset+8:offset+8+length]
            crc = struct.unpack('>I', image[offset+8+length:offset+12+length])[0]
            self.assertEqual(crc, zlib.crc32(kind+raw) & 0xffffffff)
            if kind == b'IDAT': compressed += raw
            offset += length + 12
        rows = zlib.decompress(compressed)
        colors = {tuple(rows[i:i+4]) for i in (1, 5, 10, 14)}
        self.assertEqual(colors, {(255, 0, 255, 255), (0, 255, 255, 255)})
        obj = fixtures / 'obj-bundle'
        material_name = next(line[7:] for line in (obj/'main.obj').read_text().splitlines() if line.startswith('mtllib '))
        material = obj / material_name
        texture_name = next(line[7:] for line in material.read_text().splitlines() if line.startswith('map_Kd '))
        texture = (material.parent / texture_name).resolve()
        self.assertTrue(texture.is_relative_to(obj.resolve()))
        self.assertEqual(texture.read_bytes(), image)
        for line in (fixtures / 'SHA256SUMS').read_text().splitlines():
            expected, name = line.split('  ', 1)
            self.assertEqual(hashlib.sha256((fixtures / name).read_bytes()).hexdigest(), expected)

    def test_actual_ordinary_script_companions_click_and_stop_behavior(self):
        # Actual fixture code executes; these small Overte APIs are explicit host boundaries.
        script = r'''
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const root=process.argv[1];let ending,click,created,edited,deleted,removed,includes=[];
const button={clicked:{connect(f){click=f;},disconnect(f){assert.strictEqual(f,click);click=null;}}};
const context={Script:{resolvePath(p){return path.join(root,p);},include(p){includes.push(p);vm.runInContext(fs.readFileSync(p,'utf8'),context);},scriptEnding:{connect(f){ending=f;}}},
Entities:{addEntity(p,scope){created=p;assert.strictEqual(scope,'local');return 'synthetic-owned-entity';},editEntity(id,p){assert.strictEqual(id,'synthetic-owned-entity');edited=p;},deleteEntity(id){deleted=id;}},
Tablet:{getTablet(){return {addButton(p){assert.strictEqual(p.text,'P2 SCRIPT');return button;},removeButton(b){assert.strictEqual(b,button);removed=true;}};}},
MyAvatar:{position:{x:0,y:0,z:0},orientation:{}},Quat:{getForward(){return {x:0,y:0,z:-1};}},Vec3:{multiply(n,p){return {x:n*p.x,y:n*p.y,z:n*p.z};},sum(a,b){return {x:a.x+b.x,y:a.y+b.y,z:a.z+b.z};}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(root,'main.js'),'utf8'),context);
assert.strictEqual(includes.length,2);assert.strictEqual(created.color.green,255);assert.strictEqual(created.color.blue,255);
assert.strictEqual(created.dimensions.x,.3);assert.strictEqual(created.position.z,-2);
click();assert.strictEqual(edited.color.red,255);assert.strictEqual(edited.color.green,128);
ending();assert.strictEqual(click,null);assert.strictEqual(deleted,'synthetic-owned-entity');assert.strictEqual(removed,true);
console.log('PASS actual fixture includes, visible-result commands, click and owner cleanup; native APIs are host boundaries');
'''
        subprocess.run(['node', '-e', script, str(Path(__file__).parent/'fixtures/script-bundle')], check=True)


if __name__ == '__main__':
    unittest.main()
