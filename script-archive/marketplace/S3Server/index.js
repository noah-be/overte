//
//  index.js
//  examples
//
//  Created by Eric Levin on 11/10/2015.
//  Copyright 2013 High Fidelity, Inc.
//
//  This is a simple REST API that allows an interface client script to get a list of files paths from an S3 bucket.
//  To change your bucket, modify line 34 to your desired bucket.
//  Please refer to  http://docs.aws.amazon.com/AWSJavaScriptSDK/guide/node-configuring.html
//  for instructions on how to configure the SDK to work with your bucket.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html

var express = require('express');
var S3Client = require('@aws-sdk/client-s3').S3Client;
var ListObjectsV2Command = require('@aws-sdk/client-s3').ListObjectsV2Command;

var s3 = new S3Client({
    region: "us-east-1"
});

function createApp(s3Client) {
    var app = express();

    app.set('port', (process.env.PORT || 5000));

    app.get('/', async function(req, res) {
        var params = {
            Bucket: "hifi-public",
            MaxKeys: 10
        };
        if (typeof req.query.assetDir === 'string') {
            params.StartAfter = req.query.assetDir;
        }

        try {
            var data = await s3Client.send(new ListObjectsV2Command(params));
            var keys = (data.Contents || []).map(function(item) {
                return item.Key;
            });
            res.json({
                urls: keys
            });
        } catch (error) {
            console.log(error, error.stack);
            res.status(502).send("ERROR");
        }
    });

    return app;
}

var app = createApp(s3);

if (require.main === module) {
    app.listen(app.get('port'), function() {
        console.log('Node app is running on port', app.get('port'));
    });
}

module.exports = {
    createApp: createApp
};
