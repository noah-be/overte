# SPDX-License-Identifier: Apache-2.0
"""Isolated source build, resolved artifact checks, and existing physical E2E suites."""
import ast
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from core import digest, write_json
from evidence import role_paths, validate_receipt, write_receipt
from source_checks import RULES, android_manifest, scan_text, texts
from test_store import verify_inventory, stage_runtimes


def static(g):
    shell = []
    for rel, text in texts(g):
        try:
            if rel.endswith('.py'):
                ast.parse(text, filename=rel)
            elif rel.endswith(('.xml', '.qrc')):
                ET.fromstring(text)
            elif rel.endswith('.sh'):
                shell.append(rel)
        except (SyntaxError, ET.ParseError):
            g.finding('source-syntax', 'WARNING', rel, 'Syntax needs review in conservative source scope.', 'Confirm Android relevance and repair malformed input.')
    if g.tool('shellcheck'):
        for start in range(0, len(shell), 50):
            rc, log = g.run(f'shellcheck-{start}', ['shellcheck', '--severity=error', '--format=json', *shell[start:start+50]], ok=(0, 1))
            if rc in (0, 1):
                rows = json.loads(log.read_text())
                for r in rows:
                    g.finding('shellcheck-SC' + str(r['code']), 'FAIL', r['file'],
                              r['message'], 'Repair the shell error or document an exact exception.', r['line'])
    # Native compile database and AGP model do not exist until build stage.
    g.finding('analysis-deferred', 'WARNING', '', 'Android Lint and native analysis execute after Clean Build.', 'A full gate requires their later successful completion.', suppressible=False)


def required_path(g, key):
    value = g.config.get(key)
    if not value or not Path(value).is_absolute() or not Path(value).exists():
        raise ValueError('Missing absolute existing path for ' + key)
    return Path(value).resolve()


def container_command(g, attempt):
    sdk = required_path(g, 'sdk_root')
    store = required_path(g, 'source_store')
    image = g.config.get('builder_image', '') or ''
    if not re.fullmatch(r'(?:[\w./:-]+@)?sha256:[a-f0-9]{64}', image):
        raise ValueError('builder_image must be an immutable local image ID or registry digest')
    # Pass only explicitly declared inputs; no host home, credentials, or Conan cache.
    command = ['podman', 'run', '--rm', '--pull=never', '--network=none', '--read-only',
               '--security-opt=label=disable', '--tmpfs=/tmp:rw,size=4g', '--tmpfs=/root:rw,size=128m',
               '--volume', f'{attempt}:/attempt:rw', '--volume', f'{store}:/source-store:ro',
               '--volume', f'{sdk}:/opt/android-sdk:ro']
    env = dict(OVERTE_ATTEMPT_ROOT='/attempt', OVERTE_SOURCE_CLOSURE_STORE='/source-store',
               ANDROID_SDK_ROOT='/opt/android-sdk', ANDROID_NDK_HOME='/opt/android-sdk/ndk/27.3.13750724',
               JAVA_HOME='/usr/lib/jvm/java-17-openjdk-amd64', OVERTE_SOURCE_COMMIT=g.commit,
               GATE_VERSION_CODE=str(g.config['version_code']), GATE_VERSION_NAME=g.config['version_name'],
               PATH='/opt/sh001/conan/bin:/usr/lib/jvm/java-17-openjdk-amd64/bin:/opt/android-sdk/build-tools/36.0.0:/opt/android-sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')
    for k, v in env.items():
        command += ['--env', f'{k}={v}']
    return [*command, image]


