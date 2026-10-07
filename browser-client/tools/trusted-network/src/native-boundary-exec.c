// SPDX-License-Identifier: Apache-2.0
// Fixed final native boundary guard: namespace-local caps MUST all be zero.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/capability.h>
#include <stdio.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>
#define OVERTE_NATIVE_BOUNDARY 1
#include "image.h"
extern char **environ;
static int zero_capabilities(void){
 struct __user_cap_header_struct header={_LINUX_CAPABILITY_VERSION_3,0};struct __user_cap_data_struct data[2]={{0},{0}};
 if(syscall(SYS_capget,&header,data))return -1;
 for(int i=0;i<2;i++)if(data[i].effective||data[i].permitted||data[i].inheritable)return -1;
 for(int i=0;i<64;i++){
  int bound=prctl(PR_CAPBSET_READ,i,0,0,0);if(bound<0){if(errno==EINVAL)return 0;return -1;}
  if(bound||prctl(PR_CAP_AMBIENT,PR_CAP_AMBIENT_IS_SET,i,0,0)!=0)return -1;
 }return -1;
}
int main(int argc,char **argv){
 // The installed guard is reached only AFTER bwrap has completed its own new
 // user/PID/mount/IPC/UTS/session construction and final capability drop.
 if(argc<2||argc>256||prctl(PR_GET_NO_NEW_PRIVS,0,0,0,0)!=1||zero_capabilities())goto fail;
 int accepted=0;for(int i=0;i<NATIVE_EXECUTABLE_COUNT;i++)if(!strcmp(argv[1],NATIVE_EXECUTABLES[i]))accepted=1;
 if(!accepted)goto fail;
 size_t bytes=0;for(int i=1;i<argc;i++){size_t n=strnlen(argv[i],8193);if(n>8192||bytes+n>131072)goto fail;bytes+=n;}
 char label[128];int fd=open("/proc/self/attr/apparmor/current",O_RDONLY|O_NOFOLLOW|O_CLOEXEC);if(fd<0)goto fail;
 ssize_t n=read(fd,label,sizeof(label));close(fd);if(n>0&&label[n-1]=='\n')n--;
 const char *expected="bwrap//&unpriv_bwrap (enforce)";
 if(n!=(ssize_t)strlen(expected)||memcmp(label,expected,n))goto fail;
 execve(argv[1],argv+1,environ);
 fail:fputs("Native capability boundary refused.\n",stderr);return 78;
}
