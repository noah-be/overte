// SPDX-License-Identifier: Apache-2.0
// Complete fixed-stage prototype; not installed or activated by its CPU tests.
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <ifaddrs.h>
#include <linux/memfd.h>
#include <linux/netlink.h>
#include <linux/rtnetlink.h>
#include <openssl/sha.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "image.h"
#include "route-contract.c"

#define LIMIT 131072
#define SOURCE_LIMIT 262144
#define SEALS (F_SEAL_SEAL|F_SEAL_SHRINK|F_SEAL_GROW|F_SEAL_WRITE)
// Fixed public projection only; no runtime value can become a label or string.
enum setup_phase {
 SETUP_ADMISSION,SETUP_INITIAL_CAPABILITIES,SETUP_INSTALLED_PROFILE,SETUP_INITIAL_NNP,
 SETUP_ENVIRONMENT,SETUP_SIGNALS,SETUP_CONFIGURATION,SETUP_OWNER_MODULES,SETUP_POLICY,
 SETUP_PYTHON_IMAGE,SETUP_HANDOFF_RELOCATE,SETUP_USER_NAMESPACE,SETUP_GROUPS_DENY,
 SETUP_UID_MAP,SETUP_GID_MAP,SETUP_NETWORK_NAMESPACE,SETUP_LIFETIME,SETUP_TAP_READY,
 SETUP_ROUTE_SOCKET,SETUP_ROUTE_BIND,SETUP_ROUTE_ACK_OPTION,SETUP_ROUTE_INSTALL,
 SETUP_ROUTE_READBACK,SETUP_ATTESTATION,SETUP_ATTESTATION_RELOCATE,SETUP_RETIRE_CAPS,
 SETUP_POST_RETIRE_LIFETIME,SETUP_HANDOFF_DESCRIPTORS,SETUP_CLOSE_INHERITED,SETUP_EXEC_PYTHON,
 SETUP_PYTHON_OPEN,SETUP_PYTHON_HASH,SETUP_PYTHON_IMPORT_ROOTS,
 SETUP_PYTHON_IMPORT_OPEN,SETUP_PYTHON_IMPORT_STAT,SETUP_PYTHON_IMPORT_SCAN,
 SETUP_PYTHON_ALIAS_RESOLVE,SETUP_PYTHON_ALIAS_TARGET
};
static const char *const setup_phase_labels[]={
 "admission","initial-capabilities","installed-profile","initial-nnp",
 "environment","signal-handlers","configuration","owner-modules","policy",
 "python-image","handoff-relocate","user-namespace","groups-deny",
 "uid-map","gid-map","network-namespace","lifetime","tap-ready",
 "route-socket","route-bind","route-ack-option","route-install-ack",
 "route-readback","attestation","attestation-relocate","retire-capabilities",
 "post-retirement-lifetime","handoff-descriptors","close-inherited","exec-python",
 "python-image-open","python-image-hash","python-import-roots",
 "python-import-root-open","python-import-root-stat","python-import-scan",
 "python-import-alias-resolve","python-import-alias-target"
};
// errnoObserved is the value captured at refusal before cleanup. It is not a
// claimed causal syscall for semantic/identity validation helpers. Each fixed
// operation clears older errno first; no strerror/label/path/FD/argument output.
static size_t setup_failure_json(enum setup_phase phase,int observed,char *output,size_t capacity) {
 if((unsigned)phase>=sizeof(setup_phase_labels)/sizeof(setup_phase_labels[0])||!output)return 0;
 char data[192];int error=observed>=0&&observed<=4095?observed:0;
 int length=snprintf(data,sizeof(data),"{\"version\":1,\"phase\":\"%s\",\"errnoObserved\":%d}",setup_phase_labels[phase],error);
 if(length<1||length>=(int)sizeof(data)||(size_t)length+1>capacity)return 0;
 memcpy(output,data,(size_t)length+1);return (size_t)length;
}
static volatile sig_atomic_t stopped;
static unsigned import_alias_reads;
static uint64_t import_alias_read_bytes;
static int verify_import_alias_target(int fd,const char *resolved);
#if PYTHON_SIGNED_LIBRARY_COUNT == 1
static int verify_signed_library_target(int fd,const char *resolved);
#endif
static void stop(int ignored){(void)ignored;stopped=1;}
static long long milliseconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))return -1;return t.tv_sec*1000LL+t.tv_nsec/1000000;}
static int fullwrite(int fd,const void *data,size_t length){const unsigned char *p=data;while(length){ssize_t n=write(fd,p,length);if(n<0&&errno==EINTR)continue;if(n<=0)return -1;p+=n;length-=n;}return 0;}
static int seal_bytes(const void *data,size_t length){int fd=syscall(SYS_memfd_create,"overte-trusted-stage",MFD_ALLOW_SEALING|MFD_CLOEXEC);if(fd<0)return -1;if(fullwrite(fd,data,length)||fcntl(fd,F_ADD_SEALS,SEALS)){close(fd);return -1;}return fd;}
static int putfd(int source,int target){if(source==target)return fcntl(target,F_SETFD,0);int result=dup2(source,target);close(source);return result;}

