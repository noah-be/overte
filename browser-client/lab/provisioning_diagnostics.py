# SPDX-License-Identifier: Apache-2.0
"""Fixed-label diagnostics for the owned local domain provisioning endpoint."""
import hashlib
import json
import os
from pathlib import Path
import stat
import urllib.error
import urllib.request
from guest_permissions import FLAGS, guest_permission_diagnostics

ENDPOINT = 'http://127.0.0.1:45100/settings.json'
MAX_SCHEMA_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 4096
MAX_LOG_BYTES = 65536
PERSISTENCE_ERRORS = (
    ('parent-create-failed', b'Could not create the settings file parent directory. Unable to persist settings.'),
    ('open-failed', b'Could not open the JSON settings file. Unable to persist settings.'),
    ('write-failed', b'Could not write to JSON settings file. Unable to persist settings.'),
    ('commit-failed', b'Could not commit writes to JSON settings file. Unable to persist settings.'),
)

class ProvisioningDiagnosticError(RuntimeError):
    def __init__(self, diagnostic):
        super().__init__('Native settings provisioning response or schema was not validated')
        self.diagnostic = diagnostic


def read_regular(filename, limit):
    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Provisioning input is not a bounded regular file')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Provisioning input exceeds byte bound')
        return data
    finally:
        os.close(fd)


def strict_json(data):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate provisioning JSON key')
            out[key] = value
        return out
    return json.loads(data, object_pairs_hook=pairs)


def configuration_digest(filename):
    try:
        return hashlib.sha256(read_regular(filename, MAX_SCHEMA_BYTES)).digest()
    except (OSError, ValueError):
        return None


def schema_diagnostic(data):
    result = {'version': 'unrecognized', 'postingKeys': 'unrecognized'}
    try:
        if not isinstance(data, bytes) or len(data) > MAX_SCHEMA_BYTES:
            return result
        document = strict_json(data)
        if not isinstance(document, dict) or type(document.get('version')) not in (float, int) or document['version'] != 2.7:
            return result
        result['version'] = '2.7'
        groups = document.get('settings')
        if not isinstance(groups, list) or len(groups) > 128:
            return result
        expected = {'security': {'standard_permissions': 'table', 'ip_permissions': 'table', 'machine_fingerprint_permissions': 'table'},
                    'authentication': {'enable_oauth2': 'checkbox'}}
        for group_name, settings in expected.items():
            found = [g for g in groups if isinstance(g, dict) and g.get('name') == group_name]
            if len(found) != 1 or not isinstance(found[0].get('settings'), list) or len(found[0]['settings']) > 256:
                return result
            for setting_name, kind in settings.items():
                records = [s for s in found[0]['settings'] if isinstance(s, dict) and s.get('name') == setting_name]
                if len(records) != 1 or records[0].get('type') != kind or records[0].get('content_setting', False) is not False:
                    return result
                if setting_name == 'standard_permissions':
                    columns = records[0].get('columns')
                    if not isinstance(columns, list) or len(columns) > 32:
                        return result
                    for flag in FLAGS:
                        fields = [c for c in columns if isinstance(c, dict) and c.get('name') == flag]
                        if len(fields) != 1 or fields[0].get('type') != 'checkbox':
                            return result
        result['postingKeys'] = 'recognized-domain-settings'
    except (ValueError, TypeError, UnicodeError, RecursionError):
        pass
    return result


class NoSettingsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        # Never replay the private Authorization header to another endpoint.
        raise RuntimeError('Native settings endpoint redirect refused')


class PersistenceObservation:
    """Hold the same bounded regular log FD across the POST, excluding earlier errors."""
    def __init__(self, filename):
        self.fd = None
        self.initial = 0
        fd = None
        try:
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                os.close(fd)
                return
            self.fd = fd
            self.initial = info.st_size
        except OSError:
            if fd is not None:
                os.close(fd)

    def snapshot(self):
        out = {'outcome': 'log-unavailable', 'observedBytes': 0, 'truncated': False}
        if self.fd is None:
            return out
        try:
            size = os.fstat(self.fd).st_size
            if size < self.initial:
                return {**out, 'outcome': 'log-truncated-during-post'}
            new_bytes = size - self.initial
            data = os.pread(self.fd, min(new_bytes, MAX_LOG_BYTES), max(self.initial, size - MAX_LOG_BYTES))
            outcome = 'no-reported-failure'
            for category, phrase in PERSISTENCE_ERRORS:
                if phrase in data:
                    outcome = category
                    break
            return {'outcome': outcome, 'observedBytes': min(new_bytes, (1 << 53) - 1), 'truncated': new_bytes > MAX_LOG_BYTES}
        except OSError:
            return out

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def response_diagnostic(response):
    out = {'status': 'unexpected', 'endpoint': 'unexpected', 'contentType': 'unexpected', 'body': 'unvalidated'}
    if response.status == 200:
        out['status'] = '200'
    if response.geturl() == ENDPOINT:
        out['endpoint'] = 'expected-settings-endpoint'
    content_type = response.headers.get('Content-Type', '').split(';', 1)[0].strip().lower()
    if content_type == 'application/json':
        out['contentType'] = 'application/json'
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        out['body'] = 'over-limit'
        return out
    try:
        body = strict_json(data)
        out['body'] = 'success' if body == {'status': 'success'} else 'unexpected-json'
    except (ValueError, UnicodeError, RecursionError):
        out['body'] = 'invalid-json'
    return out


