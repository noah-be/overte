"""Negative pixel-boundary checks; all images here are explicit host fixtures."""
# Copyright 2026 Overte e.V.
# SPDX-License-Identifier: Apache-2.0
import sys
from io import BytesIO
from pathlib import Path
import unittest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from adapters.ios import native_permission_visual as visual
class Appearance(unittest.TestCase):
 def setUp(self):
  self.switch={'x':60.,'y':20.,'width':30.,'height':16.}
  self.row={'x':5.,'y':18.,'width':90.,'height':20.}
  self.viewport={'x':0.,'y':0.,'width':100.,'height':50.}
 def picture(self,state,identity=True,knob=True,center=None,green=None):
  im=Image.new('RGB',(200,100),(25,25,25));draw=ImageDraw.Draw(im)
  if identity:draw.rectangle((15,43,34,63),fill=(150,70,210))
  fill=(50,215,80) if (state=='granted' if green is None else green) else (60,60,65)
  draw.rounded_rectangle((120,40,179,71),radius=15,fill=fill)
  if knob:
   center=(163 if state=='granted' else 136) if center is None else center
   draw.ellipse((center-13,42,center+13,68),fill=(240,240,240))
  output=BytesIO();im.save(output,format='PNG');return output.getvalue()
 def observe(self,before,after,**changes):
  return visual.observe(before,after,changes.get('switch',self.switch),changes.get('row',self.row),changes.get('viewport',self.viewport))
 def test_both_real_pixel_directions_and_unchanged_state_are_observable(self):
  for first,last in (('granted','denied'),('denied','granted'),('granted','granted')):
   result=self.observe(self.picture(first),self.picture(last))
   self.assertEqual(first,result['before']['state']);self.assertEqual(last,result['after']['state'])
   self.assertTrue(result['ownedRowFeaturesVerified'])
 def test_transition_knob_blank_knob_and_wrong_color_position_are_rejected(self):
  for invalid in (self.picture('granted',center=150),self.picture('granted',knob=False),self.picture('denied',green=True)):
   with self.assertRaises(AssertionError):self.observe(self.picture('granted'),invalid)
 def test_other_or_occluded_app_row_cannot_verify_permission(self):
  with self.assertRaisesRegex(AssertionError,'owned-row-changed'):
   self.observe(self.picture('granted'),self.picture('denied',identity=False))
  with self.assertRaisesRegex(AssertionError,'features-not-observed'):
   self.observe(self.picture('granted',identity=False),self.picture('denied',identity=False))
 def test_changed_image_size_invalid_bytes_and_nonfinite_or_offscreen_geometry_fail(self):
  for invalid in (b'not a native PNG',b''):
   with self.assertRaises(Exception):self.observe(self.picture('granted'),invalid)
  for change in ({'x':float('nan')},{'x':100.},{'height':0.}):
   with self.assertRaises(AssertionError):self.observe(self.picture('granted'),self.picture('denied'),switch={**self.switch,**change})
  with self.assertRaises(AssertionError):self.observe(self.picture('granted'),self.picture('denied'),viewport={**self.viewport,'height':70.})
if __name__=='__main__':unittest.main()
