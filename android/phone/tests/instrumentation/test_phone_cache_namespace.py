"""Verify diagnostic cache namespace bounds using the actual production parser."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]

class CacheNamespaceTest(unittest.TestCase):
    def test_actual_parser(self):
        source = (ROOT / 'libraries/material-networking/src/material-networking/TextureCache.cpp').read_text()
        start = source.index('static int phoneLoadingCacheNamespace(')
        parser = source[start:source.index('\n}', start) + 2]
        driver = '#include <cassert>\n#include <string>\n' + parser + r'''
int main() {
    assert(phoneLoadingCacheNamespace(nullptr, 0) == 0);
    for (int i = 0; i <= 1000; ++i) {
        auto s = std::to_string(i);
        assert(phoneLoadingCacheNamespace(s.data(), int(s.size())) == (i >= 1 && i <= 99 ? i : 0));
    }
    for (const auto* text : {"", "01", "00", "-1", "+1", "1/", "1.", " 1", "1 ", "../", "a", "1a", "a1"}) {
        std::string s(text);
        assert(phoneLoadingCacheNamespace(s.data(), int(s.size())) == 0);
    }
    const char embedded[] = {'1', '\0'};
    assert(phoneLoadingCacheNamespace(embedded, 2) == 0);
}
'''
        with tempfile.TemporaryDirectory(prefix='overte-cache-namespace-') as directory:
            cpp = Path(directory) / 'test.cpp'
            exe = Path(directory) / 'test'
            cpp.write_text(driver)
            subprocess.run(['c++', '-std=c++17', str(cpp), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True)

if __name__ == '__main__':
    unittest.main()
