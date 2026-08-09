#include <QtTest/QtTest>

#include <workload/Transaction.h>

class RecordingCollection : public workload::Collection {
public:
    int processedFrames { 0 };
    bool lastFrameHadRemovals { false };

protected:
    void processTransactionFrame(const workload::Transaction& transaction) override {
        ++processedFrames;
        lastFrameHadRemovals = transaction.hasRemovals();
    }
};

class TransactionTests : public QObject {
    Q_OBJECT
private slots:
    void allocatorReusesAndClearsIndices();
    void collectionConsolidatesQueuedTransactions();
};

QTEST_MAIN(TransactionTests)

void TransactionTests::allocatorReusesAndClearsIndices() {
    workload::indexed_container::Allocator<4> allocator;
    QCOMPARE(allocator.allocateIndex(), 0);
    QCOMPARE(allocator.allocateIndex(), 1);
    QVERIFY(allocator.checkIndex(1));
    allocator.freeIndex(-1);
    allocator.freeIndex(7);
    QCOMPARE(allocator.getNumFreeIndices(), 0);
    allocator.freeIndex(0);
    QCOMPARE(allocator.getNumLiveIndices(), 1);
    QCOMPARE(allocator.allocateIndex(), 0);
    allocator.clear();
    QCOMPARE(allocator.getNumAllocatedIndices(), 0);
    QVERIFY(!allocator.checkIndex(0));
}

void TransactionTests::collectionConsolidatesQueuedTransactions() {
    RecordingCollection collection;
    const auto first = collection.allocateID();
    const auto second = collection.allocateID();
    QVERIFY(collection.isAllocatedID(first));
    QCOMPARE(collection.getNumAllocatedProxies(), 2);

    workload::Transaction copied;
    copied.reset(first, workload::Sphere(glm::vec3(1.0f), 2.0f), workload::Owner(42));
    copied.update(first, workload::Sphere(glm::vec3(2.0f), 3.0f));
    collection.enqueueTransaction(copied);

    workload::Transaction moved;
    moved.remove(second);
    collection.enqueueTransaction(std::move(moved));
    QCOMPARE(collection.enqueueFrame(), 1u);
    collection.processTransactionQueue();
    QCOMPARE(collection.processedFrames, 1);
    QVERIFY(collection.lastFrameHadRemovals);

    QCOMPARE(collection.enqueueFrame(), 2u);
    collection.processTransactionQueue();
    QCOMPARE(collection.processedFrames, 2);
    QVERIFY(!collection.lastFrameHadRemovals);
    collection.clear();
}

#include "TransactionTests.moc"
