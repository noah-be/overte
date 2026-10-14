#!/usr/bin/env python3
# Copyright 2026 Overte contributors.
# SPDX-License-Identifier: Apache-2.0
"""Compile the actual Pico/Common APIs and execute Activity focus/picker callers on API26/35."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[4]

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gradle',type=Path,default=ROOT/'android/common/gradlew')
    parser.add_argument('--offline-init',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--common-source-root',type=Path,default=ROOT,
                        help='Explicit owning-parent test dependency; never a product source override')
    parser.add_argument('--common-source-revision',required=True)
    parser.add_argument('--android-jar',type=Path,required=True)
    parser.add_argument('--webkit-jar',type=Path,required=True)
    parser.add_argument('--qt-jar',type=Path,required=True)
    parser.add_argument('--core-jar',type=Path,required=True)
    parser.add_argument('--original-host',type=Path,
                        help='Retained original Pico host for the failing product-control run')
    args=parser.parse_args()
    common=args.common_source_root.resolve()
    actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=common,text=True).strip()
    if actual!=args.common_source_revision:raise RuntimeError('Owning source revision changed')
    if subprocess.check_output(['git','status','--porcelain','--','android/common/web'],cwd=common,text=True):
        raise RuntimeError('Owning Web dependency has uncommitted changes')
    jars=[args.android_jar,args.webkit_jar,args.qt_jar,args.core_jar]
    if not args.gradle.is_file():raise RuntimeError('An actual Gradle executable is required')
    if args.offline_init and not args.offline_init.is_file():raise RuntimeError('Missing offline initialization script')
    if not all(p.is_file() for p in jars):raise RuntimeError('The four actual SDK/AndroidX/Qt API inputs are required')
    args.output.mkdir(parents=True,exist_ok=False)
    project=args.output/'project';project.mkdir()
    sources=[]
    for folder in [ROOT/'android/vr/pico/apps/picoInterface/src/main/java',
                   ROOT/'android/common/libraries/qt/src/main/java',
                   ROOT/'security/redaction/java',common/'android/common/web/java',
                   ROOT/'android/common/documents/java',ROOT/'android/common/snapshot/java']:
        sources.extend(p for p in folder.rglob('*.java') if p.name!='PermissionsActivity.java')
    if args.original_host:
        if not args.original_host.is_file():raise RuntimeError('Missing original product-control source')
        sources=[p for p in sources if p.name!='PicoEmbeddedWebHost.java']+[args.original_host]
    sources=sorted(sources)
    (args.output/'actual-inputs.json').write_text(json.dumps({
        'picoSource':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'picoWorkingDiffSha256':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'],cwd=ROOT)).hexdigest(),
        'commonSource':actual,'commonRole':'Explicit test preview; protected direct-parent propagation remains required',
        'testSources':{str(p):digest(p) for p in [Path(__file__).resolve(),ROOT/'android/vr/pico/tests/focus/PicoEmbeddedWebFocusApiTest.java']},
        'gradleInputs':{str(p):digest(p) for p in [args.gradle]+([args.offline_init] if args.offline_init else [])},
        'sources':{str(p):digest(p) for p in sources},'apiJars':{str(p):digest(p) for p in jars},
        'originalProductControl':bool(args.original_host),
        'boundaries':['Native Qt/OpenXR/bootstrap/voice and shared JNI endpoints','OS document provider','Chromium DOM, hardware texture, media and physical HMD']},indent=2)+'\n')
    def files(paths):return ','.join(json.dumps(str(p)) for p in paths)
    (project/'settings.gradle').write_text("rootProject.name='pico-embedded-web-focus-api'\n")
    (project/'build.gradle').write_text("""plugins { id 'java' }
repositories { mavenCentral(); google() }
sourceSets {
 main.java.setSrcDirs([])
 test.java { srcDir """+json.dumps(str(ROOT/'android/vr/pico/tests/focus'))+"""; include 'PicoEmbeddedWebFocusApiTest.java' }
}
tasks.named('compileJava') { source = files("""+files(sources)+""") }
dependencies {
 compileOnly files("""+files(jars)+""")
 testImplementation files("""+files(jars[1:])+""")
 testImplementation 'org.robolectric:android-all:15-robolectric-13954326'
 testImplementation 'junit:junit:4.13.2'
 testImplementation 'org.robolectric:robolectric:4.16.1'
}
java { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
test {
 useJUnit(); systemProperty 'java.awt.headless','true'
 doFirst {
  def jars=[]
  configurations.testRuntimeClasspath.resolvedConfiguration.resolvedArtifacts.each { artifact ->
   if(artifact.extension=='aar') {
    def destination=layout.buildDirectory.dir('test-aar-api/'+artifact.moduleVersion.id.group+'/'+artifact.name).get().asFile
    copy { from zipTree(artifact.file); include 'classes.jar'; into destination }
    jars.add(new File(destination,'classes.jar'))
   }
  }
  classpath+=files(jars)
  file('runtime-input-paths.json').text=groovy.json.JsonOutput.toJson(
   [files:classpath.files.collect { it.absolutePath }, systemProperties:systemProperties])
 }
}
""")
    command=[str(args.gradle),'--no-daemon','--max-workers=4','--console=plain','-p',str(project)]
    if args.offline_init:command+=['--offline','-I',str(args.offline_init)]
    (args.output/'invocation.json').write_text(json.dumps({'argv':command+['test'],'workingDirectory':str(ROOT)},indent=2)+'\n')
    result=subprocess.run(command+['test'],check=False)
    runtime=project/'runtime-input-paths.json'
    if runtime.is_file():
        paths=json.loads(runtime.read_text())
        (args.output/'runtime-input-hashes.json').write_text(json.dumps({
            'files':{path:digest(Path(path)) for path in paths['files'] if Path(path).is_file()},
            'systemProperties':paths['systemProperties'],
            'compiledClasses':{str(path):digest(path) for path in (project/'build/classes').rglob('*.class')}},indent=2)+'\n')
    reports=list((project/'build/test-results/test').glob('TEST-*.xml'))
    counts={k:sum(int(ET.parse(p).getroot().get(k,'0')) for p in reports) for k in ['tests','failures','errors','skipped']}
    (args.output/'result.json').write_text(json.dumps({'exit':result.returncode,'counts':counts},indent=2)+'\n')
    if result.returncode:return result.returncode
    if counts!={'tests':10,'failures':0,'errors':0,'skipped':0}:raise RuntimeError('Incomplete actual Activity/API focus cases')
    classes=project/'build/classes/java/main'
    for name in ['org.overte.pico.PicoEmbeddedWebHost','org.overte.pico.PicoInterfaceActivity','org.overte.web.EmbeddedWebView']:
        text=subprocess.check_output(['javap','-private','-c','-s','-classpath',str(classes),name],text=True)
        (args.output/(name.rsplit('.',1)[-1]+'-bytecode.txt')).write_text(text)
    print('PASS actual SDK-compiled Pico/Common APIs and API26/35 Activity focus, owner and picker behavior; native engines/provider/HMD remain boundaries')
    return 0
if __name__=='__main__':raise SystemExit(main())
