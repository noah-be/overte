// SPDX-License-Identifier: Apache-2.0
.pragma library

// Explicit finite separable Gaussian alpha filter. Input/output are public
// Canvas ImageData; image RGB never influences the shadow mask.
function paintShadow(context, image, radius, offsetX, offsetY, color) {
    var width = image.width, height = image.height;
    var reach = Math.ceil(radius);
    var weights = [];
    var sum = 0;
    var sigma = Math.max(0.5, radius / 2);
    for (var k = -reach; k <= reach; ++k) {
        var weight = Math.exp(-(k * k) / (2 * sigma * sigma));
        weights.push(weight);
        sum += weight;
    }
    for (var k = 0; k < weights.length; ++k) weights[k] /= sum;
    var horizontal = new Float32Array(width * height);
    var blurred = new Float32Array(width * height);
    for (var y = 0; y < height; ++y) {
        for (var x = 0; x < width; ++x) {
            var alpha = 0;
            for (var k = -reach; k <= reach; ++k) {
                var column = x + k;
                if (column >= 0 && column < width)
                    alpha += image.data[4 * (y * width + column) + 3] * weights[k + reach];
            }
            horizontal[y * width + x] = alpha;
        }
    }
    for (var y = 0; y < height; ++y) {
        for (var x = 0; x < width; ++x) {
            var alpha = 0;
            for (var k = -reach; k <= reach; ++k) {
                var row = y + k;
                if (row >= 0 && row < height)
                    alpha += horizontal[row * width + x] * weights[k + reach];
            }
            blurred[y * width + x] = alpha;
        }
    }
    function at(x, y) {
        return x >= 0 && x < width && y >= 0 && y < height ? blurred[y * width + x] : 0;
    }
    for (var y = 0; y < height; ++y) {
        for (var x = 0; x < width; ++x) {
            var sx = x - offsetX, sy = y - offsetY;
            var left = Math.floor(sx), top = Math.floor(sy);
            var fx = sx - left, fy = sy - top;
            var alpha = (at(left, top) * (1 - fx) + at(left + 1, top) * fx) * (1 - fy)
                + (at(left, top + 1) * (1 - fx) + at(left + 1, top + 1) * fx) * fy;
            var index = 4 * (y * width + x);
            image.data[index] = Math.round(color.r * 255);
            image.data[index + 1] = Math.round(color.g * 255);
            image.data[index + 2] = Math.round(color.b * 255);
            image.data[index + 3] = Math.round(alpha * color.a);
        }
    }
    context.putImageData(image, 0, 0, 0, 0, width, height);
}
