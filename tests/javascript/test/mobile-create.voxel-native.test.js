"use strict";
const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

// Compile the shipped C++ method bodies, including update's complete state
// machine. Real Qt locks protect the fixture; worker scheduling, packet sending
// and volume geometry are the explicit engine boundaries. This is a host unit
// check, not a product build or evidence that a device renderer ran.
function method(source, signature) {
    const start = source.indexOf(signature);
    assert.notEqual(start, -1, signature);
    let end = source.indexOf("{", start), depth = 1;
    for (++end; depth && end < source.length; ++end) {
        if (source[end] === "{") { ++depth; }
        if (source[end] === "}") { --depth; }
    }
    assert.equal(depth, 0);
    return source.slice(start, end);
}

test("production PolyVox readiness waits for compression and Ready under Qt read locks", t => {
    const root = path.resolve(__dirname, "../../..");
    const renderer = fs.readFileSync(path.join(root, "libraries/entities-renderer/src/RenderablePolyVoxEntityItem.cpp"), "utf8");
    const header = fs.readFileSync(path.join(root, "libraries/entities-renderer/src/RenderablePolyVoxEntityItem.h"), "utf8");
    const api = fs.readFileSync(path.join(root, "libraries/entities/src/EntityScriptingInterface.cpp"), "utf8");
    const base = fs.readFileSync(path.join(root, "libraries/entities/src/PolyVoxEntityItem.h.in"), "utf8");
    let qt = spawnSync("pkg-config", ["--cflags", "--libs", "Qt5Core"], { encoding: "utf8" });
    if (qt.status !== 0) { qt = spawnSync("pkg-config", ["--cflags", "--libs", "Qt6Core"], { encoding: "utf8" }); }
    if (qt.status !== 0) { t.skip("Qt Core compiler prerequisites unavailable"); return; }
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), "overte-voxel-ready-"));
    t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
    const source = `
#include <QByteArray>
#include <QReadWriteLock>
#include <QReadLocker>
#include <QWriteLocker>
#include <QUuid>
#include <cassert>
#include <iostream>
#include <map>
#include <memory>
${header.match(/enum class PolyVoxState\s*\{[^}]+\};/)[0]}
struct EntityItem { virtual ~EntityItem() = default; };
struct PolyVoxEntityItem : EntityItem {
    ${method(base, "virtual bool isVoxelDataReady() const")}
};
struct EntityPropertyFlags { void setHasProperty(int) {} };
constexpr int PROP_VOXEL_DATA = 1;
struct EntityItemProperties { void setVoxelDataDirty() {} void setLastEdited(quint64) {} };
enum class PacketType { EntityEdit };
struct EntitySimulation { virtual ~EntitySimulation() = default; };
struct EntityEditPacketSender { template<class T> void queueEditEntityMessage(PacketType, T, QUuid, EntityItemProperties) {} };
struct PhysicalEntitySimulation : EntitySimulation { EntityEditPacketSender* getPacketSender() { return nullptr; } };
struct EntityTree {
    mutable QReadWriteLock lock;
    std::map<QUuid, std::shared_ptr<EntityItem>> items;
    template<class F> void withReadLock(F function) const { QReadLocker guard(&lock); function(); }
    std::shared_ptr<EntityItem> findEntityByEntityItemID(QUuid id) { auto it = items.find(id); return it == items.end() ? nullptr : it->second; }
    std::shared_ptr<EntitySimulation> getSimulation() { return nullptr; }
};
using EntityTreePointer = std::shared_ptr<EntityTree>;
struct Element { EntityTreePointer getTree() { return nullptr; } };
using EntityTreeElementPointer = std::shared_ptr<Element>;
using EntitySimulationPointer = std::shared_ptr<EntitySimulation>;
using PhysicalEntitySimulationPointer = std::shared_ptr<PhysicalEntitySimulation>;
quint64 usecTimestampNow() { return 1; }
struct RenderablePolyVoxEntityItem : PolyVoxEntityItem {
    mutable QReadWriteLock lock;
    mutable int reads = 0;
    PolyVoxState _state { PolyVoxState::Ready };
    bool _volDataDirty = false, _voxelDataDirty = false;
    QByteArray _voxelData { "old" };
    bool queuedCompression = false;
    template<class F> void withReadLock(F function) const { QReadLocker guard(&lock); ++reads; function(); }
    template<class F> void withWriteLock(F function) { QWriteLocker guard(&lock); function(); }
    bool isVoxelDataReady() const override;
    void update(const quint64& now);
    void compressVolumeDataFinished(const QByteArray& data);
    void tellNeighborsToRecopyEdges(bool) {} void copyUpperEdgesFromNeighbors() {} void stopUpdates() {}
    void recomputeMesh() { withWriteLock([&] { _state = PolyVoxState::BakingMeshFinished; }); }
    void uncompressVolumeData() { withWriteLock([&] { _state = PolyVoxState::UncompressingFinished; }); }
    void compressVolumeDataAndSendEditPacket() { queuedCompression = true; }
    void computeShapeInfoWorker() { withWriteLock([&] { _state = PolyVoxState::BakingShapeFinished; }); }
    void setLastEdited(quint64) {} void setLastBroadcast(quint64) {}
    EntityTreeElementPointer getElement() { return nullptr; }
    EntityItemProperties getProperties(EntityPropertyFlags, bool) { return {}; }
    QUuid getID() { return {}; }
};
struct EntityScriptingInterface {
    EntityTreePointer _entityTree;
    bool isVoxelDataReady(const QUuid& id);
};
${method(renderer, "bool RenderablePolyVoxEntityItem::isVoxelDataReady() const")}
${method(renderer, "void RenderablePolyVoxEntityItem::update(const quint64& now)")}
${method(renderer, "void RenderablePolyVoxEntityItem::compressVolumeDataFinished(const QByteArray& voxelData)")}
${method(api, "bool EntityScriptingInterface::isVoxelDataReady(const QUuid& id)")}
int main() {
    EntityScriptingInterface api;
    QUuid id = QUuid::createUuid();
    assert(!api.isVoxelDataReady(id));
    api._entityTree = std::make_shared<EntityTree>();
    assert(!api.isVoxelDataReady(id));
    api._entityTree->items[id] = std::make_shared<EntityItem>();
    assert(!api.isVoxelDataReady(id));
    api._entityTree->items[id] = std::make_shared<PolyVoxEntityItem>();
    assert(!api.isVoxelDataReady(id));
    auto volume = std::make_shared<RenderablePolyVoxEntityItem>();
    api._entityTree->items[id] = volume;
    assert(api.isVoxelDataReady(id));
    assert(volume->reads == 1);
    volume->withWriteLock([&] { volume->_volDataDirty = true; });
    assert(!api.isVoxelDataReady(id));
    volume->update(0); // mesh worker completes; data still old
    volume->update(0); // compression worker remains pending
    assert(volume->queuedCompression);
    assert(volume->_state == PolyVoxState::Compressing);
    assert(!api.isVoxelDataReady(id));
    for (int i = 0; i < 4; ++i) { volume->update(0); assert(!api.isVoxelDataReady(id)); }
    volume->compressVolumeDataFinished("new");
    assert(volume->_voxelData == "new");
    assert(!api.isVoxelDataReady(id)); // bytes alone do not prove completion
    volume->update(0); // shape worker completes
    assert(!api.isVoxelDataReady(id));
    volume->update(0); // Ready
    assert(api.isVoxelDataReady(id));
    volume->withWriteLock([&] { volume->_voxelDataDirty = true; });
    assert(!api.isVoxelDataReady(id)); // network update invalidates Ready
    volume->update(0); volume->update(0);
    assert(api.isVoxelDataReady(id));
    volume->withWriteLock([&] { volume->_volDataDirty = true; });
    volume->update(0); volume->update(0);
    volume->withWriteLock([&] { volume->_volDataDirty = true; }); // edit during compression
    volume->compressVolumeDataFinished("intermediate");
    volume->update(0); volume->update(0);
    assert(volume->_state == PolyVoxState::Ready);
    assert(!api.isVoxelDataReady(id)); // Ready alone cannot accept the earlier worker result
    volume->update(0); volume->update(0);
    volume->compressVolumeDataFinished("final");
    volume->update(0); volume->update(0);
    assert(api.isVoxelDataReady(id));
    assert(volume->_voxelData == "final");
    api._entityTree->items.erase(id);
    assert(!api.isVoxelDataReady(id));
    std::cout << "PASS production voxel worker readiness, Qt locks and deleted/type guards\\n";
}`;
    const filename = path.join(directory, "test.cpp");
    const binary = path.join(directory, "test");
    fs.writeFileSync(filename, source);
    const compiled = spawnSync("c++", ["-std=c++17", "-Wall", "-Werror", "-fPIC", filename, "-o", binary, ...qt.stdout.trim().split(/\s+/).flatMap(flag => flag.startsWith("-I") ? ["-isystem", flag.slice(2)] : [flag])], { encoding: "utf8", timeout: 60000 });
    assert.equal(compiled.status, 0, compiled.stdout + compiled.stderr);
    const result = spawnSync(binary, [], { encoding: "utf8", timeout: 10000 });
    assert.equal(result.status, 0, result.stdout + result.stderr);
    assert.match(result.stdout, /PASS production voxel worker readiness/);
});
