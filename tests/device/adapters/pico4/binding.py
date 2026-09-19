"""Pico extension of the canonical SH-004 Android adapter; no device auto-run."""
# SPDX-License-Identifier: Apache-2.0
from functools import wraps
import importlib.util
from pathlib import Path, PurePosixPath
import re

from execution_identity import file_digest

ROOT = Path(__file__).resolve().parents[4]
_spec = importlib.util.spec_from_file_location(
    'pico_bound_candidate_verifier', ROOT / 'android/vr/pico/ci/verify-pico-apk.py')
verifier = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verifier)


def _need(condition):
    if not condition:
        raise ValueError('OVT_PICO_BINDING_REJECTED')


def _private(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception:
            # Neither raw tool exceptions, artifact paths nor target selectors
            # become public adapter diagnostics, including direct callers.
            raise ValueError('OVT_PICO_BINDING_REJECTED') from None
    return call


def configure_parser(parser):
    # The same original candidate inputs, with named --apk because the runner
    # appends its action AFTER manifest-prefix options. No parallel schema.
    verifier.add_candidate_arguments(parser, native_binding=True)


def _inputs(args):
    from pico_candidate_identity import EVIDENCE_KEYS
    names = ('apk', 'identity_record', 'expected_inputs', 'build_evidence',
             'aapt', 'apksigner', *EVIDENCE_KEYS)
    _need(all(getattr(args, name, None) is not None for name in names))
    _need(args.source_revision and args.expected_version_code and
          args.expected_version_name and args.expected_signer_sha256 and
          args.minimum_version is not None and args.expected_artifact_sha256)
    frozen = {name: file_digest(getattr(args, name)) for name in names}
    # Parse paths using the original Shared bounded helpers. Full tier/identity
    # validation remains mandatory in verify_candidate, not reimplemented here.
    from schema.terminal_evidence import read_document, relative_file
    evidence, _ = read_document(args.build_evidence)
    for entry in evidence['receipts']:
        path = relative_file(args.build_evidence.parent, entry['path'])
        frozen['build_receipt:' + entry['tier']] = file_digest(path)
    return frozen


@_private
def create_adapter(args, base_class):
    _need(args.kind == 'pico')
    # Cleanup must still reach the original native cleanup if candidate files
    # disappeared or became invalid. It never emits an executionIdentity.
    cleanup_only = args.action == 'cleanup'
    if not cleanup_only:
        frozen = _inputs(args)
        args.require_identity = True
        candidate = verifier.verify_candidate(args)
        _need(_inputs(args) == frozen)
        _need(candidate['package'] == 'org.overte.pico' and
              candidate['identity']['artifactSha256'] == frozen['apk'])

    class PicoBoundAdapter(base_class):
        @_private
        def _candidate(self):
            _need(not cleanup_only)
            _need(_inputs(args) == frozen)
            current = verifier.verify_candidate(args)
            _need(current == candidate and _inputs(args) == frozen)
            return current

        @_private
        def _package_path(self, target):
            raw = self.adb.shell(target, 'pm', 'path', 'org.overte.pico')
            _need(isinstance(raw, str) and len(raw) <= 2048)
            lines = raw.splitlines()
            # One PackageManager path means monolithic only: never silently
            # discard a split APK or a warning/malformed extra line.
            _need(len(lines) == 1 and lines[0].startswith('package:'))
            path = lines[0][len('package:'):]
            _need(re.fullmatch(r'/data/app/[A-Za-z0-9_./+=~-]+/base[.]apk', path) is not None)
            parsed = PurePosixPath(path)
            _need(str(parsed) == path and '..' not in parsed.parts and '.' not in parsed.parts)
            # ADB joins remote argv. This constrained absolute path contains
            # no shell metacharacters, whitespace, substitutions or options.
            return path

        @_private
        def _installed_hash(self, target, path):
            raw = self.adb.shell(target, 'toybox', 'sha256sum', path)
            _need(isinstance(raw, str) and len(raw) <= 2200)
            match = re.fullmatch(r'([0-9a-f]{64})  ' + re.escape(path) + r'\n?', raw)
            _need(match is not None)
            return match.group(1)

        @_private
        def _installation(self, target):
            self.require(target)
            _need(self.adb.prop(target, 'ro.kernel.qemu') != '1')
            current = self._candidate()
            before = self._package_path(target)
            first = self._installed_hash(target, before)
            _need(self._package_path(target) == before)
            second = self._installed_hash(target, before)
            _need(self._package_path(target) == before)
            _need(first == second == current['sha256'])
            _need(_inputs(args) == frozen)
            return dict(schemaVersion=1, sourceRevision=current['identity']['sourceRevision'],
                        artifactSha256=first, installedCandidateVerified=True)

        @_private
        def capabilities(self, target=None):
            # One pinned candidate cannot establish a two-candidate upgrade.
            return [value for value in super().capabilities(target) if value != 'app.upgrade']

        @_private
        def discover(self):
            if not cleanup_only:
                self._candidate()
            return super().discover()

        @_private
        def describe(self, target):
            self._installation(target)
            description = super().describe(target)
            description['executionIdentity'] = self._installation(target)
            return description

        @_private
        def invoke(self, target, operation, values):
            _need(operation != 'app.upgrade')
            if operation == 'app.install':
                _need(type(values) is dict and set(values) == {'path'} and
                      isinstance(values['path'], str))
                path = Path(values['path'])
                _need(path.is_absolute() and not path.is_symlink() and
                      path.resolve() == args.apk.resolve() and file_digest(path) == frozen['apk'])
            # Bound suites begin with the candidate already provisioned: never
            # turn a foreign installation into an accepted initial describe.
            self._installation(target)
            try:
                result = super().invoke(target, operation, values)
            finally:
                self._installation(target)
            return result

        @_private
        def cleanup(self, target):
            # No receipt gate and no identity claim. Keep base teardown intact.
            return super().cleanup(target)

    return PicoBoundAdapter(args.kind)
