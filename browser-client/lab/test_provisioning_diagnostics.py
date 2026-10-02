# SPDX-License-Identifier: Apache-2.0
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from guest_permissions import FLAGS
from provisioning_diagnostics import (ENDPOINT, MAX_LOG_BYTES, NoSettingsRedirect, PersistenceObservation,
    ProvisioningDiagnosticError, post_guest_settings, schema_diagnostic, response_diagnostic)


def schema():
    columns = [{'name': key, 'type': 'checkbox'} for key in FLAGS]
    return {'version': 2.7, 'settings': [
        {'name': 'security', 'settings': [
            {'name': 'standard_permissions', 'type': 'table', 'columns': columns},
            {'name': 'ip_permissions', 'type': 'table'}, {'name': 'machine_fingerprint_permissions', 'type': 'table'}]},
        {'name': 'authentication', 'settings': [{'name': 'enable_oauth2', 'type': 'checkbox'}]}]}

def guest_payload():
    expected = {key: key in ('id_can_connect', 'id_can_rez', 'id_can_rez_avatar_entities', 'id_can_view_asset_urls') for key in FLAGS}
    return {'security': {'standard_permissions': [{'permissions_id': group, **expected} for group in ('anonymous', 'localhost', 'logged-in', 'friends')],
                         'ip_permissions': [], 'machine_fingerprint_permissions': []}}


def disabled_config(private='initial-secret'):
    return json.dumps({'authentication': {'enable_oauth2': False}, 'private': private})


class Response(io.BytesIO):
    def __init__(self, data=b'{"status":"success"}', status=200, url=ENDPOINT, content_type='application/json'):
        super().__init__(data); self.status=status; self.url=url; self.headers={'Content-Type': content_type}
    def geturl(self): return self.url