// Descriptor-relative canonical ancestry: no symlink or group/other writable
// ancestor. Only root may replace installed code/policy after verification.
static int rootnode(const char *path,int directory){
 if(!path||path[0]!='/'||strlen(path)>4096||strstr(path,"//")||path[strlen(path)-1]=='/')return -1;
 char copy[4097];strcpy(copy,path+1);char *save=NULL,*part=strtok_r(copy,"/",&save);
 int current=open("/",O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(current<0)return -1;
 struct stat st;if(fstat(current,&st)||st.st_uid||st.st_mode&022){close(current);return -1;}
 while(part){char *next=strtok_r(NULL,"/",&save);if(!strcmp(part,".")||!strcmp(part,"..")){close(current);return -1;}
  int fd=openat(current,part,O_RDONLY|O_NOFOLLOW|O_CLOEXEC|(next?O_DIRECTORY:0));close(current);if(fd<0)return -1;
  if(fstat(fd,&st)||st.st_uid||(st.st_mode&022)||((next||directory)?!S_ISDIR(st.st_mode):!S_ISREG(st.st_mode))){close(fd);return -1;}
  current=fd;part=next;
 }return current;
}
// Isolated Python still imports its signed distro standard library. Validate
// every possible import root recursively, not only the top directory. No user
// writable/symlink descendant can become a Python import after capability drop.
static int rootfile(const char *path){return rootnode(path,0);}
// Fixed diagnostic progress only; no path, alias, descriptor or runtime label.
static void inspection_phase(enum setup_phase *phase,enum setup_phase next) {
 *phase=next;errno=0;
}
static int import_tree(int fd,unsigned *entries,unsigned depth,enum setup_phase *phase) {
 inspection_phase(phase,SETUP_PYTHON_IMPORT_SCAN);
 if(depth>32)return -1;
 struct stat info;if(fstat(fd,&info)||info.st_uid||(info.st_mode&022)||!S_ISDIR(info.st_mode))return -1;
 int copy=dup(fd);if(copy<0)return -1;DIR *directory=fdopendir(copy);if(!directory){close(copy);return -1;}
 int result=-1;struct dirent *entry;
 while((inspection_phase(phase,SETUP_PYTHON_IMPORT_SCAN),errno=0,(entry=readdir(directory)))) {
  if(!strcmp(entry->d_name,".")||!strcmp(entry->d_name,".."))continue;
  if(++*entries>16384)goto done;
  struct stat child;if(fstatat(fd,entry->d_name,&child,AT_SYMLINK_NOFOLLOW)||child.st_uid)goto done;
  if(S_ISLNK(child.st_mode)) {
   char name[8192],resolved[4097];int length=snprintf(name,sizeof(name),"/proc/self/fd/%d/%s",fd,entry->d_name);
   if(length<1||length>=(int)sizeof(name))goto done;
   inspection_phase(phase,SETUP_PYTHON_ALIAS_RESOLVE);if(!realpath(name,resolved))goto done;
   inspection_phase(phase,SETUP_PYTHON_ALIAS_TARGET);int target=rootfile(resolved);if(target<0)goto done;
   int checked=verify_import_alias_target(target,resolved);int saved=errno;close(target);errno=saved;if(checked)goto done;continue;
  }
  if(child.st_mode&022)goto done;
  if(S_ISDIR(child.st_mode)) {
   int next=openat(fd,entry->d_name,O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC);if(next<0)goto done;
   int checked=import_tree(next,entries,depth+1,phase);close(next);if(checked)goto done;
  } else if(!S_ISREG(child.st_mode))goto done;
 }
 if(errno)goto done;
 result=0;
 done:closedir(directory);return result;
}
static int verify_import_roots(enum setup_phase *phase) {
 import_alias_reads=0;import_alias_read_bytes=0;
 unsigned entries=0;
 for(unsigned i=0;i<PYTHON_IMPORT_COUNT;i++) {
  const char *path=PYTHON_IMPORT_PATHS[i];inspection_phase(phase,SETUP_PYTHON_IMPORT_OPEN);int fd=rootnode(path,strstr(path,".zip")==NULL);
  if(fd<0) {
   if(errno!=ENOENT||!strstr(path,".zip"))return -1;
   char parent[4097];if(strlen(path)>4096)return -1;strcpy(parent,path);char *tail=strrchr(parent,'/');if(!tail||tail==parent)return -1;*tail=0;
   inspection_phase(phase,SETUP_PYTHON_IMPORT_OPEN);fd=rootnode(parent,1);if(fd<0)return -1;
   inspection_phase(phase,SETUP_PYTHON_IMPORT_STAT);struct stat st;int invalid=fstat(fd,&st)||st.st_uid||(st.st_mode&022);close(fd);if(invalid)return -1;
   continue;
  }
  inspection_phase(phase,SETUP_PYTHON_IMPORT_STAT);struct stat info;if(fstat(fd,&info)||info.st_uid||(info.st_mode&022)){close(fd);return -1;}
  int invalid=S_ISDIR(info.st_mode)?import_tree(fd,&entries,0,phase):!S_ISREG(info.st_mode);close(fd);if(invalid)return -1;
 }
 return 0;
}
// Deliberately use OpenSSL's bounded SHA-256 primitive, without EVP provider,
// engine or configuration initialization. Its algorithm bytes remain exact;
// the deprecated low-level API avoids any runtime module loading in setup.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
static int digest_bytes(const void *input,size_t length,unsigned char output[32]) {
 SHA256_CTX context;
 return SHA256_Init(&context)==1&&SHA256_Update(&context,input,length)==1&&SHA256_Final(output,&context)==1;
}
#pragma GCC diagnostic pop
static int verified_sealed(const char *path,const unsigned char expected[32],size_t limit){
 int fd=rootfile(path);if(fd<0)return -1;struct stat st;unsigned char *data=NULL;int result=-1;
 if(fstat(fd,&st)||st.st_size<1||(uint64_t)st.st_size>limit)goto done;
 data=malloc(st.st_size);if(!data)goto done;size_t offset=0;
 while(offset<(size_t)st.st_size){ssize_t n=read(fd,data+offset,st.st_size-offset);if(n<0&&errno==EINTR)continue;if(n<=0)goto done;offset+=n;}
 unsigned char tail,digest[32];if(read(fd,&tail,1)!=0||!digest_bytes(data,offset,digest)||memcmp(digest,expected,32))goto done;
 struct stat after;if(fstat(fd,&after)||after.st_size!=st.st_size||after.st_ino!=st.st_ino||after.st_dev!=st.st_dev)goto done;
 result=seal_bytes(data,offset);
 done:free(data);close(fd);return result;
}
static int binary_hash(int fd,const unsigned char expected[32]) {
 struct stat st;if(fstat(fd,&st)||st.st_size<1||st.st_size>33554432||!(st.st_mode&0111)||(st.st_mode&06000))return -1;
 unsigned char *bytes=malloc(st.st_size);if(!bytes)return -1;size_t offset=0;int result=-1;
 while(offset<(size_t)st.st_size){ssize_t n=pread(fd,bytes+offset,st.st_size-offset,offset);if(n<0&&errno==EINTR)continue;if(n<=0)goto done;offset+=n;}
 unsigned char digest[32];if(digest_bytes(bytes,offset,digest)&&!memcmp(digest,expected,32))result=0;
 done:free(bytes);return result;
}
static int initially_unprivileged(void) {
 struct __user_cap_header_struct h={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct d[2]={{0},{0}};
 if(syscall(SYS_capget,&h,d))return -1;
 for(int i=0;i<2;i++)if(d[i].effective||d[i].permitted||d[i].inheritable)return -1;
 for(int i=0;i<64;i++){int n=prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_IS_SET,i,0,0);if(n<0){return errno==EINVAL?0:-1;}if(n)return -1;}
 return -1;
}
static int config_sealed(void){
 struct stat st;if(fstat(3,&st)||!S_ISREG(st.st_mode)||st.st_uid!=getuid()||(st.st_mode&077)||st.st_size<1||st.st_size>LIMIT)return -1;
 unsigned char *data=malloc(st.st_size);if(!data)return -1;size_t count=0;
 while(count<(size_t)st.st_size){ssize_t n=pread(3,data+count,st.st_size-count,count);if(n<0&&errno==EINTR)continue;if(n<=0){free(data);return -1;}count+=n;}
 int result=seal_bytes(data,count);free(data);return result;
}
static int profile(void){char data[128];int fd=open("/proc/self/attr/apparmor/current",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return -1;ssize_t n=read(fd,data,sizeof(data));close(fd);const char *expected="overte-browser-network-setup (enforce)";if(n>0&&data[n-1]=='\n')n--;return n==(ssize_t)strlen(expected)&&memcmp(data,expected,n)==0?0:-1;}
static int mapfile(const char *name,uid_t identity){char data[32];int size=overte_self_map(identity,data,sizeof(data));if(!size)return -1;int fd=open(name,O_WRONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return -1;int result=fullwrite(fd,data,size);close(fd);return result;}
static int groups_deny(void){int fd=open("/proc/self/setgroups",O_WRONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)return -1;int result=fullwrite(fd,"deny\n",5);close(fd);return result;}
static int waitfd(int fd,long long deadline){for(;;){long long remaining=deadline-milliseconds();if(remaining<=0||stopped){errno=ETIMEDOUT;return -1;}struct pollfd p={fd,POLLIN,0};int n=poll(&p,1,remaining>100?100:(int)remaining);if(n<0&&errno==EINTR)continue;if(n<0)return -1;if(n>0)return (p.revents&POLLIN)?0:-1;}}
static int recv_kernel(int fd,void *output,size_t limit,long long deadline){
 if(waitfd(fd,deadline))return -1;
 struct sockaddr_nl peer={0};struct iovec vector={output,limit};struct msghdr message={.msg_name=&peer,.msg_namelen=sizeof(peer),.msg_iov=&vector,.msg_iovlen=1};
 ssize_t n=recvmsg(fd,&message,0);if(n<1||(message.msg_flags&MSG_TRUNC)||message.msg_namelen!=sizeof(peer)||peer.nl_family!=AF_NETLINK||peer.nl_pid!=0)return -1;return (int)n;
}
static int send_kernel(int fd,const void *data,size_t size){struct sockaddr_nl peer={.nl_family=AF_NETLINK};return sendto(fd,data,size,0,(struct sockaddr*)&peer,sizeof(peer))==(ssize_t)size?0:-1;}
static int install_routes(int fd,long long deadline){
 unsigned char request[64],response[128];for(unsigned route=0;route<12;route++){
  size_t size=overte_route_message(route,route+1,request,sizeof(request));if(!size||send_kernel(fd,request,size))return -1;
  int count=recv_kernel(fd,response,sizeof(response),deadline);if(count<0)return -1;
  int result=overte_route_ack(response,count,route+1);if(result!=1){errno=result<0?-result:EPROTO;return -1;}
 }return 0;
}
static int routes_readback(int fd,long long deadline){
 struct {struct nlmsghdr h;struct rtmsg r;} request={.h={.nlmsg_len=NLMSG_LENGTH(sizeof(struct rtmsg)),.nlmsg_type=RTM_GETROUTE,.nlmsg_flags=NLM_F_REQUEST|NLM_F_DUMP,.nlmsg_seq=100},.r={.rtm_family=AF_INET}};
 if(send_kernel(fd,&request,sizeof(request)))return -1;
 unsigned seen=0;size_t total=0;_Alignas(struct nlmsghdr) unsigned char response[8192];
 for(unsigned packets=0;packets<64;packets++){
  int count=recv_kernel(fd,response,sizeof(response),deadline);if(count<0)return -1;total+=count;if(total>131072)return -1;
  int remaining=count;for(struct nlmsghdr *h=(void*)response;NLMSG_OK(h,remaining);h=NLMSG_NEXT(h,remaining)){
   if(h->nlmsg_seq!=100||(h->nlmsg_flags&NLM_F_DUMP_INTR))return -1;
   if(h->nlmsg_type==NLMSG_DONE){if(h->nlmsg_len!=NLMSG_LENGTH(sizeof(int))||*(int*)NLMSG_DATA(h)!=0||remaining!=(int)NLMSG_ALIGN(h->nlmsg_len))return -1;return seen==0xfff?0:-1;}
   if(h->nlmsg_type!=RTM_NEWROUTE||h->nlmsg_len<NLMSG_LENGTH(sizeof(struct rtmsg)))return -1;
   struct rtmsg *r=NLMSG_DATA(h);if(r->rtm_family!=AF_INET||r->rtm_table!=RT_TABLE_MAIN||r->rtm_type!=RTN_PROHIBIT)continue;
   int bytes=RTM_PAYLOAD(h);struct in_addr address={0};int found=0;
   for(struct rtattr *a=RTM_RTA(r);RTA_OK(a,bytes);a=RTA_NEXT(a,bytes))if(a->rta_type==RTA_DST){if(found||RTA_PAYLOAD(a)!=4)return -1;memcpy(&address,RTA_DATA(a),4);found=1;}
   if(bytes)return -1;
   for(unsigned i=0;i<12;i++){struct in_addr wanted;inet_pton(AF_INET,denied[i].address,&wanted);if(found&&r->rtm_dst_len==denied[i].prefix&&address.s_addr==wanted.s_addr){if(seen&(1u<<i))return -1;seen|=1u<<i;}}
  }if(remaining)return -1;
 }return -1;
}
static int await_tap(long long deadline){
 while(!stopped&&milliseconds()<deadline){struct ifaddrs *list;if(!getifaddrs(&list)){int found=0;for(struct ifaddrs *a=list;a;a=a->ifa_next)if(a->ifa_addr&&a->ifa_addr->sa_family==AF_INET&&!strcmp(a->ifa_name,"tap0")&&((struct sockaddr_in*)a->ifa_addr)->sin_addr.s_addr==inet_addr("10.0.2.100"))found=1;freeifaddrs(list);if(found)return 0;}struct timespec pause={0,50000000};nanosleep(&pause,NULL);}errno=ETIMEDOUT;return -1;
}
static int attestation(uid_t uid,gid_t gid,pid_t parent){struct stat user,net;if(stat("/proc/self/ns/user",&user)||stat("/proc/self/ns/net",&net))return -1;char data[512];int n=snprintf(data,sizeof(data),"{\"version\":1,\"hostUID\":%u,\"hostGID\":%u,\"parentPID\":%u,\"userNS\":[%llu,%llu],\"netNS\":[%llu,%llu],\"routes\":12}",uid,gid,parent,(unsigned long long)user.st_dev,(unsigned long long)user.st_ino,(unsigned long long)net.st_dev,(unsigned long long)net.st_ino);return n>0&&n<(int)sizeof(data)?seal_bytes(data,n):-1;}
static const char bootstrap[]=
 "import os,fcntl,types,sys\n"
 "fds=(4,5,6,7)\n"
 "names=('trusted_owner','network_udp','network_route_diagnostics','owner_admission')\n"
 "sources={}\n"
 "for name,fd in zip(names,fds):\n"
 " assert fcntl.fcntl(fd,fcntl.F_GET_SEALS)&15==15\n"
 " size=os.fstat(fd).st_size\n"
 " assert 0<size<=262144\n"
 " sources[name]=os.pread(fd,size+1,0)\n"
 " assert len(sources[name])==size\n"
 " os.close(fd)\n"
 "for name in ('network_udp','network_route_diagnostics','owner_admission','trusted_owner'):\n"
 " module=types.ModuleType(name)\n"
 " module.__file__='<sealed-trusted-module>'\n"
 " sys.modules[name]=module\n"
 " exec(compile(sources.pop(name),module.__file__,'exec'),module.__dict__)\n"
 "sys.exit(sys.modules['trusted_owner'].main())\n";

// The sole typed member is generated only after exact signed package and
// installed-byte authentication. Both branches debit the SAME original count
// and read-byte budgets. This does not expand the general 4MiB verifier.
#if PYTHON_SIGNED_LIBRARY_COUNT == 1
// Match the existing bounded primitive: no EVP/provider/configuration loading.
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wdeprecated-declarations"
static int verify_signed_library_target(int fd,const char *resolved) {
 if(strcmp(PYTHON_PATH,SIGNED_LIBRARY_PYTHON_PATH)||memcmp(PYTHON_HASH,SIGNED_LIBRARY_PYTHON_HASH,32)||strcmp(resolved,SIGNED_LIBRARY_PATH)){errno=EINVAL;return -1;}
 if(++import_alias_reads>128){errno=EINVAL;return -1;}
 struct stat before,after;
 if(fstat(fd,&before))return -1;
 if(!S_ISREG(before.st_mode)||before.st_uid||(before.st_mode&022)||before.st_size!=SIGNED_LIBRARY_BYTES||SIGNED_LIBRARY_BYTES>16777216){errno=EPERM;return -1;}
 if(import_alias_read_bytes+(uint64_t)before.st_size>33554432){errno=EFBIG;return -1;}
 import_alias_read_bytes+=(uint64_t)before.st_size;
 unsigned char bytes[65536],digest[32],tail;size_t offset=0;int result=-1;
 SHA256_CTX hash;if(!SHA256_Init(&hash))return -1;
 while(offset<(size_t)before.st_size){
  size_t length=(size_t)before.st_size-offset;if(length>sizeof(bytes))length=sizeof(bytes);
  ssize_t count=pread(fd,bytes,length,(off_t)offset);
  if(count<0&&errno==EINTR)continue;
  if(count<=0){if(!count)errno=EIO;goto done;}
  if(!SHA256_Update(&hash,bytes,(size_t)count))goto done;
  offset+=(size_t)count;
 }
 if(pread(fd,&tail,1,(off_t)offset)!=0||fstat(fd,&after))goto done;
 if(before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||before.st_size!=after.st_size||
    before.st_mtim.tv_sec!=after.st_mtim.tv_sec||before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec||
    before.st_ctim.tv_sec!=after.st_ctim.tv_sec||before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec||
    before.st_uid!=after.st_uid||before.st_mode!=after.st_mode){errno=ESTALE;goto done;}
 if(!SHA256_Final(digest,&hash)||memcmp(digest,SIGNED_LIBRARY_HASH,32)){errno=ESTALE;goto done;}
 result=0;
 done:return result;
}
#pragma GCC diagnostic pop
#endif

// Hash only exact build-discovered, manifest-reviewed canonical aliases. No
// browser argument/profile wildcard can add a target. Original rootfile gates
// already bind this descriptor to immutable root-owned canonical ancestry.
static int verify_import_alias_target(int fd,const char *resolved) {
#if PYTHON_SIGNED_LIBRARY_COUNT == 1
 if(!strcmp(resolved,SIGNED_LIBRARY_PATH))return verify_signed_library_target(fd,resolved);
#endif
 int index=-1;
 for(int i=0;i<PYTHON_IMPORT_ALIAS_COUNT;i++)if(!strcmp(resolved,PYTHON_IMPORT_ALIAS_PATHS[i])){index=i;break;}
 if(index<0||++import_alias_reads>128){errno=EINVAL;return -1;}
 struct stat before;
 if(fstat(fd,&before))return -1;
 if(!S_ISREG(before.st_mode)||before.st_uid||(before.st_mode&022)||before.st_size<0||before.st_size>4194304||before.st_size!=(off_t)PYTHON_IMPORT_ALIAS_BYTES[index]){errno=EPERM;return -1;}
 if(import_alias_read_bytes+(uint64_t)before.st_size>33554432){errno=EFBIG;return -1;}
 import_alias_read_bytes+=(uint64_t)before.st_size;
 unsigned char *bytes=malloc(before.st_size?(size_t)before.st_size:1);if(!bytes)return -1;
 size_t offset=0;int result=-1;
 while(offset<(size_t)before.st_size){
  ssize_t n=pread(fd,bytes+offset,(size_t)before.st_size-offset,(off_t)offset);
  if(n<0&&errno==EINTR)continue;
  if(n<=0){if(!n)errno=EIO;goto done;}
  offset+=(size_t)n;
 }
 unsigned char tail,digest[32];ssize_t extra=pread(fd,&tail,1,(off_t)offset);
 if(extra<0)goto done;
 if(extra||!digest_bytes(bytes,offset,digest)||memcmp(digest,PYTHON_IMPORT_ALIAS_HASHES[index],32)){errno=ESTALE;goto done;}
 struct stat after;if(fstat(fd,&after))goto done;
 if(before.st_dev!=after.st_dev||before.st_ino!=after.st_ino||before.st_size!=after.st_size||before.st_mtim.tv_sec!=after.st_mtim.tv_sec||before.st_mtim.tv_nsec!=after.st_mtim.tv_nsec||before.st_ctim.tv_sec!=after.st_ctim.tv_sec||before.st_ctim.tv_nsec!=after.st_ctim.tv_nsec){errno=ESTALE;goto done;}
 result=0;
 done:free(bytes);return result;
}

int main(int argc,char **argv){
 (void)argv;uid_t uid=getuid();gid_t gid=getgid();pid_t parent=getppid();int code=78;
 enum setup_phase failure_phase=SETUP_ADMISSION;int failure_errno=0;
 #define PHASE(value) do{failure_phase=(value);errno=0;}while(0)
 #define FAIL_IF(value) do{if(value){failure_errno=errno;goto fail;}}while(0)
 #define ROUTE_FAIL_IF(value) do{if(value){failure_errno=errno;close(route);goto fail;}}while(0)
 // No arbitrary arguments/command/environment are accepted. Profile selected
 // at exec, before namespace creation; ordinary/unrecognized labels refuse.
 PHASE(SETUP_ADMISSION);FAIL_IF(argc!=1||uid==0||gid==0||uid!=geteuid()||gid!=getegid());
 PHASE(SETUP_INITIAL_CAPABILITIES);FAIL_IF(initially_unprivileged());
 PHASE(SETUP_INSTALLED_PROFILE);FAIL_IF(profile());
 PHASE(SETUP_INITIAL_NNP);FAIL_IF(prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=0);
 PHASE(SETUP_ENVIRONMENT);FAIL_IF(clearenv()||setenv("PATH","/usr/bin:/bin:/usr/sbin:/sbin",1)||setenv("LANG","C.UTF-8",1));
 PHASE(SETUP_SIGNALS);struct sigaction action={.sa_handler=stop};sigemptyset(&action.sa_mask);FAIL_IF(sigaction(SIGTERM,&action,NULL)||sigaction(SIGINT,&action,NULL));
 PHASE(SETUP_CONFIGURATION);int configuration=config_sealed();FAIL_IF(configuration<0);
 int modules[4]={-1,-1,-1,-1};for(int i=0;i<4;i++){PHASE(SETUP_OWNER_MODULES);modules[i]=verified_sealed(OWNER_PATHS[i],OWNER_HASHES[i],SOURCE_LIMIT);FAIL_IF(modules[i]<0);}
 PHASE(SETUP_POLICY);int policy=verified_sealed(POLICY_PATH,POLICY_HASH,LIMIT);FAIL_IF(policy<0);
 PHASE(SETUP_PYTHON_OPEN);int python=rootfile(PYTHON_PATH);FAIL_IF(python<0);
 PHASE(SETUP_PYTHON_HASH);FAIL_IF(binary_hash(python,PYTHON_HASH));
 PHASE(SETUP_PYTHON_IMPORT_ROOTS);FAIL_IF(verify_import_roots(&failure_phase));
 // Relocate above all prescribed fd slots before closing inherited fds.
 int selected[6]={configuration,modules[0],modules[1],modules[2],modules[3],policy};
 for(int i=0;i<6;i++){PHASE(SETUP_HANDOFF_RELOCATE);int copy=fcntl(selected[i],F_DUPFD_CLOEXEC,32);int saved=errno;close(selected[i]);if(copy<0){failure_errno=saved;goto fail;}selected[i]=copy;}
 PHASE(SETUP_HANDOFF_RELOCATE);int python_copy=fcntl(python,F_DUPFD_CLOEXEC,32);int saved=errno;close(python);python=python_copy;if(python<0){failure_errno=saved;goto fail;}
 for(int fd=3;fd<32;fd++)close(fd);
 PHASE(SETUP_USER_NAMESPACE);FAIL_IF(unshare(CLONE_NEWUSER));
 PHASE(SETUP_GROUPS_DENY);FAIL_IF(groups_deny());
 PHASE(SETUP_UID_MAP);FAIL_IF(mapfile("/proc/self/uid_map",uid));
 PHASE(SETUP_GID_MAP);FAIL_IF(mapfile("/proc/self/gid_map",gid));
 PHASE(SETUP_NETWORK_NAMESPACE);FAIL_IF(overte_new_network_namespace());
 PHASE(SETUP_LIFETIME);FAIL_IF(prctl(PR_SET_PDEATHSIG,SIGTERM,0,0,0)||prctl(PR_SET_CHILD_SUBREAPER,1,0,0,0)||getppid()!=parent||stopped);
 puts("OVERTE_NET_OWNER_READY");fflush(stdout);long long deadline=milliseconds()+10000;
 PHASE(SETUP_TAP_READY);FAIL_IF(await_tap(deadline));
 PHASE(SETUP_ROUTE_SOCKET);int route=socket(AF_NETLINK,SOCK_RAW|SOCK_CLOEXEC,NETLINK_ROUTE);FAIL_IF(route<0);
 struct sockaddr_nl local={.nl_family=AF_NETLINK};int one=1;
 PHASE(SETUP_ROUTE_BIND);ROUTE_FAIL_IF(bind(route,(struct sockaddr*)&local,sizeof(local)));
 PHASE(SETUP_ROUTE_ACK_OPTION);ROUTE_FAIL_IF(setsockopt(route,SOL_NETLINK,NETLINK_CAP_ACK,&one,sizeof(one)));
 PHASE(SETUP_ROUTE_INSTALL);ROUTE_FAIL_IF(install_routes(route,deadline));
 PHASE(SETUP_ROUTE_READBACK);ROUTE_FAIL_IF(routes_readback(route,deadline));close(route);
 PHASE(SETUP_ATTESTATION);int proof=attestation(uid,gid,parent);FAIL_IF(proof<0);
 PHASE(SETUP_ATTESTATION_RELOCATE);int proof_copy=fcntl(proof,F_DUPFD_CLOEXEC,32);saved=errno;close(proof);proof=proof_copy;if(proof<0){failure_errno=saved;goto fail;}
 PHASE(SETUP_RETIRE_CAPS);FAIL_IF(overte_retire_setup_capabilities());
 PHASE(SETUP_POST_RETIRE_LIFETIME);FAIL_IF(getppid()!=parent||stopped);
 PHASE(SETUP_HANDOFF_DESCRIPTORS);FAIL_IF(putfd(selected[0],3)<0||putfd(selected[1],4)<0||putfd(selected[2],5)<0||putfd(selected[3],6)<0||putfd(selected[4],7)<0||putfd(selected[5],8)<0||putfd(proof,9)<0);
 // Close every inherited descriptor except stdio and exact sealed handoff.
 // close_range is mandatory on the reviewed Ubuntu kernel; no guessed max-FD.
 PHASE(SETUP_CLOSE_INHERITED);FAIL_IF(putfd(python,10)<0||fcntl(10,F_SETFD,FD_CLOEXEC)||syscall(SYS_close_range,11u,~0u,0u));
 char *arguments[]={PYTHON_PATH,"-I","-S","-c",(char*)bootstrap,NULL};
 char *environment[]={"PATH=/usr/bin:/bin:/usr/sbin:/sbin","LANG=C.UTF-8",NULL};
 PHASE(SETUP_EXEC_PYTHON);fexecve(10,arguments,environment);failure_errno=errno;
 fail: {
  char summary[192];if(setup_failure_json(failure_phase,failure_errno,summary,sizeof(summary)))fprintf(stderr,"OVERTE_NET_TRUSTED_FAILURE=%s\n",summary);
  fputs("Trusted network setup refused.\n",stderr);return code;
 }
 #undef ROUTE_FAIL_IF
 #undef FAIL_IF
 #undef PHASE
}