def build(g):
    code, previous, name = (g.config.get(k) for k in ('version_code', 'previous_version_code', 'version_name'))
    if (type(code) is not int or type(previous) is not int or not 0 <= previous < code <= 2147483647
            or not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._+-]{0,99}', name)):
        raise ValueError('Supply explicit increasing version_code, previous_version_code and portable version_name')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=g.root):
        raise ValueError('Clean build requires all intended changes committed and a clean checkout')
    gradle_store = required_path(g, 'gradle_store')
    if not g.tool('podman'):
        return
    lock = json.loads((g.root / 'android/phone/fdroid/manifests/toolchain-provisioning.lock.json').read_text())
    bindings = dict(lock['android_sdk_bindings'])
    sdk = required_path(g, 'sdk_root')
    for rel, sha in bindings.items():
        if digest(sdk / rel) != sha:
            raise ValueError('Android SDK differs from toolchain lock')
    for rel, sha in lock['gradle_bindings'].items():
        if '/' in rel and digest(g.root / rel) != sha:
            raise ValueError('Gradle input differs from toolchain lock')
    if digest(g.root / lock['build_image']['containerfile']) != lock['build_image']['containerfile_sha256']:
        raise ValueError('Builder Containerfile differs from toolchain lock')
    rc, log = g.run('builder-identity', ['podman', 'image', 'inspect', g.config.get('builder_image') or ''], env=podman_env(g))
    if rc != 0:
        return
    image = json.loads(log.read_text())[0]
    if image['Id'].removeprefix('sha256:') != lock['build_image']['image_id'].removeprefix('sha256:'):
        raise ValueError('Builder image differs from the existing reviewed toolchain lock')
    g.attempt = g.out / 'attempt'
    g.attempt.mkdir()
    source = g.attempt / 'source'
    source.mkdir()
    archive = g.attempt / 'source.tar'
    rc, _ = g.run('git-archive', ['git', 'archive', '--format=tar', '-o', archive, g.commit])
    if rc != 0:
        return
    # git archive has no local untracked files; reject special/link entries escaping the archive.
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or member.isdev() or member.isfifo():
                raise ValueError('Unsafe source archive member')
        tf.extractall(source, filter='data')
    if digest(gradle_store / 'ARTIFACT_SHA256SUMS') != g.config.get('gradle_store_manifest_sha256'):
        raise ValueError('Gradle store inventory differs from independently frozen configuration')
    for rel in ('gradle.properties', 'init.gradle', 'init.gradle.kts', 'init.d'):
        if (gradle_store / rel).exists():
            raise ValueError('Gradle store contains undeclared initialization or user properties')
    if any(p.is_symlink() for p in gradle_store.rglob('*')):
        raise ValueError('Gradle acquisition store must not contain links outside its verified inventory')
    verify_inventory(gradle_store)
    shutil.copytree(gradle_store, g.attempt / 'gradle-home', symlinks=False)
    for check in ('COMPLETE', 'ARTIFACT_SHA256SUMS'):
        rc, _ = g.run('gradle-store-' + check, ['sha256sum', '-c', check], cwd=g.attempt / 'gradle-home')
        if rc != 0:
            return
    base = container_command(g, g.attempt)
    stage_runtimes(g.attempt / 'gradle-home', g.attempt / 'robolectric-sdk')
    rc, _ = g.run('offline-test-dependency-preflight', [*base, '/usr/bin/env',
        'GRADLE_USER_HOME=/attempt/gradle-home', '/attempt/source/android/common/gradlew',
        '--offline', '--no-daemon', '-p', '/attempt/source/android/phone/quality-gate/gradle-tests',
        'resolveGateTestInputs'], env=podman_env(g))
    if rc != 0:
        return
    rc, _ = g.run('source-release-build', [*base, '/bin/sh', '/attempt/source/android/phone/quality-gate/container-build.sh'],
                  timeout=g.config.get('build_timeout_seconds', 172800), env=podman_env(g))
    if rc != 0:
        return
    module = source / 'android/phone/apps/phoneInterface'
    apk = module / 'build/outputs/apk/release/phoneInterface-release-unsigned.apk'
    if not apk.is_file():
        raise ValueError('Clean release build did not produce the expected unsigned APK')
    g.artifact = apk
    analyze_build(g, base, module)
    write_receipt(g)


