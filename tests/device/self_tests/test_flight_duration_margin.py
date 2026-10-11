"""Flight must retain the observed ascent threshold despite takeoff latency."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ,{'OVERTE_DEVICE_ADAPTER_MANIFEST':'unused.json','OVERTE_DEVICE_TARGET_SELECTOR':'owned-test','OVERTE_DEVICE_ARTIFACT_DIR':'.'}):
 from overte_session import OverteSession

class FlightDurationMarginTests(unittest.TestCase):
 def run_flight(self, explicit=None):
  with patch.dict(os.environ,{'OVERTE_DEVICE_ADAPTER_MANIFEST':'unused.json','OVERTE_DEVICE_TARGET_SELECTOR':'owned-test','OVERTE_DEVICE_ARTIFACT_DIR':'.'}):
   session=OverteSession()
  session.pico_openxr=True
  before={'avatar':{'flyingEnabled':True},'verticalEvents':{'flightCount':0}}
  session.vertical_ground_snapshot=Mock(return_value=before)
  session.assert_visible_movement_world=Mock()
  applied={}
  def invoke(operation,values):
   self.assertEqual(operation,'input.fly')
   gain=max(0,values['durationSeconds']-0.518)*2
   applied.update(avatar={'flyingEnabled':True},verticalEvents={'flightCount':1,'lastFlightStartY':2.112,'lastFlightPeakY':2.112+gain})
  session._invoke=invoke
  def wait(message,predicate):
   if not predicate(applied):raise RuntimeError('insufficient actual flight gain')
   return applied
  session.wait_until=wait
  with patch('overte_session.write_json'),patch('overte_session.process_identity',return_value='123:1'),patch('overte_session.assert_process'):
   result=session.fly(explicit)
  self.assertEqual(session.assert_visible_movement_world.call_count,2)
  return result
 def test_default_pico_input_has_margin_for_observed_takeoff_delay(self):
  before,active=self.run_flight()
  event=active['verticalEvents']
  self.assertGreaterEqual(event['lastFlightPeakY']-event['lastFlightStartY'],0.5)
  self.assertLess(event['lastFlightPeakY'],4)
 def test_insufficient_flight_gain_still_fails(self):
  with self.assertRaisesRegex(RuntimeError,'insufficient actual flight gain'):self.run_flight(0.75)
if __name__=='__main__':unittest.main()
