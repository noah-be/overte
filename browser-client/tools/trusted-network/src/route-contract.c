// SPDX-License-Identifier: Apache-2.0
// Source-only fixed setup-stage prototype. No main/exec or installation path.
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <linux/capability.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <linux/securebits.h>
#include <sched.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/syscall.h>
#include <unistd.h>

struct fixed_route { const char *address; uint8_t prefix; };
static const struct fixed_route denied[12] = {
 {"10.0.0.0",8},{"172.16.0.0",12},{"192.168.0.0",16},{"169.254.0.0",16},
 {"100.64.0.0",10},{"192.0.0.0",24},{"192.0.2.0",24},{"198.18.0.0",15},
 {"198.51.100.0",24},{"203.0.113.0",24},{"224.0.0.0",4},{"240.0.0.0",4}
};
struct route_message { struct nlmsghdr header; struct rtmsg route; struct rtattr destination; uint32_t address; };

// Pure bounded serialization, independently checked against rtnetlink UAPI.
// Caller cannot supply a destination, route type, interface, table or flag.
size_t overte_route_message(unsigned index, uint32_t sequence, void *output, size_t capacity) {
 if (index >= 12 || !sequence || !output || capacity < sizeof(struct route_message)) return 0;
 struct route_message message = {0};
 message.header.nlmsg_len = sizeof(message);
 message.header.nlmsg_type = RTM_NEWROUTE;
 message.header.nlmsg_flags = NLM_F_REQUEST|NLM_F_ACK|NLM_F_CREATE|NLM_F_EXCL;
 message.header.nlmsg_seq = sequence;
 message.route.rtm_family = AF_INET;
 message.route.rtm_dst_len = denied[index].prefix;
 message.route.rtm_table = RT_TABLE_MAIN;
 message.route.rtm_protocol = RTPROT_BOOT;
 message.route.rtm_scope = RT_SCOPE_UNIVERSE;
 message.route.rtm_type = RTN_PROHIBIT;
 message.destination.rta_len = RTA_LENGTH(sizeof(uint32_t));
 message.destination.rta_type = RTA_DST;
 if (inet_pton(AF_INET, denied[index].address, &message.address) != 1) return 0;
 memcpy(output, &message, sizeof(message));
 return sizeof(message);
}

// 1 success, 0 malformed/unmatched, negative exact kernel error. No raw output.
// Transport must separately require sockaddr_nl.nl_pid=0, no MSG_TRUNC, and
// bounded one-request/one-ACK exchange; this function does not trust sender IDs.
int overte_route_ack(const void *input, size_t size, uint32_t sequence) {
 if (!input || !sequence || size != NLMSG_LENGTH(sizeof(struct nlmsgerr))) return 0;
 struct nlmsghdr header; struct nlmsgerr error;
 memcpy(&header,input,sizeof(header));
 if (header.nlmsg_len != size || header.nlmsg_type != NLMSG_ERROR || header.nlmsg_seq != sequence) return 0;
 memcpy(&error,(const unsigned char*)input+NLMSG_HDRLEN,sizeof(error));
 if (error.msg.nlmsg_len != 36 || error.msg.nlmsg_flags != (NLM_F_REQUEST|NLM_F_ACK|NLM_F_CREATE|NLM_F_EXCL)
     || error.msg.nlmsg_pid != 0 || error.msg.nlmsg_type != RTM_NEWROUTE || error.msg.nlmsg_seq != sequence
     || error.error > 0 || error.error < -4095) return 0;
 return error.error == 0 ? 1 : error.error;
}

// Pure exact self-map string, never an arbitrary UID range/multiple mapping.
int overte_self_map(uint32_t identity, char *output, size_t capacity) {
 if (!identity || identity == UINT32_MAX || !output || capacity < 24) return 0;
 // Retain the caller's numeric identity. Mapping it to namespace UID0 makes
 // the capability-free owner require a parent-root mapping at the next bwrap
 // boundary, where Linux's CAP_SETFCAP restriction can refuse that mapping.
 char record[32];int length=snprintf(record,sizeof(record),"%u %u 1\n",identity,identity);
 if(length<=0||(size_t)length>=sizeof(record)||(size_t)length>=capacity)return 0;
 memcpy(output,record,(size_t)length+1);return length;
}

// Future trusted C caller only: NEW network namespace, never setns an existing
// namespace. Caller MUST first verify its dedicated installed profile/root-owned
// executable and establish exact self uid/gid maps after CLONE_NEWUSER; no
// untrusted callback or executable runs between those steps. Not called by tests.
int overte_new_network_namespace(void) {
 return unshare(CLONE_NEWNET);
}

// Future trusted stage retirement. No exec/native activation in this prototype.
// Refuse unknown capability counts before mutation; preserve actual errno.
// Effective/permitted/inheritable, ambient and bounding all verified zero.
int overte_retire_setup_capabilities(void) {
 int count=0;
 for (; count<64; count++) {
  if (prctl(PR_CAPBSET_READ,count,0,0,0)<0) {
   if (errno!=EINVAL) return -1;
   break;
  }
 }
 if (count==0 || count==64) { errno=EOPNOTSUPP; return -1; }
 if (prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_CLEAR_ALL,0,0,0)<0) return -1;
 unsigned secure=SECBIT_NOROOT|SECBIT_NOROOT_LOCKED|SECBIT_NO_SETUID_FIXUP|SECBIT_NO_SETUID_FIXUP_LOCKED;
 if (prctl(PR_SET_SECUREBITS,secure,0,0,0)<0) return -1;
 for (int capability=0;capability<count;capability++)
  if (prctl(PR_CAPBSET_DROP,capability,0,0,0)<0) return -1;
 struct __user_cap_header_struct header={_LINUX_CAPABILITY_VERSION_3,0};
 struct __user_cap_data_struct data[2]={{0},{0}};
 if (syscall(SYS_capset,&header,data)<0 || syscall(SYS_capget,&header,data)<0) return -1;
 for (int word=0;word<2;word++)
  if(data[word].effective||data[word].permitted||data[word].inheritable){errno=EPERM;return -1;}
 for(int capability=0;capability<count;capability++)
  if(prctl(PR_CAPBSET_READ,capability,0,0,0)!=0
      ||prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_IS_SET,capability,0,0)!=0){errno=EPERM;return -1;}
 return 0;
}
