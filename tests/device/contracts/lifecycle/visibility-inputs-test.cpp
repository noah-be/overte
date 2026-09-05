// SPDX-License-Identifier: Apache-2.0
#include <cassert>
#include <thread>
#include <QtCore/QCoreApplication>
#include <QtCore/QThread>
#include "interface/src/ApplicationLifecycle.h"
#include "libraries/networking/src/RequestCancellation.h"
struct AddressManager {
    overte::network::RequestScope requests;
    bool foreground = false;
    unsigned observations = 0;
    void setClientLookupVisibility(bool value) {
        foreground = value; ++observations; requests.setActive(value);
    }
};
AddressManager addresses;
bool addressInstalled = false;
struct DependencyManager {
    template<class T> static bool isSet() { return addressInstalled; }
    template<class T> static T* get() { assert(addressInstalled); return &addresses; }
};
overte::lifecycle::Gate gate;
overte::lifecycle::Gate& overte::lifecycle::applicationGate() { return gate; }
// Complete original production publication and both exported functions.
#include "visibility-publication.inc"
int main(int argc, char** argv) {
    using namespace overte::lifecycle;
    QCoreApplication app(argc, argv);
    observeNativeVisibility(true); // Early callback must not create dependencies.
    assert(!gate.snapshot().foreground && addresses.observations == 0);
    observeNativeVisibility(false);
    addressInstalled = true;
    observeQtVisibility(true); // Startup must respect retained native pause.
    assert(!gate.snapshot().foreground && !addresses.foreground);
    observeNativeVisibility(true);
    assert(gate.snapshot().foreground && addresses.foreground);
    const auto ticket = addresses.requests.next();
    const auto generation = gate.snapshot().generation;
    observeQtVisibility(true);
    observeNativeVisibility(true);
    assert(ticket.current() && gate.snapshot().generation == generation);
    observeQtVisibility(false);
    observeNativeVisibility(true); // Reproduces Phone's cross-source race.
    assert(!gate.snapshot().foreground && !addresses.foreground && !ticket.current());
    observeNativeVisibility(false);
    observeQtVisibility(true); // The converse must also fail closed.
    assert(!gate.snapshot().foreground && !addresses.foreground);
    observeNativeVisibility(true);
    assert(gate.snapshot().foreground && addresses.foreground);
    const auto next = addresses.requests.next();
    std::thread nativePause([] { observeNativeVisibility(false); });
    nativePause.join();
    assert(next.current()); // Queued delivery, not a false synchronous-stop claim.
    QCoreApplication::processEvents();
    assert(!next.current() && !gate.snapshot().foreground && !addresses.foreground);
    observeQtVisibility(false);
    std::thread nativeResume([] { observeNativeVisibility(true); });
    nativeResume.join();
    QCoreApplication::processEvents();
    assert(!gate.snapshot().foreground && !addresses.foreground);
    observeQtVisibility(true);
    assert(gate.snapshot().foreground && addresses.foreground);
    gate.stop();
    observeNativeVisibility(false);
    observeNativeVisibility(true);
    assert(gate.snapshot().state == State::Stopped);
    assert(!addresses.foreground);
}
