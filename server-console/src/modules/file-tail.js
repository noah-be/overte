'use strict';

const EventEmitter = require('events').EventEmitter;
const fs = require('fs');
const util = require('util');

function FileTail(filePath, separator, options) {
    EventEmitter.call(this);
    this.filePath = filePath;
    this.separator = separator || '\n';
    this.position = options && options.start ? options.start : 0;
    this.interval = options && options.interval ? options.interval : 500;
    this.remainder = '';
    this.timer = null;
    this.reading = false;
}
util.inherits(FileTail, EventEmitter);

FileTail.prototype.watch = function() {
    if (!this.timer) {
        this.timer = setInterval(this._poll.bind(this), this.interval);
        this._poll();
    }
};

FileTail.prototype.unwatch = function() {
    if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
    }
};

FileTail.prototype._poll = function() {
    if (this.reading) {
        return;
    }
    this.reading = true;
    fs.stat(this.filePath, function(statError, stat) {
        if (statError) {
            this.reading = false;
            this.emit('error', statError);
            return;
        }
        if (stat.size < this.position) {
            this.position = 0;
            this.remainder = '';
        }
        if (stat.size === this.position) {
            this.reading = false;
            return;
        }

        var length = stat.size - this.position;
        var buffer = Buffer.alloc(length);
        fs.open(this.filePath, 'r', function(openError, descriptor) {
            if (openError) {
                this.reading = false;
                this.emit('error', openError);
                return;
            }
            fs.read(descriptor, buffer, 0, length, this.position, function(readError, bytesRead) {
                fs.close(descriptor, function() {});
                this.reading = false;
                if (readError) {
                    this.emit('error', readError);
                    return;
                }
                this.position += bytesRead;
                var parts = (this.remainder + buffer.toString('utf8', 0, bytesRead)).split(this.separator);
                this.remainder = parts.pop();
                parts.forEach(function(line) {
                    this.emit('line', line);
                }, this);
            }.bind(this));
        }.bind(this));
    }.bind(this));
};

module.exports = FileTail;
