#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Observe only exact distro namespace profiles; never alter or bypass policy."""
import hashlib,json,os,re,shutil,subprocess
from pathlib import Path

PROFILES={'bwrap-userns-restrict':'apparmor','unshare-userns-restrict':'apparmor-profiles'}
LOADED_NAMES={'bwrap','unshare','bwrap-userns-restrict','unshare-userns-restrict','unpriv_bwrap','unpriv_unshare'}

def read_scalar(path):
    try:
        value=Path(path).read_text().strip()
        return value if len(value)<=128 else 'oversized'
    except OSError:return 'unavailable'

def run(arguments):
    try:
        result=subprocess.run(arguments,capture_output=True,text=True,timeout=5,env={**os.environ,'LC_ALL':'C'})
        return result.returncode,result.stdout[:1024*1024]
    except (OSError,subprocess.TimeoutExpired):return None,''

def main():
    report={'scope':'Read-only runner AppArmor package/profile diagnostic; normal native/sandbox preflight remains mandatory',
        'policyChanges':'none','apparmorEnabled':read_scalar('/sys/module/apparmor/parameters/enabled'),
        'restrictUnprivilegedUserns':read_scalar('/proc/sys/kernel/apparmor_restrict_unprivileged_userns'),
        'restrictUnprivilegedUnconfined':read_scalar('/proc/sys/kernel/apparmor_restrict_unprivileged_unconfined'),
        'processProfileIsUnconfined':read_scalar('/proc/self/attr/current')=='unconfined','tools':{},'profiles':{}}
    for tool in ('bwrap','unshare'):
        path=shutil.which(tool);canonical=str(Path(path).resolve()) if path else None
        report['tools'][tool]={'present':bool(path),'distroExecutable':canonical==f'/usr/bin/{tool}'}
    code,versions=run(['dpkg-query','--show','--showformat=${Package}\t${Version}\n','apparmor','apparmor-profiles','bubblewrap','util-linux'])
    report['packageQuerySucceeded']=code==0
    report['packageVersions']={line.split('\t',1)[0]:line.split('\t',1)[1] for line in versions.splitlines() if re.fullmatch(r'[a-z0-9-]+\t[A-Za-z0-9.+:~_-]+',line)}
    try:loaded=Path('/sys/kernel/security/apparmor/profiles').read_text()
    except OSError:loaded=None
    report['loadedProfilesReadable']=loaded is not None
    if loaded is not None:
        report['relevantLoadedProfiles']=[{'profile':name,'mode':mode} for name,mode in re.findall(r'^([^\n]+) \(([^\n]+)\)$',loaded,re.M) if name in LOADED_NAMES]
    for name,package in PROFILES.items():
        path=Path('/etc/apparmor.d')/name
        item={'present':path.is_file(),'disabledMarkerPresent':os.path.lexists(Path('/etc/apparmor.d/disable')/name),'package':package}
        if path.is_file():
            content=path.read_bytes();item['sha256']=hashlib.sha256(content).hexdigest()
            text=content.decode('utf-8',errors='replace')
            item['declaredABI']=re.findall(r'^\s*abi\s+<abi/([0-9]+\.[0-9]+)>\s*,',text,re.M)[:4]
            expected_profile='bwrap' if name=='bwrap-userns-restrict' else 'unshare'
            item['expectedMainProfileDeclared']=bool(re.search(r'^\s*profile\s+'+re.escape(expected_profile)+r'\s',text,re.M))
            owner_code,owner=run(['dpkg-query','--search',str(path)])
            item['expectedPackageOwnsFile']=owner_code==0 and any(line.startswith(package+': ') for line in owner.splitlines())
            config_code,configs=run(['dpkg-query','--show','--showformat=${Conffiles}\n',package])
            found=re.search(r'^\s*'+re.escape(str(path))+r'\s+([a-f0-9]{32})(?:\s|$)',configs,re.M)
            item['matchesRecordedPackageConffile']=bool(config_code==0 and found and hashlib.md5(content).hexdigest()==found.group(1))
        report['profiles'][name]=item
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
