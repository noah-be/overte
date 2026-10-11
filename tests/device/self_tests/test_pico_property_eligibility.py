"""Preserve the Pico hardware checks while avoiding repeated WLAN reads."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.android.adapter import AndroidAdapter

PROPERTIES={'ro.product.manufacturer':'PICO','ro.product.brand':'PICO',
 'ro.product.model':'A8110','ro.product.device':'phoenix',
 'ro.product.cpu.abilist':'arm64-v8a,armeabi-v7a',
 'ro.build.version.sdk':'29','ro.opengles.version':'196610'}

class PicoPropertyEligibilityTests(unittest.TestCase):
 def adapter(self, values):
  with patch.dict(os.environ,{'OVERTE_PICO_OPENXR_INPUT':'0'}):
   a=AndroidAdapter('pico')
  a.adb=Mock();a.adb.properties.return_value=values
  return a
 def test_actual_identity_abi_sdk_and_gles_share_one_selected_snapshot(self):
  a=self.adapter(PROPERTIES);self.assertTrue(a.eligible('owned-test-alias'))
  a.adb.properties.assert_called_once_with('owned-test-alias');a.adb.prop.assert_not_called()
 def test_missing_or_incompatible_capabilities_still_fail_closed(self):
  changes=[{'ro.product.cpu.abilist':''},{'ro.product.cpu.abilist':'armeabi-v7a'},
   {'ro.build.version.sdk':'25'},{'ro.build.version.sdk':'unknown'},
   {'ro.opengles.version':'196609'},{'ro.opengles.version':''},
   {k:'Other' for k in ['ro.product.manufacturer','ro.product.brand','ro.product.model','ro.product.device']}]
  for change in changes:
   with self.subTest(change=change):self.assertFalse(self.adapter(PROPERTIES|change).eligible('owned-test-alias'))
  self.assertFalse(self.adapter({}).eligible('owned-test-alias'))
 def test_each_action_reads_current_values_instead_of_reusing_an_old_qualification(self):
  a=self.adapter(PROPERTIES);a.adb.properties.side_effect=[PROPERTIES,PROPERTIES|{'ro.build.version.sdk':'25'}]
  self.assertTrue(a.eligible('owned-test-alias'));self.assertFalse(a.eligible('owned-test-alias'))
  self.assertEqual(a.adb.properties.call_count,2)
 def test_failed_hardware_read_is_not_converted_into_a_success(self):
  a=self.adapter(PROPERTIES);a.adb.properties.side_effect=RuntimeError('unavailable')
  with self.assertRaises(RuntimeError):a.eligible('owned-test-alias')

if __name__=='__main__':unittest.main()
