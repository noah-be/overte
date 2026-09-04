'use strict';

const electron = require('electron');
const path = require('node:path');

electron.app.commandLine.appendSwitch('headless');
electron.app.disableHardwareAcceleration();

const pages = ['content-update.html', 'downloader.html', 'log.html', 'splash.html'];
const failures = [];

electron.ipcMain.on('ready', function(event) {
    event.sender.send('update', {
        state: 'error',
        args: { message: 'smoke-test' }
    });
});
electron.ipcMain.on('setSize', function() {});
electron.ipcMain.on('log:get-files', function(event) {
    event.returnValue = { ds: {}, ac: {} };
});
electron.ipcMain.on('log:open-directory', function() {});
electron.ipcMain.on('splash:get-config', function(event) {
    event.returnValue = { doNotShowSplash: false };
});
electron.ipcMain.on('splash:set-suppressed', function() {});
electron.ipcMain.on('downloader:close', function() {});

electron.app.whenReady().then(async function() {
    const windows = pages.map(function(page) {
        const window = new electron.BrowserWindow({
            show: false,
            webPreferences: {
                nodeIntegration: true,
                contextIsolation: false,
                sandbox: false,
                webSecurity: true,
                allowRunningInsecureContent: false
            }
        });
        window.webContents.on('did-fail-load', function(event, errorCode, errorDescription) {
            failures.push(page + ': ' + errorCode + ' ' + errorDescription);
        });
        window.webContents.on('render-process-gone', function(event, details) {
            failures.push(page + ': renderer exited (' + details.reason + ')');
        });
        window.webContents.on('console-message', function(event, details) {
            if (details.level === 'error') {
                failures.push(page + ': ' + details.message);
            }
        });
        return window;
    });

    try {
        await Promise.all(windows.map(function(window, index) {
            return window.loadFile(path.join(__dirname, '..', 'src', pages[index]));
        }));
        await new Promise(function(resolve) {
            setTimeout(resolve, 500);
        });
    } catch (error) {
        failures.push(error.stack || error.message);
    } finally {
        windows.forEach(function(window) {
            if (!window.isDestroyed()) {
                window.destroy();
            }
        });
    }

    if (failures.length) {
        console.error(failures.join('\n'));
        electron.app.exit(1);
    } else {
        console.log('Electron renderer smoke test passed for ' + pages.length + ' pages');
        electron.app.exit(0);
    }
});
