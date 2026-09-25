#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('repack', ROOT / 'android/phone/tools/repack_unsigned_apk.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class RepackTest(unittest.TestCase):
    def test_preserves_payload_methods_and_metadata_and_rejects_signed(self):
        with tempfile.TemporaryDirectory() as d:
            original, output = Path(d)/'in.apk', Path(d)/'out.apk'
            with zipfile.ZipFile(original, 'w') as z:
                for name, method in [('assets/words', zipfile.ZIP_DEFLATED), ('lib/arm64-v8a/libtest.so', zipfile.ZIP_STORED)]:
                    i = zipfile.ZipInfo(name, (2025,1,2,3,4,6)); i.compress_type = method
                    i.external_attr = 0o644 << 16
                    z.writestr(i, b'preserve every byte\x00'*2000, compresslevel=1)
                    if method == zipfile.ZIP_DEFLATED:i.external_attr = 0
            before = m.inventory(original)
            m.recompress(original, output)
            self.assertEqual(m.inventory(output), before)
            self.assertLess(output.stat().st_size, original.stat().st_size)
            with zipfile.ZipFile(original,'a') as z:z.writestr('META-INF/CERT.RSA', b'not an unsigned APK')
            with self.assertRaisesRegex(ValueError,'signed APK'):m.recompress(original,output)

if __name__ == '__main__':unittest.main()
