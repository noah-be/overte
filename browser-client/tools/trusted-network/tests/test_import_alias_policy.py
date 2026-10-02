# SPDX-License-Identifier: Apache-2.0
"""Bounded alias staging/runtime contracts; no profile/network/namespace changes."""
import copy
import hashlib
import importlib.util
import os
import stat
import subprocess
import tempfile
import unittest
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location('alias_' + name, BASE / 'workflow' / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


build = module('build')
install = module('install')
# Public packaged descriptor; /usr/share is intentionally writable on the hosted image.
# Keep original immutable canonical ancestry/FD/hash/budget assertions.
PUBLIC_FIXTURE = Path('/usr/lib/systemd/system/basic.target')
IMAGE_UTC = Path('/usr/share/zoneinfo/Etc/UTC')


def row(value='/usr/share/doc/python3.12/EXTERNALLY-MANAGED', size=32):
    return {'path': value, 'bytes': size, 'sha256': 'a' * 64}


def info(kind=stat.S_IFDIR, mode=0o755, uid=0):
    return SimpleNamespace(st_mode=kind | mode, st_uid=uid)


class AliasPolicy(unittest.TestCase):
    def test_exact_read_rules_include_only_literal_targets_and_necessary_directory_ancestors(self):
        records = [row('/etc/python3.12/sitecustomize.py'), row()]
        rules = build.alias_read_rules(records)
        self.assertIn('"/etc/" r,', rules)
        self.assertIn('"/etc/python3.12/" r,', rules)
        self.assertIn('"/etc/python3.12/sitecustomize.py" r,', rules)
        self.assertIn('"/usr/share/doc/python3.12/EXTERNALLY-MANAGED" r,', rules)
        for rejected in ('**', '*', ' w', 'capability', '/etc/**', '/usr/share/**', 'unlisted'):
            self.assertNotIn(rejected, rules)
        self.assertEqual(build.alias_read_rules([]), '')

    def test_rule_schema_refuses_injection_noncanonical_private_and_unknown_fields(self):
        bad = ['/usr/share/**', '/usr/share/@{HOME}', '/usr/share/evil" r,\n capability,',
               '/usr/share/x\\y', '/usr/share/../etc/x', '/usr//share/x', '/usr/share/x/',
               '/home/user/key', '/proc/self/fd/3', '/usr/share/[x]', '/usr/share/{a,b}']
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                build.alias_read_rules([row(value)])
            with self.assertRaises(install.Refusal):
                install.validate_reviewed_aliases([row(value)])
        for changed in (dict(row(), unknown=True), dict(row(), bytes=True), dict(row(), sha256='G' * 64)):
            with self.assertRaises(ValueError):
                build.validate_alias_records([changed])
            with self.assertRaises(install.Refusal):
                install.validate_reviewed_aliases([changed])

    def test_sorted_unique_count_and_byte_bounds_match_installer(self):
        invalid = [[row(), row()], [row('/usr/share/z'), row('/usr/share/a')],
                   [row('/usr/share/' + str(i).zfill(3)) for i in range(65)],
                   [row(size=4 * 1024 * 1024 + 1)],
                   [row(size=-1)],
                   [row('/usr/share/' + str(i), 4 * 1024 * 1024) for i in range(5)],
                   [row('/usr/share/' + str(i) + 'x' * 4000) for i in range(5)],
                   [row('/usr/' + '/'.join('x' for _ in range(34)))]]
        for value in invalid:
            with self.assertRaises(ValueError):
                build.validate_alias_records(value)
            with self.assertRaises(install.Refusal):
                install.validate_reviewed_aliases(value)
        good = [row('/usr/share/' + str(i), 4 * 1024 * 1024) for i in range(4)]
        self.assertEqual(build.validate_alias_records(good), good)
        self.assertEqual(install.validate_reviewed_aliases(good), good)

    def test_zero_byte_regular_alias_record_and_schema_preserve_empty_python_module(self):
        empty = {'path': '/usr/share/owned-empty.py', 'bytes': 0, 'sha256': hashlib.sha256(b'').hexdigest()}
        self.assertEqual(build.validate_alias_records([empty]), [empty])
        self.assertEqual(install.validate_reviewed_aliases([empty]), [empty])
        original = os.fstat

        def reviewed_root_metadata(fd):
            value = original(fd)
            fields = {name: getattr(value, name) for name in
                      ('st_mode', 'st_uid', 'st_size', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')}
            fields['st_uid'] = 0
            return SimpleNamespace(**fields)

        # The only controlled boundary is owner metadata, because this CPU
        # fixture must never chown/write a real host root-owned file. Reads,
        # EOF, SHA256, sizes and descriptor closure remain the actual code.
        with tempfile.TemporaryDirectory(prefix='overte-empty-alias-cpu-') as owned:
            target = Path(owned)/'empty'
            target.write_bytes(b'')
            real_open = os.open
            with patch.object(build, 'rooted', return_value=empty['path']), \
                    patch.object(build.os, 'open', side_effect=lambda *_args, **_kwargs: real_open(target, os.O_RDONLY | os.O_NOFOLLOW)), \
                    patch.object(build.os, 'fstat', reviewed_root_metadata):
                self.assertEqual(build.alias_record(empty['path']), empty)

    def virtual_chain(self, mutations=None):
        chain = {'/': info(), '/usr': info(), '/usr/lib': info(), '/usr/lib/python3.12': info(),
                 '/usr/lib/python3.12/sitecustomize.py': info(stat.S_IFLNK, 0o777),
                 '/etc': info(), '/etc/python3.12': info(),
                 '/etc/python3.12/sitecustomize.py': info(stat.S_IFREG, 0o644)}
        if mutations:
            chain.update(mutations)
        return (patch.object(Path, 'lstat', lambda value: chain[str(value)]),
                patch.object(build.os, 'readlink', return_value='/etc/python3.12/sitecustomize.py'))

    def test_canonical_root_owned_regular_alias_chain_is_admitted(self):
        a, b = self.virtual_chain()
        with a, b:
            self.assertEqual(build.rooted_alias('/usr/lib/python3.12/sitecustomize.py'),
                             '/etc/python3.12/sitecustomize.py')

    def test_writable_ancestor_user_link_and_directory_target_refuse(self):
        for changed in ({'/usr/lib/python3.12': info(mode=0o777)},
                        {'/usr/lib/python3.12/sitecustomize.py': info(stat.S_IFLNK, 0o777, 1000)},
                        {'/etc/python3.12': info(mode=0o777)},
                        {'/etc/python3.12/sitecustomize.py': info(stat.S_IFREG, 0o666)},
                        {'/etc/python3.12/sitecustomize.py': info(stat.S_IFDIR)}):
            a, b = self.virtual_chain(changed)
            with a, b, self.assertRaisesRegex(ValueError, 'chain-untrusted'):
                build.rooted_alias('/usr/lib/python3.12/sitecustomize.py')

    def test_cycle_and_user_owned_intermediate_alias_refuse(self):
        a, _ = self.virtual_chain()
        with a, patch.object(build.os, 'readlink', return_value='/usr/lib/python3.12/sitecustomize.py'), \
                self.assertRaisesRegex(ValueError, 'chain-bound'):
            build.rooted_alias('/usr/lib/python3.12/sitecustomize.py')
        a, b = self.virtual_chain({'/etc/python3.12/sitecustomize.py': info(stat.S_IFLNK, 0o777, 1000)})
        with a, b, self.assertRaisesRegex(ValueError, 'chain-untrusted'):
            build.rooted_alias('/usr/lib/python3.12/sitecustomize.py')

    def test_writable_usr_share_alias_ancestor_refuses_before_profile_bytes_are_staged(self):
        nodes = {'/': info(), '/usr': info(), '/usr/lib': info(), '/usr/lib/python3.12': info(),
                 '/usr/lib/python3.12/owned-marker': info(stat.S_IFLNK, 0o777),
                 '/usr/share': info(mode=0o777), '/usr/share/owned-marker': info(stat.S_IFREG, 0o644)}

        def inventory(_python, *, aliases):
            with patch.object(Path, 'lstat', lambda value: nodes[str(value)]), \
                    patch.object(build.os, 'readlink', return_value='/usr/share/owned-marker'):
                build.rooted_alias('/usr/lib/python3.12/owned-marker')
            self.fail('An untrusted ancestor cannot reach alias publication')

        policy = {'version': 1, 'hostUID': 1000, 'hostGID': 1000, 'sessionParent': '/tmp',
                  'nativeExecutables': ['/opt/overte/interface'], 'nativeReadRoots': ['/opt/overte']}
        with tempfile.TemporaryDirectory(prefix='overte-writable-alias-build-') as owned, \
                patch.object(build, 'trusted_import_paths', inventory):
            stage = Path(owned)/'stage'
            with self.assertRaisesRegex(ValueError, 'chain-untrusted'):
                build.build(stage, policy)
            self.assertEqual(list(stage.iterdir()), [])

    def test_measured_writable_utc_refuses_original_ancestry_before_descriptor_open(self):
        original = Path.stat

        def measured_mode(value, *args, **kwargs):
            actual = original(value, *args, **kwargs)
            if value != IMAGE_UTC:
                return actual
            fields = list(actual)
            fields[0], fields[4], fields[6] = stat.S_IFREG | 0o777, 0, 114
            return os.stat_result(fields)

        with patch.object(Path, 'stat', measured_mode), patch.object(build.os, 'open') as opened:
            with self.assertRaises(build.TrustRefusal) as raised:
                build.alias_record(IMAGE_UTC)
        opened.assert_not_called()
        refusal = build.staging_failure(raised.exception)
        self.assertEqual(refusal['category'], 'runtime-package-path-not-root-trusted')
        self.assertTrue(refusal['metadata']['rootOwned'])
        self.assertTrue(refusal['metadata']['groupOrOtherWritable'])
        self.assertEqual(refusal['metadata']['permissions'], 0o777)
        self.assertEqual(refusal['metadata']['boundedBytes'], 114)

    def test_writable_matching_bytes_refuse_original_alias_fd_gate_without_hash_reads(self):
        with tempfile.TemporaryDirectory(prefix='overte-writable-public-fixture-') as directory:
            target = Path(directory)/'fixture'
            target.write_bytes(PUBLIC_FIXTURE.read_bytes())
            target.chmod(0o777)
            real_open, real_stat = os.open, os.fstat
            opened = []

            def acquire(*_args, **_kwargs):
                fd = real_open(target, os.O_RDONLY | os.O_NOFOLLOW)
                opened.append(fd)
                return fd

            def reviewed_owner(fd):
                actual = real_stat(fd)
                return SimpleNamespace(st_uid=0, st_mode=actual.st_mode, st_size=actual.st_size)

            with patch.object(build, 'rooted', return_value=str(PUBLIC_FIXTURE)), \
                    patch.object(build.os, 'open', acquire), patch.object(build.os, 'fstat', reviewed_owner), \
                    patch.object(build.os, 'read') as read:
                with self.assertRaises(build.TrustRefusal):
                    build.alias_record(PUBLIC_FIXTURE)
            read.assert_not_called()
            for fd in opened:
                with self.assertRaises(OSError):
                    real_stat(fd)

    def test_actual_root_owned_public_descriptor_hash_and_size_match_independent_digest(self):
        self.assertEqual(build.alias_record(PUBLIC_FIXTURE), {'path': str(PUBLIC_FIXTURE), 'bytes': PUBLIC_FIXTURE.stat().st_size,
                                                 'sha256': hashlib.sha256(PUBLIC_FIXTURE.read_bytes()).hexdigest()})

    def test_actual_user_owned_temporary_target_refuses(self):
        with tempfile.TemporaryDirectory() as owned:
            target = Path(owned) / 'target'
            target.write_bytes(b'not a distro target')
            with self.assertRaises(ValueError):
                build.alias_record(target)

    def test_descriptor_metadata_mutation_refuses_and_owned_fd_closes(self):
        original = os.fstat
        real_open = os.open
        opened = []
        calls = [0]

        def tracking(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd

        def changed(fd):
            value = original(fd)
            calls[0] += 1
            if calls[0] > 1:
                fields = {name: getattr(value, name) for name in
                          ('st_mode', 'st_uid', 'st_size', 'st_dev', 'st_ino', 'st_mtime_ns', 'st_ctime_ns')}
                fields['st_mtime_ns'] += 1
                return SimpleNamespace(**fields)
            return value

        with patch.object(build.os, 'open', tracking), patch.object(build.os, 'fstat', changed), \
                self.assertRaisesRegex(ValueError, 'target-changed'):
            build.alias_record(PUBLIC_FIXTURE)
        with self.assertRaises(OSError):
            os.fstat(opened[-1])

    def test_installer_recomputes_inventory_and_hashes_before_mutation(self):
        aliases = []
        python = str(Path('/usr/bin/python3').resolve())
        libraries=[];cache=os.environ.get('OVERTE_SIGNED_LIBRARY_CACHE');keyring=os.environ.get('OVERTE_SIGNED_LIBRARY_KEYRING')
        library=build.signed_library_context(python,cache,keyring)
        if library is None:paths=build.trusted_import_paths(python,aliases=aliases)
        else:paths=build.trusted_import_paths(python,aliases=aliases,signed_library=library,signed_libraries=libraries)
        manifest = {'python': python, 'pythonImportPaths': paths, 'pythonImportAliases': aliases}
        if library is not None:manifest['pythonSignedLibraries']=libraries
        install.verify_python_imports(manifest,cache,keyring)
        changed = copy.deepcopy(manifest)
        changed['pythonImportAliases'] = [row()]
        with self.assertRaisesRegex(install.Refusal, 'runtime-mismatch'):
            install.verify_python_imports(changed,cache,keyring)

    def test_install_refuses_hash_only_mutation_after_review(self):
        reviewed = [row()]
        changed = [dict(row(), sha256='b' * 64)]
        fake = SimpleNamespace(trusted_import_paths=lambda _python, aliases: (aliases.extend(changed), ['/usr/lib/python3.12'])[1])
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=lambda _: None))
        manifest = {'python': '/usr/bin/python3.12', 'pythonImportPaths': ['/usr/lib/python3.12'],
                    'pythonImportAliases': reviewed}
        # Use only the existing explicit administrator import boundary;
        # never execute or install the fake module/profile as host code.
        with patch('importlib.util.spec_from_file_location', return_value=spec), \
                patch('importlib.util.module_from_spec', return_value=fake), \
                self.assertRaisesRegex(install.Refusal, 'runtime-mismatch'):
            install.verify_python_imports(manifest)

    def test_real_build_nonzero_inventory_binds_exact_profile_manifest_header_and_static_binary(self):
        record = build.alias_record(PUBLIC_FIXTURE)

        def inventory(_python, *, aliases):
            aliases.append(record)
            return ['/usr/lib/python3.14']

        policy = {'version': 1, 'hostUID': 1000, 'hostGID': 1000, 'sessionParent': '/tmp',
                  'nativeExecutables': ['/opt/overte/interface'], 'nativeReadRoots': ['/opt/overte']}
        with tempfile.TemporaryDirectory(prefix='overte-nonzero-alias-build-') as owned, \
                patch.object(build, 'trusted_import_paths', inventory):
            root = Path(owned)/'stage'
            manifest = build.build(root, policy, static_libraries=os.environ.get('OVERTE_SETUP_STATIC_LIBRARIES'))
            self.assertEqual(manifest['version'], 2)
            self.assertEqual(manifest['pythonImportAliases'], [record])
            profile = (root/'overte-browser-network').read_text()
            setup, owner = profile.split('profile overte-browser-network-owner flags=', 1)
            self.assertIn('"/usr/lib/systemd/system/basic.target" r,', setup)
            self.assertIn('"/usr/lib/systemd/system/" r,', setup)
            self.assertNotIn('/usr/share/**', setup)
            self.assertNotIn('/etc/**', setup)
            self.assertIn('audit deny capability,', owner)
            header = (root/'image.h').read_text()
            self.assertIn('#define PYTHON_IMPORT_ALIAS_COUNT 1', header)
            self.assertIn(json.dumps(str(PUBLIC_FIXTURE)), header)
            self.assertIn('PYTHON_IMPORT_ALIAS_HASHES', header)
            digest = hashlib.sha256((root/'manifest.json').read_bytes()).hexdigest()
            checked, _ = install.verified_bundle(root, digest)
            self.assertEqual(checked['pythonImportAliases'], [record])
            # Mutating reviewed alias fields alone, even to another valid hash,
            # cannot reuse the original reviewed manifest digest.
            mutated = copy.deepcopy(manifest)
            mutated['pythonImportAliases'][0]['sha256'] = '0' * 64
            (root/'manifest.json').write_text(json.dumps(mutated))
            with self.assertRaisesRegex(install.Refusal, 'review-manifest-mismatch'):
                install.verified_bundle(root, digest)
        changed = copy.deepcopy(manifest)
        changed['pythonImportPaths'] = ['/usr/lib/python3.99']
        cache=os.environ.get('OVERTE_SIGNED_LIBRARY_CACHE');keyring=os.environ.get('OVERTE_SIGNED_LIBRARY_KEYRING')
        if cache is not None:
            # The positive above deliberately exercises DEFAULT v2 with an
            # authored inventory. This final negative uses the ACTUAL selected
            # interpreter, so explicitly authenticate its typed Noble context.
            changed['version']=3
            changed['pythonSignedLibraries']=[build.signed_library_context(changed['python'],cache,keyring)]
        with self.assertRaisesRegex(install.Refusal, 'runtime-mismatch'):
            install.verify_python_imports(changed,cache,keyring)


class RuntimeAliasHash(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory(prefix='overte-alias-runtime-cpu-')
        cls.root = Path(cls.work.name)
        content = PUBLIC_FIXTURE.read_bytes()
        digest = hashlib.sha256(content).digest()
        source = (BASE / 'src/launcher.c').read_text()
        cls.source = source
        begin = source.index('static int verify_import_alias_target(int fd,const char *resolved) {')
        function = source[begin:source.index('\nint main(', begin)]
        code = '''#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <openssl/sha.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static unsigned import_alias_reads;static uint64_t import_alias_read_bytes;
#define PYTHON_IMPORT_ALIAS_COUNT 4
static const char *PYTHON_IMPORT_ALIAS_PATHS[4]={"/usr/share/approved", "/usr/share/stale-hash", "/usr/share/stale-size", "/usr/share/approved-empty"};
'''
        code += 'static const unsigned PYTHON_IMPORT_ALIAS_BYTES[4]={' + ','.join(map(str, (len(content), len(content), len(content)+1, 0))) + '};\n'
        code += 'static const unsigned char PYTHON_IMPORT_ALIAS_HASHES[4][32]={{' + ','.join(map(str, digest)) + '},{0},{0},{' + ','.join(map(str, hashlib.sha256(b'').digest())) + '}};\n'
        code += '''static int test_reviewed_owner_fd=-1;
static int test_fstat(int fd,struct stat *output){int result=fstat(fd,output);if(!result&&fd==test_reviewed_owner_fd)output->st_uid=0;return result;}
#define fstat test_fstat
static unsigned test_preads;
static ssize_t test_pread(int fd,void *buffer,size_t count,off_t offset){test_preads++;return pread(fd,buffer,count,offset);}
#define pread test_pread
'''
        code += '''static int digest_bytes(const void *data,size_t size,unsigned char output[32]){return SHA256(data,size,output)!=NULL;}
''' + function + '''
int check(const char *path,int fd){import_alias_reads=0;import_alias_read_bytes=0;return verify_import_alias_target(fd,path);}
int check_repeat(const char *path,int fd){import_alias_reads=0;import_alias_read_bytes=0;for(int i=0;i<129;i++)if(verify_import_alias_target(fd,path))return i;return 129;}
int check_byte_budget(const char *path,int fd){import_alias_reads=0;import_alias_read_bytes=33554432;return verify_import_alias_target(fd,path);}
int check_reviewed_owner(int fd){test_preads=0;test_reviewed_owner_fd=fd;int result=check("/usr/share/approved",fd);test_reviewed_owner_fd=-1;return result;}
unsigned count_read_calls(void){return test_preads;}
int check_empty(int fd){test_reviewed_owner_fd=fd;int result=check("/usr/share/approved-empty",fd);test_reviewed_owner_fd=-1;return result;}
'''
        (cls.root/'api.c').write_text(code)
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-O2', '-shared', '-fPIC',
                        str(cls.root/'api.c'), '-lcrypto', '-o', str(cls.root/'api.so')], check=True, capture_output=True)
        import ctypes
        cls.api = ctypes.CDLL(str(cls.root/'api.so'))
        cls.api.check.argtypes = [ctypes.c_char_p, ctypes.c_int]
        cls.api.check.restype = ctypes.c_int
        cls.api.check_repeat.argtypes = cls.api.check.argtypes
        cls.api.check_byte_budget.argtypes = cls.api.check.argtypes
        cls.api.check_empty.argtypes = [ctypes.c_int]
        cls.api.check_reviewed_owner.argtypes = [ctypes.c_int]
        cls.api.check_reviewed_owner.restype = ctypes.c_int
        cls.api.count_read_calls.argtypes = []
        cls.api.count_read_calls.restype = ctypes.c_uint

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def fd(self):
        fd = os.open(PUBLIC_FIXTURE, os.O_RDONLY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        return fd

    def test_actual_c_writable_matching_bytes_refuse_before_read_with_reviewed_owner_boundary(self):
        target = self.root/'writable'
        target.write_bytes(PUBLIC_FIXTURE.read_bytes())
        target.chmod(0o777)
        fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        self.assertEqual(self.api.check_reviewed_owner(fd), -1)
        self.assertEqual(self.api.count_read_calls(), 0)

    def test_actual_c_descriptor_hash_accepts_matching_reviewed_bytes(self):
        self.assertEqual(self.api.check(b'/usr/share/approved', self.fd()), 0)

    def test_actual_c_refuses_unlisted_stale_hash_stale_size_unreadable_nonregular(self):
        for value in (b'/usr/share/unlisted', b'/usr/share/stale-hash', b'/usr/share/stale-size'):
            self.assertEqual(self.api.check(value, self.fd()), -1)
        self.assertEqual(self.api.check(b'/usr/share/approved', -1), -1)
        fd = os.open('/usr/share', os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        self.assertEqual(self.api.check(b'/usr/share/approved', fd), -1)

    def test_actual_c_refuses_user_owned_identical_bytes(self):
        target = self.root/'owned'
        target.write_bytes(PUBLIC_FIXTURE.read_bytes())
        fd = os.open(target, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        self.assertEqual(self.api.check(b'/usr/share/approved', fd), -1)

    def test_actual_c_read_count_and_total_bytes_are_bounded(self):
        self.assertEqual(self.api.check_repeat(b'/usr/share/approved', self.fd()), 128)
        self.assertEqual(self.api.check_byte_budget(b'/usr/share/approved', self.fd()), -1)

    def test_exact_production_hasher_accepts_empty_regular_bytes_with_reviewed_owner_boundary(self):
        target = self.root/'empty'
        target.write_bytes(b'')
        fd = os.open(target, os.O_RDONLY)
        self.addCleanup(os.close, fd)
        self.assertEqual(self.api.check_empty(fd), 0)
        self.assertEqual(self.api.check(b'/usr/share/approved-empty', fd), -1, 'The ordinary real user-owned descriptor still refuses')

    def test_original_ancestry_route_cap_exec_and_failure_projection_remain(self):
        # This original source snapshot is only a before oracle; no host signal,
        # namespace, setup profile or source mutation occurs in these tests.
        before = (BASE/'tests/fixtures/alias-policy-before.c.txt').read_text()
        for start, end in (('static int rootnode(', '// Isolated Python'),
                           ('static int initially_unprivileged(', 'static const char bootstrap[]='),
                           (' // Relocate above', ' #undef ROUTE_FAIL_IF')):
            self.assertEqual(self.source[self.source.index(start):self.source.index(end, self.source.index(start))],
                             before[before.index(start):before.index(end, before.index(start))])
        self.assertIn('int target=rootfile(resolved);if(target<0)goto done;', self.source)
        self.assertIn('int checked=verify_import_alias_target(target,resolved)', self.source)
        self.assertIn('PYTHON_IMPORT_ALIAS_HASHES[index]', self.source)


if __name__ == '__main__':
    unittest.main()
