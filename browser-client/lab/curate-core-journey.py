#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Publish a numeric/name whitelist from local native journeys, never raw logs."""
import argparse,itertools,json,math,re
from pathlib import Path

MAX_REPORT=8*1024*1024
CHECKPOINTS=('actual-domain-joined','native-sees-browser','movement-measured',
 'browser-movement-synchronized','native-movement-synchronized','actual-world-collision',
 'interaction-measured','interaction-observed-by-native','browser-to-native-audio',
 'native-to-browser-audio','stable-real-connection','native-observed-clean-leave',
 'reconnected-to-actual-domain','reconnection-movement-observed','reconnection-movement',
 'mouse-look','final-view','all-real-session-assertions-passed')
SOURCE_FILES={f'browser-client/{name}' for name in (
 'gateway/server.mjs','gateway/avatar-snapshot-sender.mjs','gateway/native-bridge.js','gateway/native-avatar-sample-diagnostics.js',
 'gateway/native-avatar-stdout-projection.mjs','gateway/process-lifecycle.mjs',
 'gateway/validation.mjs','gateway/permission-policy.mjs','dist/index.html',
 'tests/integration/real-session.mjs','tests/integration/system-firefox.mjs',
 'tests/integration/owned-audio-process.mjs','tests/integration/native-peer-diagnostic.mjs',
 'lab/native-participant.js','lab/manage.py','package-lock.json')}
TIMESTAMP=re.compile(r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?Z$')
VERSION=re.compile(r'^(?:firefox/)?\d[0-9A-Za-z._+-]{0,59}$')
DIGEST=re.compile(r'^[0-9a-f]{64}$')
COMMIT=re.compile(r'^[0-9a-f]{40}$')
ASSET=re.compile(r'^browser-client/dist/assets/[A-Za-z0-9_.-]{1,180}$')


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=1e12 else None


def timestamp(value):
    return value if isinstance(value,str) and TIMESTAMP.fullmatch(value) else None


def numeric_fields(document,keys):
    if not isinstance(document,dict):return {}
    return {key: value for key in keys if (value:=number(document.get(key))) is not None}


def distance(checkpoint):
    before,after=checkpoint.get('before'),checkpoint.get('after')
    if not isinstance(before,dict) or not isinstance(after,dict):return None
    values=[item.get(axis) for item in (before,after) for axis in ('x','y','z')]
    if not all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=1e7 for v in values):return None
    return math.dist(values[:3],values[3:])



def peer_diagnostic(document):
    if not isinstance(document,dict):return None
    def bounded(value,limit):
        return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=limit else None
    def booleans(source,keys):
        return {key:source[key] for key in keys if type(source.get(key)) is bool}
    result={}
    browser=document.get('browser')
    if isinstance(browser,dict):
        item=booleans(browser,('snapshotPresent','peerProjectionTruncated'))
        for key in ('snapshotAgeMs','avatarCount','peerCount','fixtureNameMatchCount'):
            item[key]=bounded(browser.get(key),1e9 if key=='snapshotAgeMs' else 1000000)
        peers=browser.get('peers')
        if isinstance(peers,list):
            item['peers']=[{**booleans(peer,('fixtureNameMatch',)),
                'targetDistance':bounded(peer.get('targetDistance'),1e8)}
                for peer in peers[:16] if isinstance(peer,dict)]
        selection=browser.get('socketSelection')
        keys={'selectedSocketOrdinal','latestCreatedSocketOrdinal','selectedIsLatest','selectedReadyState','latestReadyState','ordinalCensored'}
        if isinstance(selection,dict) and set(selection)==keys:
            ordinal=lambda v: v is None or type(v) is int and 1<=v<=32
            states=('connecting','open','closing','closed','unknown')
            if all(ordinal(selection.get(k)) for k in ('selectedSocketOrdinal','latestCreatedSocketOrdinal')) and (selection.get('selectedIsLatest') is None or type(selection.get('selectedIsLatest')) is bool) and all(selection.get(k) in states for k in ('selectedReadyState','latestReadyState')) and type(selection.get('ordinalCensored')) is bool:
                item['socketSelection']={k:selection[k] for k in sorted(keys)}
        result['browser']=item
    native=document.get('native')
    if isinstance(native,dict):
        item=booleans(native,('commandSequenceMatched','observationPresent','observationAfterCommand','tailTruncated'))
        if native.get('status') in ('read','missing','symlink-refused','not-regular','read-refused'):item['status']=native['status']
        for key in ('commandIssuedAtMs','diagnosticReadAtMs','commandAppliedAtMs','commandAppliedAgeMs','commandTargetDistance',
                    'observationAtMs','observationAgeMs','observationTargetDistance','bytesRead'):
            limit=1e15 if key.endswith('AtMs') else 1024*1024 if key=='bytesRead' else 1e12
            item[key]=bounded(native.get(key),limit)
        result['native']=item
    return result