def require_disabled_stored_oauth(config_file):
    """Read the actual bounded regular config; never infer disabled from absence."""
    document = strict_json(read_regular(config_file, MAX_SCHEMA_BYTES))
    if not isinstance(document, dict) or not isinstance(document.get('authentication'), dict) \
            or document['authentication'].get('enable_oauth2') is not False:
        raise ValueError('Managed settings require explicitly disabled stored OAuth')


def security_only_guest_payload(payload):
    """The native auth-group POST restarts even if its boolean is unchanged."""
    if not isinstance(payload, dict) or set(payload) != {'security'}:
        return False
    security = payload['security']
    if not isinstance(security, dict) or set(security) != {'standard_permissions', 'ip_permissions', 'machine_fingerprint_permissions'} \
            or security['ip_permissions'] != [] or security['machine_fingerprint_permissions'] != []:
        return False
    rows = security['standard_permissions']
    if not isinstance(rows, list) or len(rows) != 4 or any(not isinstance(row, dict) \
            or set(row) != {'permissions_id', *FLAGS} for row in rows):
        return False
    expected = {key: key in ('id_can_connect', 'id_can_rez', 'id_can_rez_avatar_entities', 'id_can_view_asset_urls') for key in FLAGS}
    return guest_permission_diagnostics(rows, expected)['passed']


def post_guest_settings(payload, authorization, schema_file, config_file, log_file, opener=None):
    try:
        schema = schema_diagnostic(read_regular(schema_file, MAX_SCHEMA_BYTES))
    except (OSError, ValueError):
        schema = {'version': 'unavailable', 'postingKeys': 'unrecognized'}
    out = {'kind': 'settings-provisioning', 'schema': schema, 'response': {'status': 'not-requested'},
           'configurationChanged': None, 'persistence': {'outcome': 'not-observed'},
           'oauthBefore': 'unvalidated', 'oauthAfter': 'not-observed'}
    if schema['postingKeys'] != 'recognized-domain-settings' or not security_only_guest_payload(payload):
        raise ProvisioningDiagnosticError(out)
    try:
        require_disabled_stored_oauth(config_file)
        out['oauthBefore'] = 'disabled'
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        raise ProvisioningDiagnosticError(out) from None
    before = configuration_digest(config_file)
    if before is None:
        raise ProvisioningDiagnosticError(out)
    observation = PersistenceObservation(log_file)
    try:
        request = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(),
                  {'Content-Type': 'application/json', 'Authorization': authorization}, method='POST')
        connection = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoSettingsRedirect())
        try:
            with connection.open(request, timeout=10) as response:
                out['response'] = response_diagnostic(response)
        except urllib.error.HTTPError as error:
            out['response'] = {'status': 'http-error', 'endpoint': 'unvalidated', 'contentType': 'unvalidated', 'body': 'unvalidated'}
            error.close()
            raise ProvisioningDiagnosticError(out) from None
        except (OSError, RuntimeError):
            out['response'] = {'status': 'transport-or-redirect-refused'}
            raise ProvisioningDiagnosticError(out) from None
        expected = {'status': '200', 'endpoint': 'expected-settings-endpoint', 'contentType': 'application/json', 'body': 'success'}
        if out['response'] != expected:
            raise ProvisioningDiagnosticError(out)
    finally:
        out['persistence'] = observation.snapshot()
        observation.close()
        after = configuration_digest(config_file)
        out['configurationChanged'] = None if after is None else after != before
    try:
        require_disabled_stored_oauth(config_file)
        out['oauthAfter'] = 'disabled'
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        out['oauthAfter'] = 'unvalidated'
        raise ProvisioningDiagnosticError(out) from None
    return out
