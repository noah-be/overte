var ipcRenderer = require('electron').ipcRenderer;

ready = function() {
    window.$ = require('./vendor/jquery/jquery-2.1.4.min.js');

    var userConfig = ipcRenderer.sendSync('splash:get-config');
    $('#suppress-splash').prop('checked', userConfig.doNotShowSplash);
    $('#suppress-splash').change(function() {
        console.log("updating");
        ipcRenderer.send('splash:set-suppressed', $(this).is(':checked'));
    });
}
