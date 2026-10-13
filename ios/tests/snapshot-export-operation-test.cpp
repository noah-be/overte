// Copyright 2026 Overte e.V.
// SPDX-License-Identifier: Apache-2.0
#include "ios/snapshot/SnapshotExportOperation.h"
#include <thread>
#include <stdexcept>
#include <QCoreApplication>
#include <QTimer>
#include <iostream>
using Operation=overte::ios::SnapshotExportOperation;
static void require(bool value) { if(!value){throw std::runtime_error("Native Snapshot export operation invariant failed");} }
int main(int argc,char** argv) {
    QCoreApplication application(argc,argv);
    Operation cancelled("old","/owned/old.gif","save");
    cancelled.cancel();require(cancelled.current());require(!cancelled.advance(Operation::Phase::Authorizing));
    require(cancelled.finish());require(!cancelled.finish());require(!cancelled.advance(Operation::Phase::Authorizing));
    Operation permission("permission","/owned/image.png","save");
    require(permission.advance(Operation::Phase::Authorizing));permission.cancel();
    require(permission.current());require(!permission.advance(Operation::Phase::Committed));require(permission.finish());
    Operation committed("saved","/owned/image.png","save");
    require(committed.advance(Operation::Phase::Authorizing));require(committed.advance(Operation::Phase::Committed));
    committed.cancel();require(committed.phase()==Operation::Phase::Committed);require(committed.current());
    // After actual Photos commitment, cancellation cannot manufacture rollback;
    // the native actor remains leased until the actual Photos completion.
    require(committed.finish());require(!committed.finish());
    Operation shared("share","/owned/animation.gif","share");
    require(!shared.advance(Operation::Phase::Authorizing));require(shared.advance(Operation::Phase::Choosing));
    require(!shared.advance(Operation::Phase::Committed));shared.cancel();require(shared.current());
    int callbacks=0;QTimer::singleShot(0,[&]{if(shared.finish()){++callbacks;}});
    require(callbacks==0);QCoreApplication::processEvents();require(callbacks==1);require(!shared.current());
    Operation replacement("next","/owned/next.png","save");
    require(replacement.current());require(!shared.finish());require(replacement.current());
    for(int i=0;i<1000;++i) {
        Operation race("race","/owned/photo.png","save");require(race.advance(Operation::Phase::Authorizing));
        bool commitment=false;
        std::thread worker([&]{commitment=race.advance(Operation::Phase::Committed);});
        race.cancel();worker.join();
        require(race.cancelled());require(race.current());
        require(commitment==(race.phase()==Operation::Phase::Committed));
        require(!race.advance(Operation::Phase::Committed));require(race.finish());require(!race.finish());
    }
    std::cout<<"PASS: queued/permission cancellation, actual commitment boundary, native lease, stale return and atomic race\n";
}
