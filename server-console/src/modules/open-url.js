const childProcess = require('child_process');

// Keep untrusted URLs out of a shell command. macOS' `open` receives each value
// as a distinct argument, so shell metacharacters in a URL remain data.
exports.openUrl = function(bundleId, url, execFile) {
    var run = execFile || childProcess.execFile;
    return run('open', ['-b', bundleId, '--args', '--url', url]);
};
