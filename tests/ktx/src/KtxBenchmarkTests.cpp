//
//  Created by Bradley Austin Davis on 2016/07/01
//  Copyright 2014 High Fidelity, Inc.
//
//  Distributed under the Apache License, Version 2.0.
//  See the accompanying file LICENSE or http://www.apache.org/licenses/LICENSE-2.0.html
//

#include "KtxBenchmarkTests.h"

#include <mutex>

#include <QtTest/QtTest>

#include <ktx/KTX.h>
#include <gpu/Texture.h>
#include <image/Image.h>
#include <image/TextureProcessing.h>
#include <QDebug>
#include <QDir>
#include <QImageReader>
#include <QTextStream>


QTEST_GUILESS_MAIN(KtxBenchmarks)

QStringList png_images{
    "scripts/developer/tests/cube_texture.png",
    "scripts/system/assets/images/materials/GridPattern.png",
    "scripts/simplifiedUI/simplifiedEmote/emojiApp/resources/images/emojis/512px/1f92c.png",
    "scripts/system/assets/images/Particle-Sprite-Smoke-1.png",
    "scripts/system/assets/images/grabsprite-3.png",
    "scripts/system/html/img/snapshotIcon.png",
};

QStringList jpg_images{
    "interface/resources/snapshot/img/no-image.jpg",
    "scripts/system/assets/images/textures/dirt.jpeg",
};


QString test_texture = "scripts/developer/tests/cube_texture.png";

QString getRootPath() {
#ifdef OVERTE_TEST_SOURCE_ROOT
    return QDir::cleanPath(QString::fromUtf8(OVERTE_TEST_SOURCE_ROOT));
#else
#error "KtxBenchmarkTests requires OVERTE_TEST_SOURCE_ROOT"
#endif
}

QString fixturePath(const QString& relativePath) {
    return QDir(getRootPath()).filePath(relativePath);
}

void benchmarkImage(const QString &path) {

    QImage image(path);
    if ( image.isNull() ) {
        qCritical() << "Failed to load " << path;
        return;
    }

    qInfo() << "Testing " << path << ", size " << image.size() << ", depth" << image.depth();

    QBENCHMARK {
        QImage image(path);
    }
}

QSize imageSize(const QString &path) {
    QImage image(path);
    if ( image.isNull() ) {
        qCritical() << "Failed to load " << path;
        return QSize(0,0);
    }

    return image.size();
}

gpu::TexturePointer loadTexture(const QString &path) {
    QImage image(path);
    std::atomic<bool> abortSignal;
    if ( !image.isNull() ) {
        qDebug() << "Loaded " << path << "; " << image.size();
    }
    return image::TextureUsage::process2DTextureColorFromImage(std::move(image), path.toStdString(), true, gpu::BackendTarget::GL45, true, abortSignal);
}

void KtxBenchmarks::initTestCase() {
    QList<QByteArray> supported = QImageReader::supportedImageFormats();

    QString formats;
    QTextStream ts(&formats);

    for(auto format : supported) {
        ts << format;
        ts << ", ";
    }

    qDebug() << "Qt supports the following image formats: " << formats;

}

void KtxBenchmarks::cleanupTestCase() {
}

void KtxBenchmarks::benchmarkPNG_data() {
    QTest::addColumn<QString>("filename");

    for(QString filename : png_images) {
        QString full_name = fixturePath(filename);
        QImage image(full_name);
        QVERIFY2(!image.isNull(), qPrintable("Unable to load PNG benchmark fixture: " + full_name));
        QSize sz = image.size();
        QString desc = QString("%1 x %2").arg(sz.width()).arg(sz.height());

        QTest::newRow( desc.toUtf8() ) << full_name;
    }
}

void KtxBenchmarks::benchmarkPNG() {
    QFETCH(QString, filename);

    QBENCHMARK {
        QImage image(filename);
    }
}

void KtxBenchmarks::benchmarkJPG_data() {
    QTest::addColumn<QString>("filename");

    for(QString filename : jpg_images) {
        QString full_name = fixturePath(filename);
        QImage image(full_name);
        QVERIFY2(!image.isNull(), qPrintable("Unable to load JPEG benchmark fixture: " + full_name));
        QSize sz = image.size();
        QString desc = QString("%1 x %2").arg(sz.width()).arg(sz.height());

        QTest::newRow( desc.toUtf8() ) << full_name;
    }
}

void KtxBenchmarks::benchmarkJPG() {
    QFETCH(QString, filename);

    QBENCHMARK {
        QImage image(filename);
    }
}

void KtxBenchmarks::benchmarkCreateTexture() {
    const QString TEST_IMAGE = fixturePath(test_texture);

    QBENCHMARK {
        gpu::TexturePointer testTexture = loadTexture(TEST_IMAGE);

        if (!testTexture) {
            qWarning() << "Failed to process2DTextureColorFromImage:" << TEST_IMAGE;
            QFAIL("Failed to process2DTextureColorFromImage");
        }
    }
}

void KtxBenchmarks::benchmarkSerializeTexture() {
    const QString TEST_IMAGE = fixturePath(test_texture);
    gpu::TexturePointer testTexture = loadTexture(TEST_IMAGE);

    if (!testTexture) {
        qWarning() << "Failed to process2DTextureColorFromImage:" << TEST_IMAGE;
        QFAIL("Failed to process2DTextureColorFromImage");
    }

    qDebug() << "Test texture is " << testTexture->getWidth() << " x " << testTexture->getHeight();

    QBENCHMARK {
        auto ktxMemory = gpu::Texture::serialize(*testTexture, glm::ivec2(testTexture->getWidth(), testTexture->getHeight()));
        QVERIFY(ktxMemory.get());
    }
}

void KtxBenchmarks::benchmarkWriteKTX() {
    const QString TEST_IMAGE = fixturePath(test_texture);
    gpu::TexturePointer testTexture = loadTexture(TEST_IMAGE);

    if (!testTexture) {
        qWarning() << "Failed to process2DTextureColorFromImage:" << TEST_IMAGE;
        QFAIL("Failed to process2DTextureColorFromImage");
    }

    qDebug() << "Test texture is " << testTexture->getWidth() << " x " << testTexture->getHeight();

    auto ktxMemory = gpu::Texture::serialize(*testTexture, glm::ivec2(testTexture->getWidth(), testTexture->getHeight()));
    QVERIFY(ktxMemory.get());

    QBENCHMARK {
        // Serialize the image to a file
        QTemporaryFile TEST_IMAGE_KTX;
        {
            const auto& ktxStorage = ktxMemory->getStorage();
            QVERIFY(ktx::KTX::validate(ktxStorage));
            QVERIFY(ktxMemory->isValid());

            auto& outFile = TEST_IMAGE_KTX;
            if (!outFile.open()) {
                QFAIL("Unable to open file");
            }
            auto ktxSize = ktxStorage->size();
            outFile.resize(ktxSize);
            auto dest = outFile.map(0, ktxSize);
            memcpy(dest, ktxStorage->data(), ktxSize);
            outFile.unmap(dest);
            outFile.close();
        }
    }
}