class ProvisioningDiagnostics(unittest.TestCase):
    def test_schema_requires_actual_version_domain_keys_and_all_boolean_columns(self):
        self.assertEqual(schema_diagnostic(json.dumps(schema()).encode()), {'version':'2.7','postingKeys':'recognized-domain-settings'})
        for mutate in [lambda d:d.update(version=2.8),
                       lambda d:d['settings'][0]['settings'][0].update(name='private-invalid-key'),
                       lambda d:d['settings'][0]['settings'][0].update(content_setting=True),
                       lambda d:d['settings'][0]['settings'][0]['columns'].pop(),
                       lambda d:d['settings'].append(d['settings'][0])]:
            document=schema();mutate(document);result=schema_diagnostic(json.dumps(document).encode())
            self.assertEqual(result['postingKeys'],'unrecognized');self.assertNotIn('private',json.dumps(result))
        self.assertEqual(schema_diagnostic(b'{"version":2.7,"version":2.7}')['postingKeys'],'unrecognized')
        self.assertEqual(schema_diagnostic(b'['*2000+b']'*2000)['postingKeys'],'unrecognized')

    def test_response_requires_exact_endpoint_json_success_and_original_bounded_body(self):
        good=response_diagnostic(Response(content_type='application/json; charset=utf-8'))
        self.assertEqual(good,{'status':'200','endpoint':'expected-settings-endpoint','contentType':'application/json','body':'success'})
        for response in [Response(b'<html>private-secret</html>',content_type='text/html'),
                         Response(b'{"status":"success","secret":"private-secret"}'),Response(url='http://private-secret/settings.json'),
                         Response(status=201),Response(b'x'*4097),Response(b'{"status":"success","status":"success"}')]:
            out=response_diagnostic(response);self.assertNotEqual(out,good);self.assertNotIn('private-secret',json.dumps(out))
        with self.assertRaisesRegex(RuntimeError,'redirect refused'):
            NoSettingsRedirect().redirect_request(None,None,302,'private-message',{},'http://private-target/')

    def test_actual_post_constructs_security_only_payload_and_auth_but_exports_only_safe_effects(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log'
            schema_file.write_text(json.dumps(schema()));config.write_text(disabled_config());log.write_text('startup secret\n')
            payload=guest_payload()
            class Opener:
                def open(_self,request,timeout):
                    self.assertEqual(request.full_url,ENDPOINT);self.assertEqual(request.method,'POST');self.assertEqual(timeout,10)
                    self.assertEqual(request.get_header('Authorization'),'Basic synthetic-private-token');self.assertEqual(json.loads(request.data),payload);self.assertEqual(set(json.loads(request.data)),{'security'});self.assertNotIn('authentication',json.loads(request.data))
                    config.write_text(disabled_config('new-secret'));return Response()
            result=post_guest_settings(payload,'Basic synthetic-private-token',schema_file,config,log,Opener())
            self.assertEqual(result['oauthBefore'],'disabled');self.assertEqual(result['oauthAfter'],'disabled')
            self.assertTrue(result['configurationChanged']);self.assertEqual(result['persistence']['outcome'],'no-reported-failure')
            self.assertNotIn('secret',json.dumps(result));self.assertNotIn('synthetic-private-token',json.dumps(result));self.assertNotIn(str(root),json.dumps(result))
            with patch('provisioning_diagnostics.urllib.request.build_opener', return_value=Opener()) as build:
                post_guest_settings(payload,'Basic synthetic-private-token',schema_file,config,log)
            handlers=build.call_args.args
            self.assertEqual(handlers[0].proxies,{})
            self.assertIsInstance(handlers[1],NoSettingsRedirect)

    def test_post_failure_preserves_strict_refusal_and_observes_real_append_before_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log'
            schema_file.write_text(json.dumps(schema()));config.write_text(disabled_config());log.write_text('old prefix\n')
            class Opener:
                def open(_self,request,timeout):
                    with log.open('a') as f:f.write('Could not commit writes to JSON settings file. Unable to persist settings. private-secret\n')
                    return Response(b'private-html',content_type='text/html')
            with self.assertRaises(ProvisioningDiagnosticError) as caught:
                post_guest_settings(guest_payload(),'Basic private-secret',schema_file,config,log,Opener())
            out=caught.exception.diagnostic;self.assertEqual(out['response']['body'],'invalid-json');self.assertFalse(out['configurationChanged']);self.assertEqual(out['persistence']['outcome'],'commit-failed');self.assertNotIn('private-secret',json.dumps(out))

    def test_held_log_identity_ignores_old_errors_and_rejects_fifo_or_symlink_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);log=root/'log';log.write_text('Could not open the JSON settings file. Unable to persist settings.\n')
            observer=PersistenceObservation(log);self.assertEqual(observer.snapshot()['outcome'],'no-reported-failure')
            renamed=root/'owned-held';log.rename(renamed);log.symlink_to(root/'other');(root/'other').write_text('private-secret')
            with renamed.open('a') as f:f.write('Could not write to JSON settings file. Unable to persist settings.\n')
            self.assertEqual(observer.snapshot()['outcome'],'write-failed');observer.close();observer.close()
            other=PersistenceObservation(log);self.assertEqual(other.snapshot()['outcome'],'log-unavailable');other.close()
            fifo=root/'fifo';os.mkfifo(fifo);other=PersistenceObservation(fifo);self.assertEqual(other.snapshot()['outcome'],'log-unavailable');other.close()

    def test_log_limit_and_truncate_are_explicit_not_saved_success(self):
        with tempfile.TemporaryDirectory() as directory:
            log=Path(directory)/'log';log.write_bytes(b'old');observer=PersistenceObservation(log)
            with log.open('ab') as f:f.write(b'private-token'*MAX_LOG_BYTES)
            out=observer.snapshot();self.assertTrue(out['truncated']);self.assertEqual(out['outcome'],'no-reported-failure');self.assertNotIn('private-token',json.dumps(out))
            log.write_bytes(b'');self.assertEqual(observer.snapshot()['outcome'],'log-truncated-during-post');observer.close()

    def test_invalid_schema_or_configuration_prevents_any_post(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log';config.write_text(disabled_config());log.write_text('')
            class Refused:
                def open(_self,*args,**kwargs):self.fail('No POST may occur')
            schema_file.write_text('{}')
            with self.assertRaises(ProvisioningDiagnosticError):post_guest_settings(guest_payload(),'private-token',schema_file,config,log,Refused())
            schema_file.write_text(json.dumps(schema()));config.unlink();os.mkfifo(config)
            with self.assertRaises(ProvisioningDiagnosticError):post_guest_settings(guest_payload(),'private-token',schema_file,config,log,Refused())

    def test_true_unknown_untyped_or_duplicate_stored_oauth_never_posts(self):
        values = ['{}', '{"authentication":{}}', '{"authentication":{"enable_oauth2":true}}',
                  '{"authentication":{"enable_oauth2":0}}', '{"authentication":{"enable_oauth2":null}}',
                  '{"authentication":{"enable_oauth2":"false"}}',
                  '{"authentication":{"enable_oauth2":false,"enable_oauth2":false}}', 'private-malformed-json']
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log'
            schema_file.write_text(json.dumps(schema()));log.write_text('')
            class Refused:
                def open(_self,*args,**kwargs):self.fail('Unsafe OAuth state must never post')
            for value in values:
                config.write_text(value)
                with self.assertRaises(ProvisioningDiagnosticError) as caught:
                    post_guest_settings(guest_payload(),'Basic private-token',schema_file,config,log,Refused())
                self.assertEqual(caught.exception.diagnostic['oauthBefore'],'unvalidated')
                self.assertEqual(caught.exception.diagnostic['response'],{'status':'not-requested'})
                self.assertNotIn('private-',json.dumps(caught.exception.diagnostic))

    def test_any_auth_or_nonsecurity_post_group_and_invalid_guest_policy_never_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log'
            schema_file.write_text(json.dumps(schema()));config.write_text(disabled_config());log.write_text('')
            class Refused:
                def open(_self,*args,**kwargs):self.fail('Restart-triggering or invalid policy payload must never post')
            candidates = []
            old = guest_payload();old['authentication']={'enable_oauth2':False};candidates.append(old)
            extra = guest_payload();extra['oauth']={};candidates.append(extra)
            wrong=guest_payload();wrong['security']['allowed_subnets']=[];candidates.append(wrong)
            wrong=guest_payload();wrong['security']['ip_permissions']=[{'private':'secret'}];candidates.append(wrong)
            wrong=guest_payload();wrong['security']['machine_fingerprint_permissions']=[{}];candidates.append(wrong)
            wrong=guest_payload();wrong['security']['standard_permissions'][0]['id_can_kick']=True;candidates.append(wrong)
            wrong=guest_payload();wrong['security']['standard_permissions'][0]['id_can_connect']=False;candidates.append(wrong)
            wrong=guest_payload();wrong['security']['standard_permissions'][0]['private']='secret';candidates.append(wrong)
            wrong=guest_payload();wrong['security']['standard_permissions'].pop();candidates.append(wrong)
            for payload in candidates:
                with self.assertRaises(ProvisioningDiagnosticError) as caught:
                    post_guest_settings(payload,'Basic private-token',schema_file,config,log,Refused())
                self.assertEqual(caught.exception.diagnostic['response'],{'status':'not-requested'})
                self.assertNotIn('secret',json.dumps(caught.exception.diagnostic))

    def test_actual_after_read_requires_disabled_oauth_even_when_http_succeeded(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log'
            schema_file.write_text(json.dumps(schema()));log.write_text('')
            for replacement in ['{}','{"authentication":{"enable_oauth2":true}}','{"authentication":{"enable_oauth2":0}}']:
                config.write_text(disabled_config())
                class Opener:
                    def open(_self,request,timeout):
                        self.assertEqual(set(json.loads(request.data)),{'security'})
                        config.write_text(replacement);return Response()
                with self.assertRaises(ProvisioningDiagnosticError) as caught:
                    post_guest_settings(guest_payload(),'Basic private-token',schema_file,config,log,Opener())
                self.assertEqual(caught.exception.diagnostic['oauthBefore'],'disabled')
                self.assertEqual(caught.exception.diagnostic['oauthAfter'],'unvalidated')
                self.assertEqual(caught.exception.diagnostic['response']['body'],'success')

    def test_before_and_after_config_symlink_fifo_refused_without_following_or_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);schema_file=root/'schema';config=root/'config';log=root/'log';other=root/'other'
            schema_file.write_text(json.dumps(schema()));log.write_text('');other.write_text(disabled_config())
            class Refused:
                def open(_self,*args,**kwargs):self.fail('Unowned config alias must never post')
            for kind in ('symlink','fifo'):
                if kind=='symlink':config.symlink_to(other)
                else:os.mkfifo(config)
                with self.assertRaises(ProvisioningDiagnosticError) as caught:
                    post_guest_settings(guest_payload(),'Basic private-token',schema_file,config,log,Refused())
                self.assertEqual(caught.exception.diagnostic['response'],{'status':'not-requested'})
                config.unlink()
                config.write_text(disabled_config())
                class Opener:
                    def open(_self,request,timeout):
                        config.unlink()
                        if kind=='symlink':config.symlink_to(other)
                        else:os.mkfifo(config)
                        return Response()
                with self.assertRaises(ProvisioningDiagnosticError) as caught:
                    post_guest_settings(guest_payload(),'Basic private-token',schema_file,config,log,Opener())
                self.assertEqual(caught.exception.diagnostic['oauthAfter'],'unvalidated')
                self.assertEqual(other.read_text(),disabled_config())
                config.unlink()

if __name__=='__main__':unittest.main()
