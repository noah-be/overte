// SPDX-License-Identifier: Apache-2.0
#include <QSet>
#include <atomic>
#include <cassert>
#include <memory>
#include <thread>
#include <vector>
struct Node {
    int type;
    bool upstream;
    int getType() const { return type; }
    bool isUpstream() const { return upstream; }
    int getUUID() const { return 1; } // Test-only packet sink marker, not exported.
};
using SharedNodePointer = std::shared_ptr<Node>;
struct NodeType { static bool isDownstream(int type) { return type == 3; } };
class NodeList {
public:
    struct DiscoveryBoundary {
        bool foreground { true };
        void setClientDiscoveryVisibility(bool value) { foreground = value; }
    } _domainHandler;
#include "node-visibility-state.inc"
    void sendDomainServerCheckIn();
    void handleICEConnectionToDomainServer();
    void pingPunchForDomainServer();
    void pingPunchForInactiveNode(const SharedNodePointer&);
    void startNodeHolePunch(const SharedNodePointer&);
    void sendKeepAlivePings();
    int afterFence { 0 }, packets { 0 }, enumerations { 0 };
    QSet<int> _nodeTypesOfInterest { 1, 3 };
    std::vector<SharedNodePointer> nodes {
        std::make_shared<Node>(Node{1, false}), std::make_shared<Node>(Node{1, true}),
        std::make_shared<Node>(Node{3, false}), std::make_shared<Node>(Node{2, false}) };
    template<class Predicate, class Send> void eachMatchingNode(Predicate predicate, Send send) {
        ++enumerations;
        for (const auto& node : nodes) { if (predicate(node)) { send(node); } }
    }
    int constructPingPacket(int id) { return id; }
    void sendPacket(int, const Node&) { ++packets; }
    void exercise() {
        sendDomainServerCheckIn(); handleICEConnectionToDomainServer(); pingPunchForDomainServer();
        pingPunchForInactiveNode({}); startNodeHolePunch({}); sendKeepAlivePings();
    }
};
#include "node-visibility-methods.inc"
int main() {
    NodeList client;
    client.exercise(); // Unmanaged assignment/server default unchanged.
    assert(client.afterFence == 5 && client.packets == 1 && client.enumerations == 1);
    client.setClientTransportVisibility(false);
    assert(!client._domainHandler.foreground);
    client.exercise();
    assert(client.afterFence == 5 && client.packets == 1 && client.enumerations == 1);
    client.setClientTransportVisibility(false); // Duplicate pause stays closed.
    client.exercise();
    assert(client.afterFence == 5 && client.packets == 1);
    client.setClientTransportVisibility(true);
    assert(client._domainHandler.foreground);
    client.exercise();
    assert(client.afterFence == 10 && client.packets == 2 && client.enumerations == 2);
    std::thread pause([&] { client.setClientTransportVisibility(false); });
    pause.join();
    client.exercise();
    assert(client.afterFence == 10 && client.packets == 2 && client.enumerations == 2);
    // This deliberately makes no assertion about a send already past its guard.
}
