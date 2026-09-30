// SPDX-License-Identifier: Apache-2.0
// Await exit before releasing a session's process slot or deleting its private files.
export async function terminateProcess(child, graceMilliseconds = 3000) {
    if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
    await new Promise(resolve => {
        const finished = () => { clearTimeout(timer); resolve(); };
        const timer = setTimeout(() => { child.kill('SIGKILL'); }, graceMilliseconds);
        child.once('exit', finished);
        child.kill('SIGTERM');
    });
}
