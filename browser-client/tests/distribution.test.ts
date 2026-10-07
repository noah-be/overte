// SPDX-License-Identifier: Apache-2.0
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, symlink, rm} from 'node:fs/promises';
import {execFileSync, spawnSync} from 'node:child_process';
import {tmpdir} from 'node:os';
import path from 'node:path';

async function fixture() {
    const repository = await mkdtemp(path.join(tmpdir(),'overte-distribution-test-'));
    await mkdir(path.join(repository,'browser-client/tools'),{recursive:true});
    await mkdir(path.join(repository,'browser-client/dist'),{recursive:true});
    await writeFile(path.join(repository,'browser-client/tools/package.py'),await readFile(new URL('../tools/package.py',import.meta.url)));
    await writeFile(path.join(repository,'browser-client/package.json'),'{"version":"0.1.0"}');
    await writeFile(path.join(repository,'browser-client/dist/index.html'),'<html>Actual built fixture bytes</html>');
    await writeFile(path.join(repository,'.gitignore'),'browser-client/dist/\nbuild/\n');
    const git = (...args:string[]) => execFileSync('git',args,{cwd:repository,stdio:'pipe'});
    git('init','--initial-branch=feature/main/distribution-test'); git('add','.');
    git('-c','user.name=Distribution Test','-c','user.email=distribution-test@example.invalid','commit','-m','Create isolated distribution fixture');
    const pack = () => spawnSync('python3',['browser-client/tools/package.py'],{cwd:repository,encoding:'utf8'});
    return {repository,git,pack};
}

test('distribution refuses omitted new modules and includes staged source with exact manifest and repeatable bytes', async() => {
    const {repository,git,pack} = await fixture();
    try {
        await writeFile(path.join(repository,'browser-client/native-world.js'),'export const realModule = "new runtime source";\n');
        const omitted = pack(); assert.notEqual(omitted.status,0); assert.match(omitted.stderr,/untracked modules would be omitted/);
        git('add','browser-client/native-world.js');
        const first = pack(); assert.equal(first.status,0,first.stderr);
        const result = JSON.parse(first.stdout); assert.equal(result.uncommittedChanges,true);
        const artifact = path.join(repository,'build/browser-client-distribution',result.filename);
        const audit = JSON.parse(execFileSync('python3',['-c',`
import hashlib,json,sys,tarfile
with tarfile.open(sys.argv[1]) as archive:
    manifest=json.load(archive.extractfile('browser-client/BUILD_INFO.json'))
    for name,digest in manifest['files'].items():
        assert hashlib.sha256(archive.extractfile(name).read()).hexdigest()==digest
    assert archive.extractfile('browser-client/native-world.js').read()==b'export const realModule = "new runtime source";\\n'
    assert archive.extractfile('browser-client/dist/index.html').read()==b'<html>Actual built fixture bytes</html>'
    print(json.dumps({'verifiedFiles':len(manifest['files'])}))
`,artifact],{encoding:'utf8'}));
        assert.equal(audit.verifiedFiles,4);
        const repeat = pack(); assert.equal(repeat.status,0,repeat.stderr);
        assert.equal(JSON.parse(repeat.stdout).sha256,result.sha256);
    } finally { await rm(repository,{recursive:true,force:true}); }
});
test('distribution never follows a generated asset symlink into an operator file', async() => {
    const {repository,pack} = await fixture();
    try {
        const privateFile = path.join(repository,'operator-private.txt');
        await writeFile(privateFile,'synthetic operator data that must not enter the archive');
        await symlink(privateFile,path.join(repository,'browser-client/dist/private.txt'));
        const result = pack(); assert.notEqual(result.status,0); assert.match(result.stderr,/Only regular repository files/);
    } finally { await rm(repository,{recursive:true,force:true}); }
});
