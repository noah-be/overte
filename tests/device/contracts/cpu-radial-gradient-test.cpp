// SPDX-License-Identifier: Apache-2.0
#include <QGuiApplication>
#include <QQuickView>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QTest>
#include <QSignalSpy>
#include <QImage>
#include <cassert>
#include <cmath>

static QImage capture(QQuickItem* item) {
    QTest::qWait(80);
    auto result = item->grabToImage();
    assert(result);
    QSignalSpy ready(result.data(), &QQuickItemGrabResult::ready);
    assert(ready.wait(1000));
    assert(!result->image().isNull());
    return result->image();
}
static QColor sample(const QImage& image, double x, double y) {
    return image.pixelColor(qMin(image.width()-1, int(x*image.width())),
                            qMin(image.height()-1, int(y*image.height())));
}
static void checkPixels(const QImage& image, bool frame) {
    const auto center = sample(image, .5, .5);
    const auto horizontal = sample(image, .75, .5);
    const auto vertical = sample(image, .5, .75);
    if (frame) {
        assert(center.alpha() > 246);
        assert(horizontal.alpha() > 78 && horizontal.alpha() < 94);
        assert(std::abs(horizontal.alpha()-vertical.alpha()) <= 3);
        assert(sample(image, .99, .5).alpha() < 5);
        assert(sample(image, .5, .99).alpha() < 5);
        assert(sample(image, .01, .01).alpha() == 0);
    } else {
        assert(center.alpha() == 255 && center.red() >= 37);
        assert(horizontal.red() >= 27 && horizontal.red() <= 30);
        assert(std::abs(horizontal.red()-vertical.red()) <= 1);
        assert(sample(image, .99, .5).red() >= 18 && sample(image, .99, .5).red() <= 21);
        assert(sample(image, .01, .01).red() >= 10 && sample(image, .01, .01).red() <= 13);
    }
}
int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    assert(argc == 3);
    const bool frame = QString::fromLocal8Bit(argv[2]) == "frame";
    QQuickView view;
    view.setColor(Qt::transparent);
    view.setSource(QUrl::fromLocalFile(QString::fromLocal8Bit(argv[1])));
    assert(view.status() == QQuickView::Ready);
    view.show();
    auto root = view.rootObject();
    auto radial = root->findChild<QQuickItem*>("radial");
    assert(radial);
    assert(radial->isVisible());
    if (frame) {
        assert(qFuzzyCompare(radial->width(), 1.66 * root->width()));
        assert(qFuzzyCompare(radial->height(), 1.66 * root->height()));
        assert(qAbs(radial->x() - (root->width()-radial->width())/2) < .01);
        assert(qAbs(radial->y() - (root->height()/2-.375*radial->height())) < .01);
    }
    checkPixels(capture(radial), frame);
    root->setWidth(280);
    root->setHeight(360);
    checkPixels(capture(radial), frame);
    if (frame) {
        root->setProperty("gradientsSupported", false);
        assert(!radial->isVisible());
        root->setProperty("gradientsSupported", true);
        assert(radial->isVisible());
        root->setFocus(false);
        assert(!radial->isVisible());
        root->setFocus(true);
        auto content = root->property("content").value<QObject*>();
        content->setProperty("visible", false);
        assert(!radial->isVisible());
        content->setProperty("visible", true);
    }
    view.hide(); QTest::qWait(30); view.show();
    checkPixels(capture(radial), frame);
    // Property replacement triggers redraw; a removed fill must not retain pixels.
    radial->setProperty("stops", QVariantList{});
    auto cleared = capture(radial);
    assert(sample(cleared, .5, .5).alpha() == 0);
}
