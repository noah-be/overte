// SPDX-License-Identifier: Apache-2.0
import test from 'node:test';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

test('laboratory browser opening verifies Chrome before starting services and never selects a system browser',()=>{
 execFileSync('python3',['-B','-m','unittest','-v','test_chrome_browser.py'],{
  cwd:fileURLToPath(new URL('../lab/',import.meta.url)),encoding:'utf8',timeout:30000,
 });
});
