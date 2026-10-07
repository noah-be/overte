# SPDX-License-Identifier: Apache-2.0
import json
import unittest
from guest_permissions import GROUPS, FLAGS, guest_permission_diagnostics

class GuestReadback(unittest.TestCase):
    def setUp(self):
        self.expected={key:key in ('id_can_connect','id_can_rez','id_can_rez_avatar_entities','id_can_view_asset_urls') for key in FLAGS}
        self.rows=[{'permissions_id':group,**self.expected} for group in GROUPS]
    def test_exact_rows_any_order(self):
        self.assertTrue(guest_permission_diagnostics(self.rows[::-1],self.expected)['passed'])
    def test_actual_flag_mismatch_is_fixed_safe_data(self):
        self.rows[0]['id_can_kick']=True
        result=guest_permission_diagnostics(self.rows,self.expected)
        self.assertFalse(result['passed']);self.assertEqual(result['differences'],[{'group':'anonymous','flag':'id_can_kick','expected':False,'actual':True}])
    def test_missing_empty_and_duplicate_refused(self):
        for rows in ([],self.rows[:3],self.rows+[self.rows[0]]):
            self.assertFalse(guest_permission_diagnostics(rows,self.expected)['passed'])
    def test_nonboolean_false_not_accepted_and_secret_not_exported(self):
        for value in (0,'private-secret',{'secret':'hidden'},None):
            self.rows[0]['id_can_kick']=value
            out=guest_permission_diagnostics(self.rows,self.expected)
            self.assertFalse(out['passed']);self.assertNotIn('private-secret',json.dumps(out));self.assertNotIn('hidden',json.dumps(out))
    def test_unknown_group_and_bad_row_never_export_strings(self):
        for value in ({'permissions_id':'private-user-token'},'secret',{'permissions_id':[]}):
            out=guest_permission_diagnostics(self.rows+[value],self.expected)
            self.assertFalse(out['passed']);self.assertEqual(out['unknownRows'],1);self.assertNotIn('private-user-token',json.dumps(out));self.assertNotIn('secret',json.dumps(out))
    def test_rows_limit_and_bad_baseline(self):
        self.assertFalse(guest_permission_diagnostics(self.rows*5,self.expected)['passed'])
        with self.assertRaises(ValueError):guest_permission_diagnostics(self.rows,{})

if __name__=='__main__':unittest.main()
