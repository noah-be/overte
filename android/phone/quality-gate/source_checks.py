# SPDX-License-Identifier: Apache-2.0
"""Source heuristics produce reviewable locations, never copy suspected secrets."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from core import digest, write_json

RULES = [
    ('private-key', 'FAIL', r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----', 'Remove the key and rotate it.'),
    ('credential-literal', 'FAIL', r'''(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token)\s*[:=]\s*["'][^"'\s]{8,}["']''', 'Review literal credentials; rotate actual secrets.'),
    ('private-ip', 'WARNING', r'\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|127(?:\.\d{1,3}){3})\b|\b(?:fc|fd)[0-9a-f]{2}:[0-9a-f:]+', 'Confirm a documented fixture or remove internal addressing.'),
    ('mac-address', 'WARNING', r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b', 'Remove device identity or document a synthetic value.'),
    ('local-path-user', 'WARNING', r'(?:/home/|/Users/|[A-Za-z]:\\Users\\)[^\s/"\'<>]+', 'Remove embedded local paths and account names.'),
    ('email', 'WARNING', r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', 'Distinguish required author notices from unintended personal data.'),
    ('internal-url', 'WARNING', r'(?i)https?://[^\s"\'<>]*(?:\.internal|\.local|localhost|staging|testserver|devserver)', 'Review endpoint reachability and intended release use.'),
    ('account-literal', 'WARNING', r'''(?i)(?:username|user_name|test_account)\s*[:=]\s*["'][^"']+["']''', 'Review test accounts and personal identifiers.'),
    ('sensitive-log', 'WARNING', r'(?i)(?:log|print|qDebug|console\.).*(?:password|token|credential|email|authorization)', 'Verify runtime redaction and absence from shipped logs.'),
]
CLEANUP = [
    ('cleanup-marker', 'WARNING', r'\b(?:TODO|FIXME|HACK|XXX)\b|(?i:quick.and.dirty|workaround|temporary fix)', 'Triage; ordinary maintenance comments do not block release.'),
    ('debug-production', 'WARNING', r'(?i)debug.?menu|qDebug\(|console\.log\(|\bmock\b|staging|test.account', 'Confirm unreachable test/debug behavior or remove it.'),
    ('security-bypass', 'FAIL', r'(?i)ignoreSslErrors\s*\(|setVerifyMode\s*\(\s*(?:QSslSocket::)?VerifyNone|verify\s*=\s*False|curl\s+[^\n]*(?:--insecure| -k\b)|checkServerTrusted[^\n]*\{\s*\}', 'Remove bypass or prove this exact file is not a release input.'),
    ('commented-code', 'WARNING', r'^\s*//\s*(?:if\s*\(|return\b|function\b|class\b)', 'Review commented-out implementation.'),
]


def texts(g):
    for rel in g.files:
        p = g.out / 'source-scope' / rel
        if not p.is_file():
            continue
        data = p.read_bytes()
        if b'\0' not in data:
            yield rel, data.decode('utf-8', errors='replace')


def scan_text(g, rel, text, rules):
    for rule, status, pattern, action in rules:
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(pattern, line):
                g.finding(rule, status, rel, 'Pattern requires review; matched value withheld.', action, n)


def materialize(g):
    dest = g.out / 'source-scope'
    dest.mkdir()
    rows = []
    for rel in g.files:
        p = g.root / rel
        if p.is_file() and not p.is_symlink():
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, target)
            sha = digest(target)
            g.source_hashes[rel] = sha
            rows.append(dict(path=rel, sha256=sha, basis='conservative Android source/build/resource closure'))
        else:
            g.fail('source-unscanned', 'Tracked scope entry is missing, a symlink or not a regular file.', rel)
    if not rows:
        raise ValueError('Android source scan scope is empty')
    write_json(g.out / 'source-scope.json', rows)
    return dest


def secrets(g):
    for rel, text in texts(g):
        scan_text(g, rel, text, RULES)
        for marker in g.config.get('private_markers', []):
            if not isinstance(marker, str) or len(marker) < 3:
                raise ValueError('Private markers must be strings of at least three characters')
            if marker.casefold() in text.casefold():
                g.finding('private-marker', 'FAIL', rel, 'Configured private identifier found; value withheld.',
                          'Remove personal data or document an exact false positive.')
    for rel in g.files:
        if re.search(r'(?i)screenshot|screen.?capture', rel):
            g.finding('screenshot-review', 'WARNING', rel, 'Potential personal visual content.', 'Inspect the image manually; OCR cannot prove absence of private data.')
    if g.tool('gitleaks', ('version',)):
        scope = g.out / 'source-scope'
        for mode, path, extra in [('dir', scope, []), ('git', g.root, ['--log-opts=HEAD'])]:
            # Full reachable history intentionally includes deleted/renamed Android inputs.
            report = g.out / ('gitleaks-' + mode + '.json')
            rc, _ = g.run('gitleaks-' + mode, ['gitleaks', mode, path, '--redact=100',
                          '--report-format=json', '--report-path', report, *extra], ok=(0, 1))
            if rc in (0, 1) and report.is_file():
                findings = json.loads(report.read_text())
                if not isinstance(findings, list) or (rc == 1 and not findings):
                    raise ValueError('Secret scanner report is inconsistent with its exit status')
                for row in findings:
                    commit = row.get('Commit') if mode == 'git' else None
                    if mode == 'git' and (not isinstance(commit, str) or not re.fullmatch(r'[0-9a-f]{40,64}', commit)):
                        raise ValueError('Historical secret finding lacks a valid commit identity')
                    relative = row.get('File', '')
                    relative = relative.removeprefix(str(scope) + '/').removeprefix(str(g.root) + '/')
                    g.finding('gitleaks-' + row['RuleID'], 'FAIL', relative,
                              'Secret detector finding; value redacted in private evidence.',
                              'Rotate genuine secrets and investigate history; waive only reviewed false positives.',
                              row.get('StartLine'), fdroid=True, suppressible=mode != 'git', history_commit=commit)
            elif rc in (0, 1):
                g.fail('gitleaks-report', 'Secret scan did not produce its required report.')
    shallow = subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'], cwd=g.root, text=True).strip()
    if shallow == 'true':
        g.fail('history-incomplete', 'Shallow history cannot establish complete reachable-history coverage.')


def evidence_privacy(g):
    """Postflight scan of generated diagnostics; never publish scanner values."""
    with g.category_scope('secrets'):
        _evidence_privacy(g)


def _evidence_privacy(g):
    dest = g.out / 'diagnostic-scan-input'
    dest.mkdir()
    candidates = list((g.out / 'logs').glob('*.log'))
    candidates += list(g.out.glob('error-*.txt'))
    for directory in g.out.glob('device-*'):
        if directory.is_dir():
            candidates += [p for p in directory.rglob('*') if p.is_file() and p.suffix in {'.log', '.json', '.jsonl', '.xml', '.txt'}]
    for index, p in enumerate(candidates):
        if p.stat().st_size > 1024 * 1024 * 1024:
            g.fail('diagnostic-too-large', 'A diagnostic exceeds privacy inspection budget.', p.relative_to(g.out).as_posix())
            continue
        # The scanner's redacted results are evidence, not a new secret source.
        if 'gitleaks' in p.name or 'scancode' in p.name:
            continue
        rel = 'diagnostics/' + p.relative_to(g.out).as_posix()
        scan_text(g, rel, p.read_text(errors='replace'), RULES)
        shutil.copyfile(p, dest / (str(index) + p.suffix))
    if g.tool('gitleaks', ('version',)):
        g.run('gitleaks-diagnostics', ['gitleaks', 'dir', dest, '--redact=100', '--report-format=json',
                                     '--report-path', g.out / 'gitleaks-diagnostics.json'])


def hygiene(g):
    # Repository-wide names only; no sibling platform content scanners.
    all_files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=g.root).decode().split('\0')
    for rel in filter(None, all_files):
        if re.search(r'(^|/)(?:build|\.idea|\.gradle|\.cxx)/|\.(?:log|bak|tmp|swp|dmp|hprof|jks|keystore)$|(^|/)core(?:\.\d+)?$|(^|/)local.properties$', rel):
            g.finding('tracked-development-file', 'WARNING', rel, 'Tracked development/build/private-file candidate.', 'Review and remove accidental files; preserve intentional fixtures.')
    for rel in g.files:
        p = g.root / rel
        if p.is_file() and p.stat().st_size > g.policy['large_file_bytes']:
            g.finding('large-source-file', 'WARNING', rel, 'Large tracked file.', 'Review size and necessity.')
    for rel, text in texts(g):
        if '/quality-gate/' not in rel:
            scan_text(g, rel, text, CLEANUP)
    # Check Git semantics, including nested rules and negations, rather than
    # searching for pattern substrings in one file.
    probes = ['android/phone/diagnostic.log', 'android/phone/heap.hprof',
              'android/phone/local.properties', 'android/phone/.gradle/cache.bin',
              'android/phone/apps/phoneInterface/build/intermediates/output.bin']
    checked = subprocess.run(['git', 'check-ignore', '--no-index', '-z', '--stdin'],
                             cwd=g.root, input='\0'.join(probes) + '\0',
                             text=True, capture_output=True)
    if checked.returncode not in (0, 1):
        g.fail('ignore-inspection', 'Git could not determine Android ignore coverage.')
    else:
        ignored = set(checked.stdout.split('\0'))
        for name in probes:
            if name not in ignored:
                g.finding('ignore-coverage', 'WARNING', name, 'Local Android output is not ignored.',
                          'Add a scoped ignore pattern; preserve intentionally tracked fixtures.')


def licenses(g):
    rows, branding = [], []
    for rel, text in texts(g):
        if re.search(r'(?i)license|copying|notice|copyright', Path(rel).name):
            rows.append(dict(path=rel, sha256=digest(g.root / rel), kind='notice'))
        if re.search(r'(?i)overte|high.?fidelity|vircadia', rel + '\n' + text):
            branding.append(dict(path=rel, basis='source reference; confirm packaging in artifact inventory'))
    for rel in g.files:
        if Path(rel).suffix.lower() in g.policy['media_extensions']:
            rows.append(dict(path=rel, sha256=digest(g.root / rel), kind='media', license='REQUIRES_RECONCILIATION'))
            if re.search(r'(?i)logo|icon|launcher|overte|hifi|vircadia', rel):
                branding.append(dict(path=rel, basis='brand-like resource name'))
    write_json(g.out / 'license-inventory.json', rows)
    write_json(g.out / 'branding.json', branding)
    (g.out / 'branding.md').write_text('# Android branding candidates\n\nInformational; no legal prohibition is inferred.\n\n' + '\n'.join('- `' + r['path'] + '`' for r in branding) + '\n')
    if not (g.root / 'LICENSE').is_file():
        g.fail('root-license', 'Root license is absent.', fdroid=True)
    if g.tool('scancode'):
        report = g.out / 'scancode.json'
        rc, _ = g.run('scancode', ['scancode', '--processes', str(g.config.get('scancode_processes', 2)),
                                 '--license', '--copyright', '--package', '--info',
                                 '--json-pp', report, g.out / 'source-scope'])
        if rc in (0, 1) and report.is_file():
            scanned = json.loads(report.read_text())
            files = scanned.get('files')
            if not isinstance(files, list) or not files:
                raise ValueError('License scan report has no file inventory')
            primary_paths = {r.get('path', '').removeprefix(str(g.out / 'source-scope') + '/').removeprefix('source-scope/')
                             for r in files if r.get('type') == 'file'}
            # ScanCode deliberately skips VCS metadata while walking directories.
            # Explicit single-file inputs retain it; never silently waive coverage.
            supplemental = []
            for index, relative in enumerate(sorted(set(g.source_hashes) - primary_paths)):
                if Path(relative).name not in {'.gitignore', '.gitattributes', '.gitmodules'}:
                    continue
                extra = g.out / f'scancode-vcs-{index}.json'
                status, _ = g.run(f'scancode-vcs-{index}', ['scancode', '--processes', '1',
                    '--license', '--copyright', '--package', '--info', '--json-pp', extra,
                    g.out / 'source-scope' / relative])
                if status not in (0, 1) or not extra.is_file():
                    continue
                records = json.loads(extra.read_text()).get('files', [])
                if (len(records) != 1 or records[0].get('type') != 'file'
                        or Path(records[0].get('path', '')).name != Path(relative).name):
                    g.fail('license-supplement-report', 'Single-file license report is inconsistent.', relative, True)
                    continue
                row = dict(records[0], path=relative)
                files.append(row)
                supplemental.append(dict(path=relative, report=extra.name, sha256=g.source_hashes[relative]))
            write_json(g.out / 'license-supplemental.json', supplemental)
            scanned_paths = set()
            for row in files:
                relative = row.get('path', '').removeprefix(str(g.out / 'source-scope') + '/').removeprefix('source-scope/')
                if row.get('type') == 'file':
                    scanned_paths.add(relative)
                if row.get('scan_errors'):
                    g.fail('license-scan-error', 'License scanner could not inspect a file.', relative, True)
                expr = row.get('detected_license_expression_spdx')
                if row.get('type') == 'file' and (not expr or 'LicenseRef' in expr):
                    g.finding('license-unresolved', 'WARNING', relative, 'No definitive SPDX license assignment.', 'Reconcile file with component/asset license and notices.', fdroid=True)
            if set(g.source_hashes) - scanned_paths:
                g.fail('license-scan-coverage', 'License report does not cover every materialized source file.', fdroid=True)
        else:
            g.fail('license-report', 'License scan report unavailable.', fdroid=True)
    (g.out / 'licenses.md').write_text('# License evidence\n\nRoot: Apache-2.0; third-party terms remain separate.\n\nSee license-inventory.json, scancode.json and the digest-bound manual reviews.\n\n' + '\n'.join('- `' + r['path'] + '` (' + r['kind'] + ')' for r in rows) + '\n')
    g.review('licenses')


def dependencies(g):
    rows = []
    for rel, text in texts(g):
        if not re.search(r'(?:gradle|conan|cmake|lock|Containerfile|\.sh$)', rel):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for value in re.findall(r'[\w.-]+:[\w.-]+:[\w.+-]+|[\w.-]+/[\w.+-]+(?:@[\w/.-]+)?#[a-f0-9]+', line):
                rows.append(dict(path=rel, line=n, coordinate=value))
            if re.search(r"(?<![\w.-])[A-Za-z_][\w.-]*:[A-Za-z_][\w.-]*:[^\s'\"]*(?:\+|SNAPSHOT)|\b(?:latest.release|latest.integration)\b", line):
                g.finding('dynamic-dependency', 'FAIL', rel, 'Mutable dependency version.', 'Pin and lock a reviewed immutable version.', n, True)
            if re.search(r'(?i)https?://|\b(?:curl|wget|FetchContent|ExternalProject|download)\b', line):
                rows.append(dict(path=rel, line=n, kind='repository-or-download'))
            if re.search(r'(?i)(?:url|repository|download).*http://', line):
                g.finding('insecure-download', 'WARNING', rel, 'Potential unencrypted dependency source.', 'Confirm executable path and enforce HTTPS with verified digests.', n, True)
    write_json(g.out / 'dependencies.json', rows)
    (g.out / 'dependencies.md').write_text('# Dependency declarations and acquisition sites\n\n' + '\n'.join(f"- `{r['path']}:{r['line']}`: {r.get('coordinate', r.get('kind'))}" for r in rows) + '\n')
    # Grype runs on resolved, merged SBOM after the build; declarations are not full resolution.
    g.review('dependencies')


def android_manifest(g, text, path, final=False):
    root = ET.fromstring(text)
    a = '{http://schemas.android.com/apk/res/android}'
    permissions = []
    for p in root:
        if p.tag.startswith('uses-permission'):
            name = p.get(a + 'name', '')
            reason = g.policy['permissions'].get(name)
            permissions.append(dict(name=name, origin=path, reason=reason or 'UNREVIEWED'))
            if not reason:
                g.finding('permission-unreviewed', 'FAIL' if final else 'WARNING', path, f'Unreviewed permission: {name}.', 'Identify the dependency/manifest origin and justify least privilege.')
    app = root.find('application')
    if app is None:
        g.fail('manifest-application', 'Application element missing.', path)
        return permissions
    for attr, bad in [('debuggable','true'), ('testOnly','true'), ('usesCleartextTraffic','true'), ('allowBackup','true')]:
        if app.get(a + attr) == bad:
            g.finding('manifest-' + attr, 'FAIL', path, f'Application sets {attr}={bad}.', 'Use a release-safe configuration.', fdroid=True)
    if app.get(a + 'allowBackup') is None:
        g.finding('backup-default', 'FAIL', path, 'Backup behavior is implicit.', 'Set and verify explicit backup/extraction rules.')
    if not app.get(a + 'networkSecurityConfig'):
        g.finding('network-policy-review', 'WARNING', path, 'No explicit Network Security Configuration.', 'Review target-SDK defaults and native Qt/OpenSSL networking separately.')
    components = []
    for c in app:
        if c.tag not in {'activity', 'activity-alias', 'service', 'receiver', 'provider'}:
            continue
        name = c.get(a + 'name', '')
        qualified = g.policy['application_id'] + name if name.startswith('.') else name
        exported = c.get(a + 'exported')
        filters = c.findall('intent-filter')
        components.append(dict(type=c.tag, name=name, exported=exported, permission=c.get(a+'permission'), intent_filters=[ET.tostring(f, encoding='unicode') for f in filters]))
        if (exported == 'true' and qualified not in g.policy['exported_components']) or (filters and exported is None):
            g.finding('exported-component', 'FAIL', path, f'Unreviewed exported component: {qualified}.', 'Restrict export or review permission protection and caller validation.')
        if c.tag == 'provider':
            g.finding('provider-review', 'WARNING', path, f'Review provider: {qualified}.', 'Verify authorities, grants, exported=false and narrow FileProvider paths.')
        for data in c.findall('.//data'):
            scheme = data.get(a + 'scheme')
            if scheme and scheme not in g.policy['deep_link_schemes']:
                g.finding('deep-link-review', 'WARNING', path, f'Unreviewed deep-link scheme: {scheme}.', 'Validate host/path constraints and untrusted URL handling.')
    write_json(g.out / ('components-final.json' if final else 'components-source.json'), components)
    return permissions


def android_resource(g, text, rel):
    root = ET.fromstring(text)
    for node in root.iter():
        if node.tag in {'root-path', 'external-path'} and node.get('path', '').strip() in {'', '.', '/'}:
            g.finding('fileprovider-broad-path', 'FAIL', rel, 'Broad file sharing path.',
                      'Restrict FileProvider to dedicated export directories.')
        if node.get('cleartextTrafficPermitted') == 'true':
            g.finding('cleartext-config', 'FAIL', rel, 'Cleartext explicitly enabled.',
                      'Remove or document a tightly scoped exception.')
        if node.tag == 'certificates' and node.get('src') == 'user':
            g.finding('user-certificate-trust', 'WARNING', rel, 'User CA trust enabled.',
                      'Confirm this is not a debug policy in the release.')


def android(g):
    path = 'android/phone/apps/phoneInterface/src/main/AndroidManifest.xml'
    permissions = android_manifest(g, (g.root / path).read_text(), path)
    write_json(g.out / 'permissions-source.json', permissions)
    (g.out / 'permissions.md').write_text('# Android permissions\n\n| Permission | Source | Reason |\n|---|---|---|\n' + '\n'.join(f"| {p['name']} | {p['origin']} | {p['reason']} |" for p in permissions) + '\n\nFinal manifest and merger provenance are checked after the clean build.\n')
    for rel, text in texts(g):
        if '/src/main/res/xml/' in rel:
            android_resource(g, text, rel)


def fdroid(g):
    blobs = []
    wrapper = 'android/common/gradle/wrapper/gradle-wrapper.jar'
    lock_path = g.root / 'android/phone/fdroid/manifests/toolchain-provisioning.lock.json'
    bindings = json.loads(lock_path.read_text()).get('gradle_bindings', {}) if lock_path.is_file() else {}
    for rel in g.files:
        p = g.root / rel
        if not p.is_file() or p.is_symlink():
            continue
        with p.open('rb') as stream:
            header = stream.read(4)
        if p.suffix.lower() in g.policy['binary_extensions'] or header.startswith((b'\x7fELF', b'PK\x03\x04', b'\xca\xfe\xba\xbe', b'MZ')):
            sha = digest(p)
            row = dict(path=rel, sha256=sha, origin='REVIEW_REQUIRED', necessity='REVIEW_REQUIRED')
            if rel == wrapper:
                if bindings.get(rel) != sha:
                    g.fail('wrapper-integrity', 'Gradle wrapper differs from the reviewed toolchain binding.', rel, True)
                else:
                    row.update(origin='toolchain-provisioning.lock.json:gradle_bindings',
                               necessity='Gradle command-line bootstrap; not application runtime',
                               qualification='Integrity bound; F-Droid bootstrap policy review still required')
            blobs.append(row)
            g.finding('binary-origin', 'WARNING', rel, 'Prebuilt/archive input requires provenance review.', 'Identify source, build recipe, license and actual Android usage.', fdroid=True)
    write_json(g.out / 'binary-origins.json', blobs)
    for rel, text in texts(g):
        if '/quality-gate/' in rel:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if re.search(r'(?i)com\.google\.android\.gms|com\.google\.firebase|crashlytics|appsflyer|adjust\.sdk|facebook\.sdk|flurry|unityads', line):
                g.finding('proprietary-or-tracker-reference', 'WARNING', rel, 'Potential SDK/tracker reference in conservative source scope.', 'Establish Android runtime reachability; packaged matches block release.', n, True)
    g.review('fdroid')
