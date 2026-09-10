# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[3]

class NativeMetricsTests(unittest.TestCase):
    def test_real_typed_store_callback_freshness_and_degradation(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / 'metrics'
            subprocess.run(['c++', '-std=c++14', '-Wall', '-Wextra', '-Werror', '-pthread', '-I', str(ROOT),
                            str(ROOT / 'interface/src/metrics/NativeMetrics.cpp'),
                            str(Path(__file__).with_name('native-metrics-test.cpp')), '-o', str(binary)],
                           check=True, timeout=30)
            subprocess.run([str(binary)], check=True, timeout=10)

    def test_actual_refresh_rate_caller_keeps_vr_and_preferences(self):
        source = (ROOT / 'interface/src/RefreshRateManager.cpp').read_text()
        query = source.split('int RefreshRateManager::queryRefreshRateTarget', 1)[1].split('void RefreshRateManager::updateRefreshRateController', 1)[0]
        self.assertIn('if (uxMode == RefreshRateManager::UXMode::DESKTOP)', query)
        self.assertIn('#if defined(Q_OS_IOS)', query)
        self.assertIn('iosFrameLimit(targetRefreshRate, overte::metrics::latestNativeSample())', query)
        self.assertNotIn('.set(', query)
        self.assertIn('setNativeMetricsChangedCallback({})', source)
        self.assertIn('_metricsRefreshQueued.compare_exchange_strong', source)
        self.assertIn('freshnessTimer->setInterval(5000)', source)

if __name__ == '__main__': unittest.main()
