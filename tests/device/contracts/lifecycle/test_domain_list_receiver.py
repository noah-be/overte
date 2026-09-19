"""Real DomainList header serialization and receiver through session mutation.

Host Qt wire/receiver regression, not a live domain or native iOS test.
"""
from pathlib import Path
import os, shlex, subprocess, sys, tempfile
from test_login_dialog_domain_receiver import block
ROOT=Path(__file__).resolve().parents[4]
baseline=os.environ.get('OVERTE_DOMAIN_LIST_BASELINE')
source=subprocess.check_output(['git','show',baseline+':libraries/networking/src/NodeList.cpp'],cwd=ROOT,text=True) if baseline else (ROOT/'libraries/networking/src/NodeList.cpp').read_text()
method=block(source,'void NodeList::processDomainList(')
method=method[:method.index('    // FIXME: Remove this call to requestDomainSettings()')]+'}\n'
producer=(ROOT/'domain-server/src/DomainServer.cpp').read_text()
producer=producer[producer.index('    extendedHeaderStream << limitedNodeList->getSessionUUID();'):producer.index('    auto domainListPackets = NLPacketList::create(PacketType::DomainList, extendedHeader);')]
permissions=(ROOT/'libraries/networking/src/NodePermissions.cpp').read_text()
operators=block(permissions,'QDataStream& operator<<(QDataStream& out, const NodePermissions& perms)')+'\n'+block(permissions,'QDataStream& operator>>(QDataStream& in, NodePermissions& perms)')
fixture=r'''
#include <QDataStream>
#include <QIODevice>
#include <QUuid>
#include <QSharedPointer>
#include <QDebug>
#include <chrono>
#include <cassert>
#include <iostream>
#include "libraries/networking/src/DomainListRequestHistory.h"
using namespace std::chrono;
using p_high_resolution_clock=steady_clock;
constexpr int USECS_PER_MSEC=1000,MSECS_PER_SECOND=1000;
quint64 usecTimestampNow(){return 123;}
namespace overte { namespace security {enum class DiagnosticEvent{Redacted};const char* diagnosticEvent(DiagnosticEvent){return "redacted";}}}
#define networking 0
#undef qCDebug
#undef qCWarning
#define qCDebug(...) qDebug()
#define qCWarning(...) qWarning()
struct SockAddr {int endpoint=1;bool isNull()const{return endpoint==0;}bool operator!=(const SockAddr& b)const{return endpoint!=b.endpoint;}};
struct NodePermissions {using Permissions=uint;uint permissions=0;};
/* OPERATORS */
struct Node {using LocalID=quint16;static constexpr LocalID NULL_LOCAL_ID=0;QUuid uuid;LocalID id=9;QUuid getUUID(){return uuid;}LocalID getLocalID(){return id;}NodePermissions getPermissions(){return {31};}};
struct ReceivedMessage {QByteArray data;SockAddr sender;QByteArray getMessage(){return data;}SockAddr getSenderSockAddr(){return sender;}};
struct Domain {SockAddr socket;bool connected=false;QUuid uuid;int acknowledgements=0;SockAddr getSockAddr(){return socket;}bool isConnected(){return connected;}QUuid getUUID(){return uuid;}void setIsConnected(bool v){connected=v;}int getSettingsObject(){return 0;}void clearPendingCheckins(){++acknowledgements;}};
struct LimitedNodeList {enum class ConnectionStep {ReceiveDSList};};
struct NodeList;
NodeList* current;
struct DependencyManager {template<class T>static T* get(){return current;}};
struct NodeList {
 DomainListRequestHistory _domainListRequests;
 NodeList(){_domainListRequests.issued(456);_domainListRequests.issued(457);}
 struct Socket {void clearConnections(){}} _nodeSocket;
 Domain _domainHandler;QUuid session;Node::LocalID local=0;quint64 _nodeConnectTimestamp=0;
 enum Reason {Old,Connect};Reason _connectReason=Old;int receipts=0,adjustments=0,resets=0;bool drop=true;
 bool adjustCanRezAvatarEntitiesPermissions(int,NodePermissions&,bool){++adjustments;return false;}
 void setDropOutgoingNodeTraffic(bool v){drop=v;}void receivedDomainServerList(){++receipts;}void flagTimeForConnectionStep(LimitedNodeList::ConnectionStep){}
 Node::LocalID getSessionLocalID(){return local;}QUuid getSessionUUID(){return session;}
 void setSessionLocalID(Node::LocalID v){local=v;}void setSessionUUID(QUuid v){session=v;}
 void reset(const char*,bool){++resets;session={};local=0;}
 void processDomainList(QSharedPointer<ReceivedMessage> message);
};
/* METHOD */
struct ServerIdentity {QUuid uuid;QUuid getSessionUUID(){return uuid;}quint16 getSessionLocalID(){return 2;}bool getAuthenticatePackets(){return true;}};
struct ServerNodeData {quint64 token;quint64 getLastDomainCheckinTimestamp(){return token;}};
QByteArray packet(QUuid domain,QUuid session,quint64 token=456) {
 QByteArray extendedHeader;QDataStream extendedHeaderStream(&extendedHeader,QIODevice::WriteOnly);
 ServerIdentity identity{domain};auto limitedNodeList=&identity;Node n{session};auto node=&n;ServerNodeData data{token};auto nodeData=&data;quint64 requestPacketReceiveTime=0;bool newConnection=true;
 /* PRODUCER */
 return extendedHeader;
}
int main(int argc,char**argv){
 const auto domain=QUuid::createUuid(),session=QUuid::createUuid(),other=QUuid::createUuid();
 auto bytes=packet(domain,session);
 auto deliver=[&](NodeList& list,QByteArray payload,int sender=1){current=&list;auto message=QSharedPointer<ReceivedMessage>::create();message->data=payload;message->sender.endpoint=sender;list.processDomainList(message);};
 const std::string mode=argc>1?argv[1]:"positive";
 if(mode=="positive") {
  NodeList list;deliver(list,bytes);assert(list.session==session&&list.local==9&&list.receipts==1&&list._domainHandler.acknowledgements==1&&!list.drop);
  list._domainHandler.connected=true;list._domainHandler.uuid=domain;
  deliver(list,bytes);assert(list.resets==0&&list.receipts==2); // packet-list sibling/duplicate is valid
  deliver(list,packet(domain,other,457));assert(list.resets==1&&list.session==other); // genuine server reassignment still works
 }else if(mode=="reordered") {
  NodeList list;list._domainHandler.connected=true;list._domainHandler.uuid=domain;list.session=session;list.local=9;
  deliver(list,packet(domain,other,457));assert(list.session==other&&list.resets==1);
  list._domainHandler.connected=true;deliver(list,bytes);
  assert(list.session==other&&list.resets==1&&list.receipts==1);
 }else if(mode=="unknown") {
  NodeList list;deliver(list,packet(domain,session,100));assert(list.receipts==0);
 }else if(mode=="sender") {
  NodeList list;deliver(list,bytes,2);assert(list.receipts==0&&list.session.isNull()&&list.adjustments==0);
 }else if(mode=="domain") {
  NodeList list;list._domainHandler.connected=true;list._domainHandler.uuid=other;
  deliver(list,bytes);assert(list.receipts==0&&list._domainHandler.acknowledgements==0&&list.adjustments==0&&list._nodeConnectTimestamp==0);
 }else if(mode=="truncated") {
  for(int length=0;length<bytes.size();++length){NodeList list;deliver(list,bytes.left(length));assert(list.receipts==0&&list.session.isNull()&&list.adjustments==0&&list._nodeConnectTimestamp==0);}
 }else if(mode=="disconnected") {
  NodeList list;list._domainHandler.socket.endpoint=0;deliver(list,bytes);assert(list.receipts==0&&list.adjustments==0&&list._nodeConnectTimestamp==0);
 }
}
'''
flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','Qt6Core'],text=True))
with tempfile.TemporaryDirectory(prefix='overte-domain-list-') as directory:
 p=Path(directory);(p/'test.cpp').write_text(fixture.replace('/* METHOD */',method).replace('/* PRODUCER */',producer).replace('/* OPERATORS */',operators))
 subprocess.run(['c++','-std=c++17','-fPIC','-I'+str(ROOT),str(p/'test.cpp'),'-o',str(p/'test'),*flags],check=True,timeout=30)
 for mode in ('positive','sender','domain','truncated','disconnected','reordered','unknown'):
  result=subprocess.run([str(p/'test'),mode],capture_output=True,text=True,timeout=5)
  expected_failure=bool(baseline and ((mode in ('reordered','unknown') and '_domainListRequests.accept(' not in method) or (mode in ('sender','domain','truncated','disconnected') and 'packetStream.status() != QDataStream::Ok' not in method)))
  assert (result.returncode!=0)==expected_failure,(mode,result.stderr)
  print(('EXPECTED BASELINE FAILURE' if expected_failure else 'PASS')+': '+mode)
