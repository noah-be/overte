"""Run the production collision experiment and actual recursive entity locking."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[4]


def method(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def driver():
    source = (ROOT / 'libraries/entities-renderer/src/RenderableModelEntityItem.cpp').read_text()
    mode = method(source, 'int phoneCollisionPriorityMode()')
    block = source[source.index('    // Phone collision priority experiment:'):
                   source.index('    // End Phone collision priority experiment.')]
    model = (ROOT / 'libraries/entities/src/ModelEntityItem.cpp.in').read_text()
    entity = (ROOT / 'libraries/entities/src/EntityItem.cpp.in').read_text()
    getters = '\n'.join(method(model, signature) for signature in (
        'ShapeType ModelEntityItem::getShapeType()',
        'bool ModelEntityItem::hasCompoundShapeURL()',
        'QString ModelEntityItem::getCompoundShapeURL()',
        'QString ModelEntityItem::getModelURL()'))
    getters = getters.replace('ModelEntityItem::', 'RenderableModelEntityItem::')
    getters += '\n' + method(entity, 'bool EntityItem::getCollisionless()').replace(
        'EntityItem::', 'RenderableModelEntityItem::')
    getters += '\n' + method(source, 'QString RenderableModelEntityItem::getCollisionShapeURL()')
    macros = (ROOT / 'libraries/entities/src/EntityItemPropertiesMacros.h').read_text()
    basic = macros[macros.index('#define DEFINE_VARIABLE_BASIC('):
                   macros.index('#define DEFINE_VARIABLE_BASIC_REF(')]
    return r'''
#include <cassert>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstring>
#include <future>
#include <limits>
#include <memory>
#include <thread>
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QThread>
#include <QUrl>
#include "libraries/shared/src/shared/ReadWriteLockable.h"
#include "libraries/networking/src/PhoneResourcePriorityMap.h"
uint qHash(const QPointer<QObject>& value, uint seed) {
    return qHash(value.data(), static_cast<size_t>(seed));
}
bool diagnostics = true;
std::string property = "2";
constexpr int PROP_VALUE_MAX = 92;
constexpr float EPSILON = 0.00001f;
int __system_property_get(const char* name, char* value) {
    assert(std::string(name) == "debug.overte.loading.collision_priority");
    std::strcpy(value, property.c_str());
    return int(property.size());
}
bool phoneLoadingDiagnosticsEnabled() { return diagnostics; }
#define PHONE_LOADING(...) do {} while (false)
''' + mode + '\n' + basic + r'''
enum ShapeType { SHAPE_TYPE_NONE, SHAPE_TYPE_COMPOUND, SHAPE_TYPE_SIMPLE_COMPOUND, SHAPE_TYPE_STATIC_MESH };
class Resource : public QObject {
public:
    static PhoneResourcePriorityMap maps;
    PhoneResourcePriorityMap::Map operators;
    bool loaded = false;
    bool failed = false;
    int installed = 0;
    bool isLoaded() const { return loaded; }
    bool isFailed() const { return failed; }
    void setLoadPriorityOperator(const QPointer<QObject>& owner, std::function<float()> callback) {
        assert(QThread::currentThread() == thread());
        if (!failed) { maps.set(operators, owner, callback); ++installed; }
    }
    float priority() { return maps.priority(operators); }
};
PhoneResourcePriorityMap Resource::maps;
class RenderableModelEntityItem : public QObject, public ReadWriteLockable,
        public std::enable_shared_from_this<RenderableModelEntityItem> {
public:
    QSharedPointer<Resource> _collisionGeometryResource;
    ShapeType _shapeType = SHAPE_TYPE_COMPOUND;
    bool _dynamic = false;
    bool _collisionless = false;
    bool domain = true;
    QString _compoundShapeURL = "https://example.invalid/collision.obj";
    QString _modelURL = _compoundShapeURL;
    auto getThisPointer() { return shared_from_this(); }
    ShapeType getShapeType() const;
    bool hasCompoundShapeURL() const;
    QString getCompoundShapeURL() const;
    QString getModelURL() const;
    QString getCollisionShapeURL() const;
    bool getCollisionless() const;
    bool isDomainEntity() const { return domain; }
    DEFINE_VARIABLE_BASIC(LoadPriority, loadPriority, float, 0.0f);
public:
    void registerPriority() {
        const auto collisionShapeURL = getCollisionShapeURL();
''' + block + r'''
    }
};
''' + getters + r'''
int main(int argc, char** argv) {
    QCoreApplication app(argc, argv);
    if (argc == 4) {
        diagnostics = std::string(argv[1]) == "1";
        property = argv[2];
        assert(phoneCollisionPriorityMode() == std::stoi(argv[3]));
        auto entity = std::make_shared<RenderableModelEntityItem>();
        auto resource = QSharedPointer<Resource>::create();
        entity->_collisionGeometryResource = resource;
        entity->registerPriority();
        QCoreApplication::processEvents();
        const int mode = std::stoi(argv[3]);
        assert(resource->installed == (mode != 0));
        assert(resource->priority() == (mode == 2 ? 9.5f : 0.0f));
        entity->setLoadPriority(7.0f);
        assert(resource->priority() == (mode ? 7.0f : 0.0f));
        return 0;
    }
    auto entity = std::make_shared<RenderableModelEntityItem>();
    auto resource = QSharedPointer<Resource>::create();
    entity->_collisionGeometryResource = resource;
    // Registration from a foreign thread must only install on Resource's
    // thread, after the event loop runs. Pointer configuration is stable.
    std::thread registration([&] { entity->registerPriority(); });
    registration.join();
    assert(resource->installed == 0);
    QCoreApplication::processEvents();
    assert(resource->installed == 1);
    assert(resource->priority() == 9.5f);
    entity->setLoadPriority(-7.0f);
    assert(resource->priority() == -7.0f);
    entity->setLoadPriority(22.0f);
    assert(resource->priority() == 22.0f);
    entity->setLoadPriority(std::numeric_limits<float>::infinity());
    assert(resource->priority() == 0.0f);
    entity->setLoadPriority(std::numeric_limits<float>::quiet_NaN());
    assert(resource->priority() == 0.0f);
    entity->setLoadPriority(0.0f);
    entity->domain = false;
    assert(resource->priority() == 0.0f);
    entity->domain = true;
    entity->_collisionless = true;
    assert(resource->priority() == 0.0f);
    entity->_collisionless = false;
    entity->_compoundShapeURL += ".replaced";
    assert(resource->priority() == 0.0f);
    entity->_compoundShapeURL = entity->_modelURL;
    entity->_shapeType = SHAPE_TYPE_SIMPLE_COMPOUND;
    assert(resource->priority() == 0.0f); // same URL, different shape
    entity->_shapeType = SHAPE_TYPE_NONE;
    assert(resource->priority() == 0.0f);
    entity->_shapeType = SHAPE_TYPE_COMPOUND;

    // A writer holding the entity lock must not block scheduler evaluation.
    std::promise<void> acquired, release;
    auto released = release.get_future();
    std::thread writer([&] {
        entity->withWriteLock([&] { acquired.set_value(); released.wait(); });
    });
    acquired.get_future().wait();
    assert(resource->priority() == 0.0f);
    release.set_value();
    writer.join();
    assert(resource->priority() == 9.5f);

    // The actual getters DO acquire nested read locks. Verify recursive
    // acquisition, including the callback's try-read, while a writer waits.
    std::thread waitingWriter;
    std::atomic<bool> writerEntered { false };
    assert(entity->withTryReadLock([&] {
        std::promise<void> attempting;
        auto attempted = attempting.get_future();
        waitingWriter = std::thread([&, attempting = std::move(attempting)]() mutable {
            assert(!entity->getLock().tryLockForWrite());
            attempting.set_value();
            entity->withWriteLock([&] { writerEntered = true; });
        });
        attempted.wait();
        std::this_thread::sleep_for(std::chrono::milliseconds(20));
        assert(!writerEntered);
        assert(entity->getLoadPriority() == 0.0f);
        assert(entity->getCollisionShapeURL() == entity->_modelURL);
        assert(resource->priority() == 9.5f);
        assert(!writerEntered);
    }));
    waitingWriter.join();
    assert(writerEntered);

    // Destroying an entity before delivery must not install an operator or
    // prolong entity lifetime. Destroying a resource cancels queued delivery.
    auto gone = std::make_shared<RenderableModelEntityItem>();
    auto untouched = QSharedPointer<Resource>::create();
    gone->_collisionGeometryResource = untouched;
    std::weak_ptr<RenderableModelEntityItem> weakEntity = gone;
    gone->registerPriority();
    gone.reset();
    assert(weakEntity.expired());
    QCoreApplication::processEvents();
    assert(untouched->installed == 0);
    gone = std::make_shared<RenderableModelEntityItem>();
    auto doomed = QSharedPointer<Resource>::create();
    auto weakResource = doomed.toWeakRef();
    gone->_collisionGeometryResource = doomed;
    gone->registerPriority();
    gone->_collisionGeometryResource.reset();
    doomed.reset();
    assert(weakResource.isNull());
    QCoreApplication::processEvents();

    // Completion before queued registration must remain unmodified.
    auto completed = QSharedPointer<Resource>::create();
    gone->_collisionGeometryResource = completed;
    gone->registerPriority();
    completed->loaded = true;
    QCoreApplication::processEvents();
    assert(completed->installed == 0);
    completed->loaded = false;
    completed->failed = true;
    gone->registerPriority();
    QCoreApplication::processEvents();
    assert(completed->installed == 0);
    // No strong entity cycle after successful operator registration either.
    weakEntity = entity;
    entity.reset();
    assert(weakEntity.expired());
    resource->priority(); // prunes the now-null QObject owner
    assert(resource->priority() == 0.0f);
}
'''


class CollisionPriorityTest(unittest.TestCase):
    def test_production_registration_policy_lifetime_and_recursive_locking(self):
        flags = shlex.split(subprocess.check_output(
            ['pkg-config', '--cflags', '--libs', 'Qt6Core'], text=True))
        with tempfile.TemporaryDirectory(prefix='phone-collision-priority-') as scratch:
            path = Path(scratch)
            (path / 'driver.cpp').write_text(driver())
            subprocess.run(['c++', '-std=c++17', '-fPIC', '-pthread', '-I', str(ROOT),
                            str(path / 'driver.cpp'), '-o', str(path / 'test'), *flags],
                           check=True, timeout=45)
            subprocess.run([str(path / 'test')], check=True, timeout=15)
            for diagnostics, value, expected in [
                ('0', '2', '0'), ('1', '', '0'), ('1', '0', '0'),
                ('1', '1', '1'), ('1', '2', '2'), ('1', '3', '0'),
                ('1', '2garbage', '0'), ('1', '-1', '0')
            ]:
                subprocess.run([str(path / 'test'), diagnostics, value, expected],
                               check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