def podman_env(g):
    # Rootless Podman needs its user's existing image store/runtime; container remains clean.
    env = dict(g.env)
    for key in ('HOME', 'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def analyze_build(g, base, module):
    with g.category_scope('static'):
        _analyze_build(g, base, module)


def _analyze_build(g, base, module):
    gradle = ['/attempt/source/android/common/gradlew', '--offline', '--no-daemon',
              '--settings-file', '/attempt/source/android/phone/settings.gradle', '-p', '/attempt/source/android/phone',
              '--init-script', '/attempt/source/android/phone/quality-gate/release.init.gradle',
              '-PVERSION_CODE=' + str(g.config['version_code']), '-PRELEASE_NUMBER=' + g.config['version_name'],
              '-PRELEASE_TYPE=RELEASE', '-PSTABLE_BUILD=1', '--no-build-cache',
              '-Pandroid.aapt2FromMavenOverride=/opt/android-sdk/build-tools/36.0.0/aapt2']
    # /usr/bin/env applies these only inside the container.
    g.run('android-lint-and-jvm', [*base, '/usr/bin/env', 'OVERTE_FDROID_CONAN_DIR=/attempt/target',
          'GRADLE_USER_HOME=/attempt/gradle-home', *gradle, ':phoneInterface:lintRelease',
          ':phoneInterface:testReleaseUnitTest'], env=podman_env(g))
    databases = [p for p in module.glob('.cxx/**/compile_commands.json')
                 if any(part in {'Release', 'RelWithDebInfo'} for part in p.parts)]
    if not databases:
        g.fail('compile-database', 'No Release compile database; native Android scope is unproven.')
    else:
        merged = []
        for p in databases:
            for row in json.loads(p.read_text()):
                # Rewrite container paths only for host cppcheck. Preserve Android compiler defines.
                for key in ('directory', 'file', 'command'):
                    if key in row:
                        row[key] = row[key].replace('/attempt/', str(g.attempt) + '/')
                        row[key] = row[key].replace('/opt/android-sdk/', str(required_path(g, 'sdk_root')) + '/')
                if 'arguments' in row:
                    row['arguments'] = [x.replace('/attempt/', str(g.attempt) + '/').replace('/opt/android-sdk/', str(required_path(g, 'sdk_root')) + '/') for x in row['arguments']]
                merged.append(row)
        db = g.out / 'compile_commands.json'
        write_json(db, merged)
        write_json(g.out / 'compiled-android-sources.json', sorted(set(row['file'] for row in merged)))
        archived_root = g.attempt / 'source'
        for filename in sorted(set(row['file'] for row in merged)):
            file = Path(filename)
            if not file.is_absolute():
                g.fail('compile-source-relative', 'Compiler database contains a relative file; scope cannot be reconciled.')
                continue
            if archived_root in file.parents:
                rel = file.relative_to(archived_root).as_posix()
                # Generated sources are captured with build evidence, not claimed as tracked source.
                if (g.root / rel).is_file() and not g.in_scope(rel):
                    g.fail('source-scope-gap', 'An actual Android translation unit is outside the source scan closure.', rel)
        if not merged:
            g.fail('compile-database-empty', 'Native compiler database has no translation units.')
        if g.tool('cppcheck'):
            rc, log = g.run('cppcheck-android', ['cppcheck', '--project=' + str(db), '--enable=warning,performance,portability',
                                              '--quiet', '--xml', '--xml-version=2'])
            if rc == 0:
                report = ET.fromstring(log.read_text())
                for error in report.findall('.//error'):
                    loc = error.find('location')
                    rel = loc.get('file', '') if loc is not None else ''
                    rel = rel.removeprefix(str(g.attempt / 'source') + '/')
                    g.finding('cppcheck-' + error.get('id', 'unknown'),
                              'FAIL' if error.get('severity') == 'error' else 'WARNING', rel,
                              error.get('msg', 'Native analysis finding.'),
                              'Review in the actual Android compiler configuration.',
                              int(loc.get('line', '0')) if loc is not None else None)


def load_artifact(g):
    return validate_receipt(g)


def archive_members(g, z):
    infos = z.infolist()
    if len(infos) > g.policy['max_archive_members'] or sum(i.file_size for i in infos) > g.policy['max_archive_bytes']:
        raise ValueError('Archive exceeds extraction budget')
    names = set()
    for i in infos:
        p = PurePosixPath(i.filename)
        mode = stat.S_IFMT(i.external_attr >> 16)
        if (p.is_absolute() or '..' in p.parts or '\\' in i.filename or p.as_posix() in names
                or not p.parts or i.flag_bits & 1
                or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                or i.file_size > g.policy['max_archive_member_bytes']):
            raise ValueError('Unsafe, encrypted or duplicate archive member')
        names.add(p.as_posix())
    return infos


def unpack(g, archive, dest):
    dest.mkdir()
    inventory = []
    with zipfile.ZipFile(archive) as z:
        for i in archive_members(g, z):
            if i.is_dir():
                continue
            target = dest / i.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(i) as inp, target.open('wb') as out:
                shutil.copyfileobj(inp, out)
            inventory.append(dict(path=i.filename, size=i.file_size, compressed=i.compress_size, sha256=digest(target)))
    return inventory


def inspect_payload(g, dest, rows, prefix=''):
    for row in rows:
        rel = prefix + row['path']
        if re.search(r'(?i)\.map$|\.log$|\.bak$|\.jks$|\.keystore$|(?:^|/)(?:testdata|debug|screenshots)/|overte_e2e_probe|e2e_scene', rel):
            g.finding('unexpected-payload', 'FAIL', rel, 'Development/private payload in release.', 'Remove it from release packaging.', fdroid=True, suppressible=False)
        if row['size'] > g.policy['large_file_bytes']:
            g.finding('large-payload', 'WARNING', rel, 'Large packaged member.', 'Review compression, necessity, and duplicate resources.')
        data = (dest / row['path']).read_bytes()
        # Includes printable ASCII and UTF-16 strings in DEX/ELF/resources, not only text assets.
        text = data.decode('utf-8', errors='replace')
        scan_text(g, rel, text, RULES)
        if b'\x00' in data:
            scan_text(g, rel, data.decode('utf-16-le', errors='replace'), RULES)
        if re.search(rb'com[/\.]google[/\.]android[/\.]gms|com[/\.]google[/\.]firebase|com[/\.]appsflyer|com[/\.]flurry', data):
            g.finding('packaged-sdk', 'FAIL', rel, 'Potential non-free/tracking SDK in shipped bytes.', 'Verify and remove prohibited runtime components.', fdroid=True, suppressible=False)


def artifact(g):
    apk = load_artifact(g)
    if apk.suffix != '.apk':
        raise ValueError('APK required for final manifest/device checks; AAB inventory is supplemental')
    dest = g.out / 'apk-unpacked'
    rows = unpack(g, apk, dest)
    write_json(g.out / 'apk-files.json', rows)
    inspect_payload(g, dest, rows)
    write_json(g.out / 'native-libraries.json', [r for r in rows if r['path'].endswith('.so')])
    if g.tool('gitleaks', ('version',)):
        g.run('gitleaks-artifact', ['gitleaks', 'dir', dest, '--redact=100', '--report-format=json',
                                  '--report-path', g.out / 'gitleaks-artifact.json'])
    sdk = required_path(g, 'sdk_root')
    env = dict(g.env, ANDROID_SDK_ROOT=str(sdk), ANDROID_HOME=str(sdk))
    g.run('existing-phone-apk-gate', ['bash', g.root / 'android/phone/tests/check-phone-apk-16k.sh', apk], env=env)
    if g.tool('apkanalyzer'):
        rc, log = g.run('packaged-manifest', ['apkanalyzer', 'manifest', 'print', apk])
        if rc == 0:
            permissions = android_manifest(g, log.read_text(), 'APK/AndroidManifest.xml', final=True)
            write_json(g.out / 'permissions-final.json', permissions)
            with (g.out / 'permissions.md').open('a') as stream:
                stream.write('\n## Packaged permissions\n\n')
                stream.write('\n'.join('- ' + p['name'] + ': ' + p['reason'] for p in permissions) + '\n')
        for field, expected in [('application-id', g.policy['application_id']), ('version-code', g.config.get('version_code')),
                                ('version-name', g.config.get('version_name')), ('min-sdk', g.policy['min_sdk']),
                                ('debuggable', 'false')]:
            rc, log = g.run('apk-' + field, ['apkanalyzer', 'manifest', field, apk])
            if rc == 0 and log.read_text().strip() != str(expected):
                g.fail('apk-' + field, 'Packaged value differs from release policy.', 'APK/AndroidManifest.xml')
        rc, log = g.run('apk-target-sdk', ['apkanalyzer', 'manifest', 'target-sdk', apk])
        if rc == 0 and int(log.read_text().strip()) < g.policy['target_sdk_minimum']:
            g.fail('apk-target-sdk', 'Target SDK is below reviewed policy floor.')
    # Unsigned source-built APK is expected. Do not sign or generate keys here.
    signer = sdk / 'build-tools/36.0.0/apksigner'
    rc, log = g.run('apk-certificates', [signer, 'verify', '--verbose', '--print-certs', apk], required=False)
    if rc == 0:
        g.finding('signed-input', 'WARNING', '', 'APK is signed; certificate details retained privately.', 'Verify expected certificate and upgrade lineage.')
    elif rc is not None and not re.search(r'Missing META-INF/MANIFEST.MF|No JAR signatures', log.read_text(errors='replace'), re.I):
        g.fail('signature-inspection', 'Signature inspection failed without recognized unsigned-APK evidence.')
    if g.tool('fdroid'):
        fdroid_dir = g.out / 'fdroid-scan'
        fdroid_dir.mkdir()
        (fdroid_dir / 'config.yml').write_text('sdk_path: ' + json.dumps(str(sdk)) + '\n')
        rc, _ = g.run('fdroid-binary', ['fdroid', 'scanner', '--exit-code', str(apk)], cwd=fdroid_dir, env=env)
        if rc != 0:
            g.fail('fdroid-binary-rejected', 'F-Droid binary scanner did not pass; inspect fdroid-binary.log.', fdroid=True)
    if g.attempt:
        aabs = role_paths(g, 'aab')
        for n, aab in enumerate(aabs):
            aab_dest = g.out / f'aab-unpacked-{n}'
            aab_rows = unpack(g, aab, aab_dest)
            write_json(g.out / f'aab-files-{n}.json', aab_rows)
            inspect_payload(g, aab_dest, aab_rows, prefix='AAB/')
            if g.tool('gitleaks', ('version',)):
                g.run(f'gitleaks-aab-{n}', ['gitleaks', 'dir', aab_dest, '--redact=100',
                      '--report-format=json', '--report-path', g.out / f'gitleaks-aab-{n}.json'])
            g.run(f'existing-aab-contents-{n}', [sys.executable, g.root / 'android/phone/tests/check-phone-apk-contents.py', aab])
        if not aabs:
            g.fail('aab-absent', 'Clean build did not produce the requested supplemental AAB.')
        merger = role_paths(g, 'merger')
        records = []
        origin_texts = []
        for p in merger:
            if p.is_file():
                target = g.out / ('manifest-origin-' + str(len(records)) + '.txt')
                shutil.copyfile(p, target)
                records.append(target.name)
                origin_texts.append(p.read_text(errors='replace'))
        write_json(g.out / 'permission-origin-reports.json', records)
        if not records:
            g.fail('permission-origin', 'No manifest merger provenance for transitive permission attribution.')
        final_permissions = g.out / 'permissions-final.json'
        if final_permissions.is_file():
            permissions = json.loads(final_permissions.read_text())
            for permission in permissions:
                origins = []
                for text in origin_texts:
                    blocks = re.split(r'\n\s*\n', text)
                    origins.extend(block.strip() for block in blocks if permission['name'] in block)
                permission['merger_provenance'] = origins
                if not origins:
                    g.fail('permission-origin-unresolved', 'No merger attribution for ' + permission['name'])
            write_json(final_permissions, permissions)
            with (g.out / 'permissions.md').open('a') as stream:
                stream.write('\n## Manifest merger provenance\n\n')
                for permission in permissions:
                    stream.write('### ' + permission['name'] + '\n\n' + permission['reason'] + '\n\n')
                    stream.write('```text\n' + '\n\n'.join(permission['merger_provenance']) + '\n```\n\n')
        resolved_sbom(g, dest)
    else:
        g.fail('resolved-dependencies', 'Build graph is unavailable for artifact dependency reconciliation.')
    g.review('artifact', artifact=True)


def resolved_sbom(g, dest):
    with g.category_scope('dependencies'):
        _resolved_sbom(g, dest)


def _resolved_sbom(g, dest):
    components = []
    source_built = set()
    for role in ('bootstrap', 'host-tools', 'target'):
        graph = json.loads((g.attempt / (role + '-result.json')).read_text())
        nodes = graph['graph']['nodes']
        if not isinstance(nodes, dict) or not nodes:
            raise ValueError('Conan graph has no dependency evidence')
        for node in nodes.values():
            ref = node.get('ref')
            if not ref or node.get('recipe') == 'Consumer':
                continue
            nv = ref.split('@')[0].split('#')[0]
            name, version = nv.split('/', 1)
            components.append(dict(type='library', name=name, version=version,
                                   purl=f'pkg:conan/{name}@{version}',
                                   properties=[dict(name='overte:role', value=role), dict(name='overte:conan-ref', value=ref)]))
            identity = (ref, node.get('package_id'), node.get('prev'))
            if node.get('binary') == 'Build':
                source_built.add(identity)
            if node.get('binary') not in ('Build', 'Skip') and identity not in source_built:
                g.fail('conan-prebuilt', 'Dependency lacks source-build evidence in the fresh graph.', role + '/' + name, True)
    gradle = json.loads((g.attempt / 'gradle-runtime.json').read_text())
    if not isinstance(gradle, list) or not gradle:
        raise ValueError('Resolved Gradle runtime inventory is empty')
    for r in gradle:
        component = dict(type='library', name=r['name'], hashes=[dict(alg='SHA-256', content=r['sha256'])])
        if r.get('kind') == 'maven' and r.get('group') and r.get('version'):
            component.update(group=r['group'], version=r['version'], purl=f"pkg:maven/{r['group']}/{r['name']}@{r['version']}")
        else:
            component['properties'] = [dict(name='overte:origin', value='local-source-built-jar-review-required')]
            g.finding('local-runtime-license', 'WARNING', r['file'], 'Local runtime JAR requires source/license reconciliation.',
                      'Match its hash to the source-built Qt package and notices.', fdroid=True)
        components.append(component)
    if g.tool('syft'):
        rc, _ = g.run('syft-payload', ['syft', 'scan', 'dir:' + str(dest), '-o', 'cyclonedx-json=' + str(g.out / 'payload.cdx.json')])
        if rc == 0:
            payload_bom = json.loads((g.out / 'payload.cdx.json').read_text())
            if payload_bom.get('bomFormat') != 'CycloneDX' or not isinstance(payload_bom.get('components'), list):
                raise ValueError('Payload scanner did not produce a valid component inventory')
            components += payload_bom['components']
    sbom = g.out / 'resolved.cdx.json'
    write_json(sbom, dict(bomFormat='CycloneDX', specVersion='1.6', version=1, components=components))
    if not components:
        g.fail('empty-sbom', 'Resolved dependency inventory is empty.', fdroid=True)
    if g.tool('grype', ('version',)):
        g.run('grype-resolved', ['grype', 'sbom:' + str(sbom), '--fail-on', 'high', '-o', 'json', '--file', g.out / 'vulnerabilities.json'])


def e2e(g, group):
    if g.config.get('device_authorized') is not True:
        raise ValueError('Dedicated Phone device use must be explicitly enabled in private configuration')
    adapter = required_path(g, 'adapter_manifest')
    manifest = json.loads(adapter.read_text())
    if manifest.get('id') not in {'android-phone-adb', 'appium-android'}:
        raise ValueError('A real Phone adapter is required; mock and Pico adapters are forbidden')
    command = manifest.get('command')
    wrapper = 'adapter.py' if manifest['id'] == 'android-phone-adb' else 'appium_adapter.py'
    expected_wrapper = g.root / 'tests/device/adapters/android-phone' / wrapper
    if (not isinstance(command, list) or not command or not isinstance(command[0], str)
            or (adapter.parent / command[0]).resolve() != expected_wrapper.resolve()):
        raise ValueError('Manifest must directly select the repository-owned bound Phone adapter')
    candidate = required_path(g, 'candidate_apk')
    expected = g.config.get('candidate_sha256')
    if digest(candidate) != expected:
        raise ValueError('Installed candidate digest differs from independent expectation')
    # Byte identity between the signed device candidate and unsigned clean build:
    apk = load_artifact(g)
    def payload(path):
        with zipfile.ZipFile(path) as z:
            result = {}
            for i in archive_members(g, z):
                if i.is_dir() or re.fullmatch(r'META-INF/(?:MANIFEST.MF|[^/]+\.(?:SF|RSA|DSA|EC))', i.filename, re.I):
                    continue
                h = hashlib.sha256()
                with z.open(i) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        h.update(chunk)
                result[i.filename] = h.hexdigest()
            return result
    if payload(candidate) != payload(apk):
        raise ValueError('Device candidate payload differs from the clean release APK (signatures excepted)')
    signer = required_path(g, 'sdk_root') / 'build-tools/36.0.0/apksigner'
    rc, _ = g.run('candidate-signature-' + group, [signer, 'verify', '--verbose', '--print-certs', candidate])
    if rc != 0:
        return
    if group == 'long':
        seconds = g.config.get('long_seconds', 14400)
        if type(seconds) is not int or seconds < g.policy['long_seconds_minimum']:
            raise ValueError('Long-running duration is below policy minimum')
        suites = [s for _ in range(math.ceil(seconds / 7200)) for s in g.policy['long_suites']]
    else:
        suites = g.policy[group + '_suites']
    soak_seconds = 0
    for index, suite in enumerate(suites):
        output = g.out / f'device-{group}-{index:03d}-{suite}'
        env = dict(g.env, OVERTE_DEVICE_LOCK_ROOT=os.environ.get('OVERTE_DEVICE_LOCK_ROOT', tempfile.gettempdir()))
        allowed = {'OVERTE_APPIUM_TARGETS', 'OVERTE_E2E_SCENE_URL', 'OVERTE_E2E_DOMAIN_URL',
                   'OVERTE_E2E_DOMAIN_ID', 'OVERTE_E2E_DOMAIN_HOST', 'OVERTE_E2E_DOMAIN_MARKERS_JSON',
                   'OVERTE_E2E_DOMAIN_CONTROL_URL', 'OVERTE_E2E_DOMAIN_CONTROL_TOKEN', 'OVERTE_ANDROID_AAPT',
                   'OVERTE_DEVICE_LOCK_ROOT', 'ADB_VENDOR_KEYS'}
        for key, value in g.config.get('device_environment', {}).items():
            if key not in allowed or not isinstance(value, str):
                raise ValueError('Unsupported device environment entry')
            env[key] = value
        if group == 'long':
            env.update(OVERTE_DEVICE_IDLE_SECONDS='7200', OVERTE_DEVICE_SAMPLE_SECONDS='30')
        rc, _ = g.run(f'e2e-{group}-{index:03d}-{suite}', [sys.executable, g.root / 'tests/device/run.py',
                 '--adapter-manifest', adapter, '--catalog', g.root / 'tests/device/catalog.json',
                 '--suite', suite, '--tablet-policy', g.root / 'tests/device/policies/android-phone-flat-touch.json',
                 '--output-dir', output, '--require-complete', '--candidate-artifact', candidate,
                 '--expected-source-sha', g.commit, '--expected-artifact-sha256', expected], env=env, timeout=8500)
        if rc != 0:
            break  # No retry masks a product failure or infrastructure skip.
        summary = json.loads((output / 'summary.json').read_text())
        run = json.loads((output / 'run-manifest.json').read_text())
        identity = json.loads((output / 'result-identity.json').read_text())
        if (identity.get('sourceRevision') != g.commit or identity.get('artifactSha256') != expected
                or any(identity.get(key) != digest(output / filename) for key, filename in
                       [('runSha256', 'run-manifest.json'), ('summarySha256', 'summary.json'), ('junitSha256', 'junit.xml')])):
            g.fail('e2e-identity', 'Suite evidence lacks its installed-candidate identity binding.')
            break
        if (summary.get('status') != 'passed' or not summary.get('results')
                or any(r.get('status') != 'passed' for r in summary['results'])
                or run.get('physical') is not True or run.get('platform') != 'android'
                or run.get('suite') != suite or run.get('adapter') != manifest['id']
                or not run.get('requireComplete')):
            g.fail('e2e-incomplete', f'{suite}: incomplete or non-physical execution.')
            break
        if suite == 'stability':
            if 'telemetry.snapshot' not in run.get('capabilities', []):
                g.fail('telemetry-unavailable', 'Soak lacks RAM/battery/thermal evidence.')
            soak_seconds += analyze_telemetry(g, output)
    if group == 'long' and soak_seconds < seconds:
        g.fail('soak-duration', 'Recorded successful soak duration is below the requested minimum.')
    g.review(group, artifact=True)


def analyze_telemetry(g, output):
    p = output / 'modules/idle-soak/telemetry.jsonl'
    if not p.is_file():
        g.fail('telemetry-missing', 'No recorded soak telemetry.')
        return 0
    metrics = json.loads((p.parent / 'metrics.json').read_text())
    if metrics.get('durationSeconds') != 7200:
        g.fail('telemetry-duration', 'Idle-soak metrics do not prove the requested two-hour session.')
        return 0
    samples = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
    fields = {'memoryPssKb': (1, 2 ** 63 - 1), 'memoryRssKb': (1, 2 ** 63 - 1),
              'batteryLevel': (0, 100), 'batteryTemperatureDeciC': (-500, 2000),
              'thermalStatus': (0, 6)}
    if len(samples) < 3 or any(not isinstance(s, dict) or any(
            type(s.get(key)) is not int or not low <= s[key] <= high
            for key, (low, high) in fields.items()) for s in samples):
        g.fail('telemetry-incomplete', 'Missing or invalid memory, battery or thermal samples.')
        return 0
    elapsed = [sample.get('elapsedSeconds') for sample in samples]
    if (any(type(value) is not int for value in elapsed) or elapsed != sorted(set(elapsed))
            or not 0 <= elapsed[0] <= 60 or not 7140 <= elapsed[-1] <= 7260
            or any(b - a > 90 for a, b in zip(elapsed, elapsed[1:]))
            or type(metrics.get('samples')) is not int or len(samples) != metrics['samples']):
        g.fail('telemetry-coverage', 'Soak samples do not cover the recorded interval.')
        return 0
    if any(s['thermalStatus'] > 5 for s in samples):
        g.fail('telemetry-thermal', 'Recorded thermal status exceeded the soak safety limit.')
        return 0
    growth = samples[-1]['memoryPssKb'] - samples[0]['memoryPssKb']
    write_json(output / 'memory-trend.json', dict(samples=len(samples), pss_growth_kb=growth,
               max_pss_kb=max(s['memoryPssKb'] for s in samples),
               max_temperature_decic=max(s['batteryTemperatureDeciC'] for s in samples)))
    if growth > max(262144, samples[0]['memoryPssKb'] * 0.25):
        g.finding('memory-growth', 'WARNING', '', 'Sustained run ended with significant PSS growth.', 'Inspect time series and profile allocations; growth alone is not proof of a leak.')
    return 7200
