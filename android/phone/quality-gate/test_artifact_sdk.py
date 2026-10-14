#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Explicit real-SDK resource regression; never builds Overte or uses a device."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
from artifact_inputs import artifact_inputs, sdk_files
from core import digest, write_json
from runtime_checks import packaged_browser_network
from source_checks import NETWORK_ROOT, NETWORK_CONFIG, PHONE_MANIFEST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk-root', type=Path, required=True)
    parser.add_argument('--sdk-bindings', type=Path, required=True)
    parser.add_argument('--expected-sdk-bindings-sha256', required=True)
    parser.add_argument('--java-home', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    output = args.output.resolve()
    if output.exists() or root == output or root in output.parents:
        parser.error('Output must be a new private directory outside the checkout')
    if digest(args.sdk_bindings) != args.expected_sdk_bindings_sha256:
        parser.error('SDK binding file differs from independent expected SHA256')
    bindings = json.loads(args.sdk_bindings.read_text())
    sdk = args.sdk_root.resolve()
    files = sdk_files(sdk)
    if set(files) != set(bindings):
        parser.error('SDK closure differs from complete configured bindings')
    for relative, source in files.items():
        if (digest(source) != bindings[relative]['sha256']
                or bool(source.stat().st_mode & 0o111) != bindings[relative]['executable']):
            parser.error('SDK input differs from configured bytes or executable mode')
    lock = json.loads((root/'android/phone/fdroid/manifests/toolchain-provisioning.lock.json').read_text())
    if digest(sdk/'build-tools/36.0.0/aapt2') != lock['android_sdk_bindings']['build-tools/36.0.0/aapt2']:
        parser.error('Fixture compiler differs from original source provisioning lock')
    os.umask(0o077)
    output.mkdir(parents=True)
    tracer = shutil.which('strace', path='/usr/bin:/bin')
    env = dict(PATH='/usr/bin:/bin', JAVA_HOME=str(args.java_home), JAVA_OPTS='-XX:ActiveProcessorCount=4')
    aapt = sdk/'build-tools/36.0.0/aapt2'
    source_config = (root/NETWORK_CONFIG).read_bytes()
    manifest_source = ET.fromstring((root/PHONE_MANIFEST).read_bytes())
    android = '{http://schemas.android.com/apk/res/android}'
    source_app = manifest_source.find('application')
    fixture = ET.Element('manifest', {'package':'io.github.noah_be.overte.phone',
        android+'versionCode':'14', android+'versionName':'resource-fixture'})
    ET.SubElement(fixture, 'uses-sdk', {android+'minSdkVersion':'26',android+'targetSdkVersion':'36'})
    app = ET.SubElement(fixture, 'application', {android+'usesCleartextTraffic':source_app.get(android+'usesCleartextTraffic'),
        android+'networkSecurityConfig':source_app.get(android+'networkSecurityConfig')})
    declaration = next(m for m in source_app.findall('meta-data')
                       if m.get(android+'name')=='org.overte.web.NETWORK_CAPABILITY')
    ET.SubElement(app,'meta-data',dict(declaration.attrib))
    manifest = output/'fixture-manifest.xml'
    manifest.write_bytes(ET.tostring(fixture,encoding='utf-8',xml_declaration=True))
    apks = {}
    for name, content in [('valid',source_config),('invalid',source_config.replace(b'src="system"',b'src="user"'))]:
        resource = output/name/'res/xml/overte_embedded_web_network_security_config.xml'
        resource.parent.mkdir(parents=True)
        resource.write_bytes(content)
        compiled, apk = output/(name+'-compiled.zip'), output/(name+'.apk')
        with (output/(name+'-compiler.log')).open('w') as log:
            subprocess.run([aapt,'compile','--dir',resource.parent.parent,'-o',compiled],env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
            subprocess.run([aapt,'link','-o',apk,'--manifest',manifest,'-I',sdk/'platforms/android-36/android.jar',compiled],
                           env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
        apks[name]=apk
    # Mutable SDK origin is a private copy, never the installed SDK or producer cache.
    mutable = output/'sdk-origin'
    try:
        for relative in files:
            target=mutable/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(sdk/relative,target)
        cases=[]
        class Fixture:
            def __init__(self,directory):
                self.root=directory/'source-origin';self.out=directory
                self.policy={'embedded_browser_network_capability':'overte.android.embedded-web.http-https.v1',
                             'max_archive_bytes':4*1024*1024*1024}
                self.config={'artifact_sdk_bindings':bindings};self.source_hashes={};self.commands=[];self.findings=[];self.sdk_opened=set()
                self.artifact=None;self.attempt=None;self.receipt=None
                (directory/'tmp').mkdir()
                for relative in [NETWORK_CONFIG,NETWORK_ROOT+'network-capability.json',PHONE_MANIFEST]:
                    data=(root/relative).read_bytes()
                    for prefix in [self.root,directory/'source-scope']:
                        path=prefix/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
                    self.source_hashes[relative]=hashlib.sha256(data).hexdigest()
            def fail(self,*args):self.findings.append(args)
            def run(self,label,command):
                command=[str(x)for x in command];self.commands.append(command)
                if label.startswith('apk-network-resource-') and label!='apk-network-resource-inventory':
                    if mode=='replace-apk':shutil.copyfile(apks['valid'],original)
                    if mode=='replace-sdk':
                        (mutable/'cmdline-tools/latest/bin/apkanalyzer').write_text('#!/bin/sh\nexit 0\n')
                    if mode=='replace-source':
                        (self.root/(NETWORK_ROOT+'network-capability.json')).write_text('{}')
                    if mode=='corrupt-capture':
                        (self.out/'source-scope'/(NETWORK_ROOT+'network-capability.json')).write_text('{}')
                    if mode=='decoder-error':raise OSError('explicit decoder failure boundary')
                log=self.out/(label+'.log')
                try:
                    trace=self.out/(label+'-files.trace')
                    invocation=([tracer,'-f','-qq','-e','trace=openat','-o',str(trace),*command]
                                if tracer else command)
                    with log.open('w')as stream:
                        rc=subprocess.run(invocation,env=env,stdout=stream,stderr=subprocess.STDOUT).returncode
                    if tracer:
                        content=trace.read_text()
                        assert str(sdk)+'/' not in content, 'Decoder reopened original installed SDK'
                        assert str(mutable)+'/' not in content, 'Decoder reopened mutable SDK origin'
                        active_sdk=self.artifact_input_paths[1]
                        import re
                        for opened in re.findall(r'openat\([^,]+, "([^"\n]+)"',content):
                            path=Path(opened)
                            if path.is_relative_to(active_sdk):
                                relative=path.relative_to(active_sdk).as_posix()
                                if relative in bindings:
                                    self.sdk_opened.add(relative)
                                    assert digest(path)==bindings[relative]['sha256']
                    return rc,log
                finally:
                    shutil.copyfile(apks[which],original)
                    shutil.copyfile(sdk/'cmdline-tools/latest/bin/apkanalyzer',mutable/'cmdline-tools/latest/bin/apkanalyzer')
        for mode,which,wanted in [('ordinary-valid','valid',True),('ordinary-invalid','invalid',False),
                ('replace-apk','invalid',False),('replace-sdk','invalid',False),('replace-source','valid',True),
                ('corrupt-capture','valid',False),('decoder-error','valid',False)]:
            directory=output/mode;directory.mkdir()
            g=Fixture(directory);original=directory/'original.apk';shutil.copyfile(apks[which],original)
            expected=digest(original)
            with artifact_inputs(g,original,expected,mutable)as(private_apk,private_sdk):
                decoder=private_sdk/'cmdline-tools/latest/bin/apkanalyzer'
                decoded=subprocess.check_output([str(decoder),'manifest','print',str(private_apk)],env=env,text=True)
                result=packaged_browser_network(g,decoded,private_apk,private_sdk)
                assert result is wanted,(mode,result,g.findings)
                assert all(Path(c[-1])==private_apk for c in g.commands),mode
                assert all(Path(c[0]).is_relative_to(private_sdk)for c in g.commands),mode
            assert not private_apk.exists() and not private_sdk.exists(),mode
            assert list((directory/'tmp').iterdir())==[],mode
            assert digest(original)==expected,mode
            cases.append(dict(case=mode,accepted=result,expected=wanted,allReadersSamePrivateApk=True,
                              originalRestoredByteEqual=True,successAndFailureCopiesRemoved=True,
                              snapshotApkSha256=expected,optionalTracedSdkFiles=sorted(g.sdk_opened)))
        write_json(output/'actual-sdk-result.json',dict(
            source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
            cases=cases,sdk_binding_sha256=digest(args.sdk_bindings),sdkFiles=len(files),
            source_inputs={r:digest(root/r)for r in [NETWORK_CONFIG,NETWORK_ROOT+'network-capability.json',PHONE_MANIFEST]},
            fixture_inputs={'android36Jar':digest(sdk/'platforms/android-36/android.jar'),
                            'manifest':digest(manifest),'validApk':digest(apks['valid']),'invalidApk':digest(apks['invalid'])},
            optionalFilesystemTrace=('strace openat audit' if tracer else
                                     'not available; no dynamic file-open claim'),
            tracerSha256=digest(tracer) if tracer else None,
            java=dict(executableSha256=digest(args.java_home/'bin/java'),
                      version=subprocess.check_output([str(args.java_home/'bin/java'),'-version'],stderr=subprocess.STDOUT,text=True)),
            scope='Actual SDK binary resource decoder and production Phone consumer; resource-only fixtures. '
                  'SDK inventory awaits independent review; no full app/producer/signature/credential/device qualification.'))
    finally:
        shutil.rmtree(mutable)
    print('Actual SDK resource regression: 7 cases passed; all private consumer copies removed.')


if __name__=='__main__':
    main()
