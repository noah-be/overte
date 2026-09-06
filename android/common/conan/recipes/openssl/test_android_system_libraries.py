"""Original Android OpenSSL package metadata and the actual libnode consumer."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HERE = Path(__file__).resolve().parent
OPENSSL = load('openssl_system_libraries', HERE / 'conanfile.py').OpenSSLAndroidConan
NODE = load('libnode_system_libraries', HERE.parent / 'libnode/conanfile.py').LibnodeAndroidConan


class AndroidSystemLibraries(unittest.TestCase):
    def test_actual_package_info_exports_bionic_system_library_set(self):
        info = SimpleNamespace(set_property=Mock())
        OPENSSL.package_info(SimpleNamespace(cpp_info=info))
        self.assertEqual(info.libs, ['ssl', 'crypto'])
        self.assertEqual(info.system_libs, ['dl'])
        self.assertEqual([call.args for call in info.set_property.call_args_list],
                         [('cmake_file_name', 'OpenSSL'), ('pkg_config_name', 'openssl')])

    def test_actual_node_consumer_forwards_package_metadata_without_pthread(self):
        info = SimpleNamespace(set_property=Mock(), components={}, includedirs=['/target/include'], libdirs=['/target/lib'])
        OPENSSL.package_info(SimpleNamespace(cpp_info=info))
        recipe = SimpleNamespace(dependencies={'openssl': SimpleNamespace(cpp_info=info)})
        self.assertEqual(NODE._shared_args(recipe, 'openssl', 'openssl'),
                         ['--shared-openssl', '--shared-openssl-includes=/target/include',
                          '--shared-openssl-libname=ssl,crypto,dl', '--shared-openssl-libpath=/target/lib'])


if __name__ == '__main__': unittest.main()
