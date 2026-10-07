#!/usr/bin/env python3
# Copyright 2026 Overte contributors
# SPDX-License-Identifier: Apache-2.0
"""Compile only. Never create a GUI, display, native/browser/profile/domain process."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'web-editor'))
from application_key_attestation import attest_input,digest_regular

def compile_fixture(input_build,qt_libraries,output):
    build=Path(input_build).resolve(strict=True);qt=Path(qt_libraries).resolve(strict=True);output=Path(output).absolute()
    if output.exists() or output.is_symlink() or output.parent.resolve(strict=True)!=output.parent or not output.as_posix().startswith('/tmp/'):raise ValueError('key-fixture-exclusive-tmp-output-required')
    source=HERE.parent/'native-input.cpp';bindings=attest_input(build,source)
    whitelist=json.loads((HERE.parent/'web-editor/runtime-input-artifacts.json').read_text())
    for name,row in whitelist['files'].items():
        digest,data=digest_regular(qt.parent/name,32*1024*1024)
        if digest!=row['sha256'] or len(data)!=row['bytes']:raise ValueError('key-fixture-pinned-runtime-refused')
    files=['key-fixture.cpp','key-fixture.qml','key-fixture.html'];pins={name:digest_regular(HERE/name,128*1024)[0] for name in files}
    output.mkdir(mode=0o700);include=build/'sdk/usr/include/x86_64-linux-gnu/qt5';moc=build/'sdk/usr/lib/qt5/bin/moc'
    flags=['-std=c++17','-fPIC','-O2','-Wall','-Wextra','-Werror','-I',str(include)]
    for name in ['QtCore','QtGui','QtQml','QtQuick','QtWidgets']:flags+=['-I',str(include/name)]
    flags+=['-I',str(output)];env={'PATH':os.defpath,'LD_LIBRARY_PATH':str(qt)}
    commands=[[str(moc),*flags[6:],str(HERE/'key-fixture.cpp'),'-o',str(output/'key-fixture.moc')],['g++',*flags,str(HERE/'key-fixture.cpp'),'-o',str(output/'key-fixture'),*[str(qt/f'libQt5{m}.so.5') for m in ['WebEngine','Widgets','Quick','Qml','Gui','Core']]]]
    for command in commands:subprocess.run(command,env=env,check=True,timeout=60,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    qtconf='[Paths]\nPrefix = '+str(qt.parent)+'\nData = .\nTranslations = translations\nLibraryExecutables = libexec\nLibraries = lib\nPlugins = plugins\nImports = qml\nQml2Imports = qml\n'
    (output/'qt.conf').write_text(qtconf);(output/'qt.conf').chmod(0o600)
    if attest_input(build,source)!=bindings or any(digest_regular(HERE/name,128*1024)[0]!=digest for name,digest in pins.items()):raise ValueError('key-fixture-source-changed')
    proof={'version':1,'compiled':True,'guiLaunched':False,'nativeInterfaceProof':False,'qtSDKVersion':'5.15.3','pinnedRuntimeResources':len(whitelist['files']),'inputBindings':bindings,'sources':pins,'ownedQtConfigurationSHA256':hashlib.sha256(qtconf.encode()).hexdigest(),'fixtureExecutableSHA256':digest_regular(output/'key-fixture',32*1024*1024)[0]}
    report=output/'compile-proof.private.json';report.write_text(json.dumps(proof,indent=2)+'\n');report.chmod(0o600);return proof
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['input-build','qt-libraries','output']:parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    try:print(json.dumps(compile_fixture(args.input_build,args.qt_libraries,args.output)))
    except (OSError,ValueError,subprocess.SubprocessError):print(json.dumps({'compiled':False,'guiLaunched':False,'failureCategory':'key-fixture-build-or-attestation-refused'}));raise SystemExit(1)
