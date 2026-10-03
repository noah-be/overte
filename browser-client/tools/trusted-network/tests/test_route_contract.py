# SPDX-License-Identifier: Apache-2.0
"""CPU serialization contracts only: never namespaces/caps/netlink sockets/signals."""
import ctypes
import ipaddress
import pathlib
import struct
import subprocess
import tempfile
import unittest

HERE=pathlib.Path(__file__).parent
ROUTES=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','169.254.0.0/16',
        '100.64.0.0/10','192.0.0.0/24','192.0.2.0/24','198.18.0.0/15',
        '198.51.100.0/24','203.0.113.0/24','224.0.0.0/4','240.0.0.0/4')

class Serialization(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.work=tempfile.TemporaryDirectory(prefix='overte-setup-cpu-')
  library=pathlib.Path(cls.work.name)/'contract.so'
  subprocess.run(['cc','-Wall','-Wextra','-Werror','-O2','-fPIC','-shared',str(HERE.parent/'src'/'route-contract.c'),'-o',str(library)],check=True,capture_output=True)
  cls.api=ctypes.CDLL(str(library))
  cls.api.overte_route_message.argtypes=[ctypes.c_uint,ctypes.c_uint32,ctypes.c_void_p,ctypes.c_size_t]
  cls.api.overte_route_message.restype=ctypes.c_size_t
  cls.api.overte_route_ack.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint32]
  cls.api.overte_route_ack.restype=ctypes.c_int
  cls.api.overte_self_map.argtypes=[ctypes.c_uint32,ctypes.c_void_p,ctypes.c_size_t]
  cls.api.overte_self_map.restype=ctypes.c_int
 @classmethod
 def tearDownClass(cls): cls.work.cleanup()
 def message(self,index=0,sequence=1,capacity=64):
  output=ctypes.create_string_buffer(b'X'*64,65)
  size=self.api.overte_route_message(index,sequence,output,capacity)
  return size,output.raw[:size],output
 def test_twelve_exact_fixed_routes_independent_wire_oracle(self):
  for index,source in enumerate(ROUTES):
   with self.subTest(index=index):
    size,raw,_=self.message(index,index+1)
    network=ipaddress.ip_network(source)
    expected=struct.pack('=IHHII',36,24,0x605,index+1,0)
    expected+=struct.pack('=BBBBBBBBI',2,network.prefixlen,0,0,254,3,0,8,0)
    expected+=struct.pack('=HH',8,1)+network.network_address.packed
    self.assertEqual(size,36);self.assertEqual(raw,expected)
 def test_capacity_failure_is_atomic_and_does_not_touch_output(self):
  for capacity in (0,1,35):
   size,raw,out=self.message(capacity=capacity)
   self.assertEqual(size,0);self.assertEqual(out.raw[:64],b'X'*64)
 def test_invalid_index_sequence_and_null_refused(self):
  self.assertEqual(self.message(12)[0],0)
  self.assertEqual(self.message(2**32-1)[0],0)
  self.assertEqual(self.message(sequence=0)[0],0)
  self.assertEqual(self.api.overte_route_message(0,1,None,64),0)
 def ack(self,error=0,sequence=5,type_=2,original_type=24,original_seq=5,length=36,trailing=b''):
  return struct.pack('=IHHIIiIHHII',length,type_,0,sequence,0,error,36,original_type,0x605,original_seq,0)+trailing
 def classify(self,raw,sequence=5):
  buffer=ctypes.create_string_buffer(raw)
  return self.api.overte_route_ack(buffer,len(raw),sequence)
 def test_success_requires_matching_request_ack(self):self.assertEqual(self.classify(self.ack()),1)
 def test_permission_and_duplicate_failure_retained(self):
  self.assertEqual(self.classify(self.ack(error=-1)),-1)
  self.assertEqual(self.classify(self.ack(error=-17)),-17)
 def test_malformed_wrong_type_sequence_length_truncation_and_trailing_refused(self):
  for raw in (self.ack(type_=24),self.ack(sequence=6),self.ack(original_seq=6),self.ack(original_type=22),
              self.ack(length=35),self.ack()[:-1],self.ack(trailing=b'X'),self.ack(error=1),self.ack(error=-4096)):
   self.assertEqual(self.classify(raw),0)
 def test_original_ack_request_length_flags_pid_and_kernel_error_are_exact(self):
  for offset,format_,value in ((20,'I',35),(26,'H',0),(32,'I',1)):
   packet=bytearray(self.ack());struct.pack_into('='+format_,packet,offset,value)
   self.assertEqual(self.classify(bytes(packet)),0)
 def test_exact_single_self_maps(self):
  for identity in (1,1000,2**32-2):
   out=ctypes.create_string_buffer(32)
   size=self.api.overte_self_map(identity,out,32)
   self.assertEqual(out.raw[:size],f'{identity} {identity} 1\n'.encode())
 def test_invalid_self_maps_do_not_change_output(self):
  for identity,capacity in ((0,32),(2**32-1,32),(1000,23),(2**32-2,24)):
   out=ctypes.create_string_buffer(b'X'*32,33)
   self.assertEqual(self.api.overte_self_map(identity,out,capacity),0)
   self.assertEqual(out.raw[:32],b'X'*32)
 def test_no_runnable_entrypoint_or_generic_exec_or_payload_mode(self):
  source=(HERE.parent/'src'/'route-contract.c').read_text()
  self.assertNotIn('int main(',source)
  self.assertNotIn('execv(',source);self.assertNotIn('system(',source)
  self.assertNotIn('setns(',source)

if __name__=='__main__':unittest.main()
