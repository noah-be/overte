#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Execute production native editor metadata with Android API26/35; provider is a boundary."""
import argparse
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gradle", type=Path, default=ROOT / "android/common/gradlew")
    parser.add_argument("--offline-init", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    project=args.output / "project"; project.mkdir()
    (project / "settings.gradle").write_text("rootProject.name='pico-native-editor-api'\n")
    source=ROOT / "android/vr/pico/apps/picoInterface/src/main/java"
    tests=ROOT / "android/vr/pico/tests/editor"
    (project / "build.gradle").write_text("""plugins { id 'java' }
repositories { mavenCentral(); google() }
sourceSets {
 main.java { srcDir '"""+str(source)+"""'; include 'org/overte/pico/PicoWebEditorState.java'; include 'org/overte/pico/PicoTextInput.java' }
 test.java { srcDir '"""+str(tests)+"""'; include 'PicoWebEditorApiTest.java' }
}
dependencies {
 compileOnly 'org.robolectric:android-all:15-robolectric-13954326'
 testImplementation 'org.robolectric:android-all:15-robolectric-13954326'
 testImplementation 'junit:junit:4.13.2'
 testImplementation 'org.robolectric:robolectric:4.16.1'
}
java { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
test {
 useJUnit(); systemProperty 'java.awt.headless', 'true'
 // The plain Java plugin does not expose classes nested inside original AARs.
 // Consume the actual resolved runtime classes.jar instead of inventing APIs.
 doFirst {
  def jars = []
  configurations.testRuntimeClasspath.resolvedConfiguration.resolvedArtifacts.each { artifact ->
   if (artifact.extension == 'aar') {
    def destination = layout.buildDirectory.dir('test-aar-api/' + artifact.moduleVersion.id.group + '/' + artifact.name).get().asFile
    copy { from zipTree(artifact.file); include 'classes.jar'; into destination }
    jars.add(new File(destination, 'classes.jar'))
   }
  }
  classpath += files(jars)
 }
}
""")
    command=[str(args.gradle),'--no-daemon','--max-workers=4','--console=plain','-p',str(project)]
    if args.offline_init:command+=['--offline','-I',str(args.offline_init)]
    result=subprocess.run(command+['test'],check=False)
    if result.returncode:return result.returncode
    reports=list((project/'build/test-results/test').glob('TEST-*.xml'))
    counts={key:sum(int(ET.parse(p).getroot().get(key,'0')) for p in reports) for key in ['tests','failures','errors','skipped']}
    if counts!={'tests':6,'failures':0,'errors':0,'skipped':0}:raise RuntimeError('Incomplete actual Android editor API cases')
    print('PASS actual Android API26/35 metadata, composition, selection; provider/DOM and physical HMD remain boundaries')
    return 0

if __name__=='__main__':raise SystemExit(main())