def curate(document,engine):
    if engine not in ('chrome','chromium','firefox'):raise ValueError('Unexpected CI browser engine')
    if not isinstance(document,dict):raise ValueError('Journey report must be an object')
    result={'schemaVersion':1,'browser':engine,'status':'not-run','completed':False,
            'scope':'Real local managed-domain core journey; no public-world fluidness claim',
            'audio':'Synthetic signals at actual browser/native outputs; no physical microphone claim',
            'endurance':'Omitted at the user’s explicit instruction','checkpoints':[],'sourceSHA256':{}}
    for field in ('startedAt','finishedAt'):
        if value:=timestamp(document.get(field)):result[field]=value
    for field in ('browserVersion','nativeVersion'):
        value=document.get(field)
        if isinstance(value,str) and VERSION.fullmatch(value):result[field]=value
    result.update(numeric_fields(document,('journeySeconds','continuousSharedSessionSeconds')))
    hashes=document.get('sourceSHA256',{})
    if isinstance(hashes,dict):
        for key,value in itertools.islice(hashes.items(),256):
            if isinstance(key,str) and (key in SOURCE_FILES or ASSET.fullmatch(key)) and isinstance(value,str) and DIGEST.fullmatch(value):
                result['sourceSHA256'][key]=value
    entries=document.get('checkpoints',[])
    if not isinstance(entries,list) or len(entries)>256:raise ValueError('Checkpoint list exceeds reviewed bounds')
    for entry in entries:
        if not isinstance(entry,dict) or entry.get('name') not in CHECKPOINTS:continue
        item={'name':entry['name']}
        if value:=timestamp(entry.get('at')):item['at']=value
        if entry['name']=='actual-domain-joined':item.update(numeric_fields(entry,('entityCount','avatarCount')))
        if entry['name']=='native-sees-browser':item.update(numeric_fields(entry,('nativeOtherParticipants',)))
        if entry['name'] in ('movement-measured','browser-movement-synchronized','reconnection-movement'):
            if (value:=distance(entry)) is not None:item['distanceMeters']=value
        if entry['name']=='stable-real-connection':item.update(numeric_fields(entry,('connectedSeconds',)))
        if entry['name']=='movement-measured':
            item['renderPerformance']=numeric_fields(entry.get('performance'),('fps','p95FrameMs','maximumFrameMs','drawCalls','triangles'))
        for audio in ('nativeOutput','browserOutput'):
            if audio in entry:item[audio]=numeric_fields(entry[audio],('rms','peak','bytes','tone440Amplitude','tone997Amplitude'))
        result['checkpoints'].append(item)
    if diagnostic:=peer_diagnostic(document.get('nativePeerMovementDiagnostic')):
        result['nativePeerMovementDiagnostic']=diagnostic
    names={entry['name'] for entry in result['checkpoints']}
    short=type(document.get('durationSeconds')) in (int,float) and document.get('durationSeconds')==0
    result['completed']=document.get('completed') is True and short and document.get('syntheticMicrophone') is True and names==set(CHECKPOINTS)
    result['status']='passed' if result['completed'] else 'incomplete' if document else 'not-run'
    return result


def checked_commit(value):
    if not isinstance(value,str) or not COMMIT.fullmatch(value):raise ValueError('Tested commit must be an exact lowercase Git SHA')
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--commit-sha',type=checked_commit)
    parser.add_argument('--browser',choices=('chrome','chromium','firefox'),default='chrome',
                        help='Current CI uses Google Chrome; older evidence can still be curated explicitly')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    for engine in (args.browser,):
        source=args.input/f'real-session-{engine}.json'
        if source.exists():
            if source.stat().st_size>MAX_REPORT:raise ValueError('Journey report exceeds reviewed byte limit')
            document=json.loads(source.read_text())
        else:document={}
        result=curate(document,engine)
        if args.commit_sha:result['testedCommitSHA']=args.commit_sha
        (args.output/f'core-journey-{engine}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(f'{engine}: {result["status"]}; {len(result["checkpoints"])} named checkpoints')

if __name__=='__main__':main()
