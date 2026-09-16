//
//  OpenEXRReader.cpp
//  image/src/image
//
//  Created by Olivier Prat
//  Copyright 2019 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "OpenEXRReader.h"
#include "DecodeLimits.h"

#include "TextureProcessing.h"
#include "ImageLogging.h"

#include <QIODevice>
#include <QDebug>

#include <OpenEXR/ImfIO.h>
#include <OpenEXR/ImfRgbaFile.h>
#include <OpenEXR/ImfArray.h>
#include <OpenEXR/ImfTestFile.h>
#include <OpenEXR/ImfInt64.h>

class QIODeviceImfStream : public Imf::IStream {
public:

    QIODeviceImfStream(QIODevice& device, const std::string& filename) :
        Imf::IStream(filename.c_str()), _device(device) {
    }

    bool read(char c[/*n*/], int n) override {
        if (_device.read(c, n) <= 0) {
            qWarning(imagelogging) << "OpenEXR - in file " << fileName() << " : " << _device.errorString();
            return false;
        }
        return true;
    }

    uint64_t tellg() override {
        return _device.pos();
    }

    void seekg(uint64_t pos) override {
        _device.seek(pos);
    }

    void clear() override {
        // Not much to do
    }

private:

    QIODevice&  _device;
};

image::Image image::readOpenEXR(QIODevice& content, const std::string& filename, std::uint64_t maxDecodedPixels) {
    QIODeviceImfStream device(content, filename);

    if (Imf::isOpenExrFile(device)) {
        Imf::RgbaInputFile file(device);
        Imath::Box2i viewport = file.dataWindow();
        Imf::Array2D<Imf::Rgba> pixels;
        const std::int64_t width64 = std::int64_t(viewport.max.x) - viewport.min.x + 1;
        const std::int64_t height64 = std::int64_t(viewport.max.y) - viewport.min.y + 1;
        if (!decodedImageFits(width64, height64, maxDecodedPixels)) {
            qWarning(imagelogging) << "IMAGE_DECODE_REJECT dimensions" << width64 << height64;
            return QImage();
        }
        const int width = static_cast<int>(width64);
        const int height = static_cast<int>(height64);

        pixels.resizeErase(height, width);

        file.setFrameBuffer(&pixels[0][0] - viewport.min.x - viewport.min.y * width, 1, width);
        file.readPixels(viewport.min.y, viewport.max.y);

        Image image{ width, height, Image::Format_PACKED_FLOAT };
        auto packHDRPixel = getHDRPackingFunction();

        for (int y = 0; y < height; y++) {
            const auto srcScanline = pixels[y];
            gpu::uint32* dstScanline = (gpu::uint32*) image.editScanLine(y);

            for (int x = 0; x < width; x++) {
                const auto& srcPixel = srcScanline[x];
                auto& dstPixel = dstScanline[x];
                glm::vec3 floatPixel{ srcPixel.r, srcPixel.g, srcPixel.b };

                dstPixel = packHDRPixel(floatPixel);
            }
        }
        return image;
    } else {
        qWarning(imagelogging) << "OpenEXR - File " << filename.c_str() << " doesn't have the proper format";
    }
    return QImage();
}
