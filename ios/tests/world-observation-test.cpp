// SPDX-License-Identifier: Apache-2.0
#include "../render/WorldObservation.h"
#include <shared/IOSRuntimeLogging.h>
#include <QGuiApplication>
#include <QStandardPaths>
#include <QFile>
#include <QJsonDocument>
#include <QTimer>
#include <cassert>

// Substitute only the container directory. Run the actual startup registration,
// timer and atomic writer with real host Qt, never the user's Documents folder.
struct TestPaths {
    enum StandardLocation { DocumentsLocation };
    static QString writableLocation(StandardLocation) {
        return QString::fromUtf8(qgetenv("OVERTE_TEST_OUTPUT"));
    }
};
#define QStandardPaths TestPaths
#define Q_OS_IOS
#define OVERTE_IOS_E2E_TEST_BUILD
#include "../render/InstallWorldObservation.cpp"
#undef QStandardPaths

int main(int argc, char** argv) {
    QGuiApplication app(argc, argv);
    beginIOSRuntimeEntityEvidence();
    const auto generation = iosRuntimeEntityEvidenceGeneration();
    setExpectedIOSRuntimeEntities({ "private-test-entity" });
    recordIOSRuntimeRenderableEntity("private-test-entity");
    recordIOSRuntimeSceneEntity("private-test-entity", generation);
    recordIOSRuntimeDrawnEntity("private-test-entity");
    commitIOSRuntimeEntityEvidence();
    auto sample = overte::ios::worldObservation(true);
    assert(sample["expectedEntities"].toInt() == 1 && sample["drawnEntities"].toInt() == 1);
#if defined(OVERTE_IOS_WORLD_OBSERVATION_VERSION)
    assert(!recordIOSRuntimePresentedFrame(0, 1, true));
    assert(recordIOSRuntimePresentedFrame(generation, 42, true));
    assert(recordIOSRuntimePresentedFrame(generation, 43, false));
    recordIOSRuntimeSoftwareQmlImage(generation);
    sample = overte::ios::worldObservation(true);
    assert(sample["generation"] == QString::number(generation));
    assert(sample["acceptedPresentCalls"] == "1" && sample["rejectedPresentCalls"] == "1");
    assert(sample["lastPresentedFrame"] == "42" && sample["softwareQmlImagesProduced"] == "1");
    invalidateIOSRuntimeEntityEvidence();
    assert(!recordIOSRuntimePresentedFrame(generation, 44, true));
    assert(overte::ios::worldObservation(true)["generation"] == "0");
    beginIOSRuntimeEntityEvidence();
    setExpectedIOSRuntimeEntities({ "new-private-entity" });
    commitIOSRuntimeEntityEvidence(generation); // stale decoder cannot commit new world
    assert(!iosRuntimeEntityEvidenceSnapshot().committed);
    commitIOSRuntimeEntityEvidence(iosRuntimeEntityEvidenceGeneration());
    assert(!recordIOSRuntimePresentedFrame(generation, 45, true));
    assert(recordIOSRuntimePresentedFrame(iosRuntimeEntityEvidenceGeneration(), 46, true));
    recordIOSRuntimeSoftwareQmlImage(generation);
    assert(overte::ios::worldObservation(true)["softwareQmlImagesProduced"] == "0");
#else
    assert(sample["producer"] == "entity-counts-only" && !sample.contains("generation"));
#endif
    sample = overte::ios::worldObservation(false);
    assert(!sample["armed"].toBool() && sample["expectedEntities"] == 0);
    auto raw = QJsonDocument(sample).toJson();
    assert(!raw.contains("private-") && !raw.contains("accepted\":true"));
    const auto directory = TestPaths::writableLocation(TestPaths::DocumentsLocation);
    sample["elapsedMs"] = "1"; sample["expired"] = false;
    assert(overte::ios::writeWorldObservation(directory, sample));
    assert(!overte::ios::writeWorldObservation(directory + "/missing", sample));
    assert(!overte::ios::writeWorldObservation(directory, QJsonObject {{ "large", QString(5000, 'x') }}));
    QTimer::singleShot(1100, &app, &QCoreApplication::quit);
    app.exec();
    QFile file(directory + "/overte-world-observation.json");
    assert(file.open(QIODevice::ReadOnly));
    const auto retained = QJsonDocument::fromJson(file.readAll()).object();
    if (app.arguments().contains("--ios-world-evidence")) {
        assert(retained["elapsedMs"].toString().toLongLong() >= 500);
    } else {
        assert(retained["elapsedMs"] == "1"); // no opted-in startup write
    }
    assert(retained["status"] == "OBSERVATION_NOT_ACCEPTANCE");
}
