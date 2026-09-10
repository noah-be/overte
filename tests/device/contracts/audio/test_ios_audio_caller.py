# SPDX-License-Identifier: Apache-2.0
"""Focused source wiring checks, explicitly not a Qt/macOS compilation."""
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[4]
class CallerTests(unittest.TestCase):
    def setUp(self):
        self.source=(ROOT/'libraries/audio-client/src/AudioClient.cpp').read_text()
    def test_activation_precedes_permission_ticket(self):
        start=self.source.split('void AudioClient::start() {',1)[1].split('void AudioClient::stop()',1)[0]
        self.assertLess(start.index('overteIOSActivateAudioSession()'),start.index('overteIOSRequestMicrophonePermission()'))
    def test_callback_queued_and_cleared_before_stop(self):
        self.assertIn('refreshIOSAudioInput(); }, Qt::QueuedConnection)',self.source)
        stop=self.source.split('void AudioClient::stop() {',1)[1].split('void AudioClient::handleAudioEnvironmentDataPacket',1)[0]
        self.assertLess(stop.index('setIOSAudioStateCallback({})'),stop.index('if (!_audioLifecycleRunning)'))
    def test_mute_closes_and_grant_reopens_actual_input(self):
        refresh=self.source.split('void AudioClient::refreshIOSAudioInput() {',1)[1].split('bool AudioClient::switchInputToAudioDevice',1)[0]
        self.assertIn('_isMuted || !overteIOSMicrophonePermissionGranted()',refresh)
        self.assertIn('switchInputToAudioDevice(HifiAudioDeviceInfo(), true)',refresh)
        self.assertIn('_inputRingBuffer.clear()',refresh)
        self.assertIn('switchInputToAudioDevice(defaultAudioDeviceForMode',refresh)
        self.assertIn('microphonePermissionGranted = !_isMuted && overteIOSMicrophonePermissionGranted()',self.source)
if __name__ == '__main__': unittest.main()
