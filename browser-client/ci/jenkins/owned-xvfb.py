#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run one unchanged headed gate on an authenticated, owned verified Xvfb."""
import argparse
import os
from pathlib import Path
import secrets
import selectors
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
from run import checked_executable, stop_owned


def display_number(process, descriptor, deadline, cancelled=lambda: False):
    payload=bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(descriptor, selectors.EVENT_READ)
        while time.monotonic()<deadline:
            if cancelled():raise RuntimeError('owned-xvfb-cancelled')
            if process.poll() is not None:raise RuntimeError('owned-xvfb-exited-before-display')
            for _key,_mask in selector.select(.05):
                data=os.read(descriptor,32)
                if not data:raise RuntimeError('owned-xvfb-display-pipe-closed')
                payload.extend(data)
                if len(payload)>16:raise RuntimeError('owned-xvfb-display-output-limit')
                if b'\n' in payload:
                    if payload.count(b'\n')!=1 or not payload.endswith(b'\n') or not payload[:-1].isdigit():raise RuntimeError('owned-xvfb-invalid-display')
                    number=int(payload[:-1])
                    if not 0<=number<=65535:raise RuntimeError('owned-xvfb-invalid-display')
                    return number
    raise RuntimeError('owned-xvfb-startup-deadline')


def authenticated_setup(filename, process, cookie, deadline):
    """The allocated socket must be the owned child's actual authenticated X11."""
    if len(cookie)!=16:raise RuntimeError('owned-xvfb-invalid-cookie-size')
    connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise RuntimeError('owned-xvfb-startup-deadline')
        connection.settimeout(min(remaining,2))
        connection.connect(str(filename))
        pid,uid,_gid=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if pid!=process.pid or uid!=os.getuid():raise RuntimeError('owned-xvfb-socket-owner-mismatch')
        name=b'MIT-MAGIC-COOKIE-1'
        request=struct.pack('<BBHHHHH',ord('l'),0,11,0,len(name),len(cookie),0)+name+b'\0'*((-len(name))%4)+cookie
        connection.sendall(request)
        def receive(length):
            result=bytearray()
            while len(result)<length:
                remaining=deadline-time.monotonic()
                if remaining<=0:raise RuntimeError('owned-xvfb-startup-deadline')
                connection.settimeout(min(remaining,2))
                value=connection.recv(length-len(result))
                if not value:raise RuntimeError('owned-xvfb-incomplete-X11-setup')
                result.extend(value)
            return bytes(result)
        header=receive(8)
        status,_unused,major,minor,length=struct.unpack('<BBHHH',header)
        if status!=1 or major!=11 or minor!=0 or not 1<=length<=16384:raise RuntimeError('owned-xvfb-authenticated-X11-setup-refused')
        receive(length*4)
    finally:connection.close()


def owned_command(command, *, environment, log, input_bytes=None, timeout=10, cancelled=lambda:False):
    launcher=Path(__file__).resolve().parent/'owned-exec.py'
    child=subprocess.Popen([sys.executable,str(launcher),str(os.getpid()),*command],
        env=environment,stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
        stdout=log,stderr=log,start_new_session=True)
    try:
        if input_bytes is not None:
            child.stdin.write(input_bytes);child.stdin.close()
        deadline=time.monotonic()+timeout
        while child.poll() is None:
            if cancelled():raise RuntimeError('owned-xvfb-cancelled')
            if time.monotonic()>=deadline:raise RuntimeError('owned-xvfb-command-deadline')
            if os.fstat(log.fileno()).st_size>1024*1024:raise RuntimeError('owned-xvfb-private-log-size-limit')
            time.sleep(.05)
        if child.returncode:raise RuntimeError('owned-xvfb-auth-file-command-failed')
    finally:stop_owned(child)


def run_gate(xvfb,xauth,command,runtime,environment):
    cancelled=False
    def cancel(_signum,_frame):
        nonlocal cancelled
        cancelled=True
    old={number:signal.signal(number,cancel) for number in (signal.SIGTERM,signal.SIGINT)}
    server=gate=None
    temporary=None
    try:
        temporary=tempfile.TemporaryDirectory(prefix='owned-xvfb-',dir=runtime)
        directory=temporary.name
        authority=Path(directory)/'Xauthority';authority.touch(mode=0o600);cookie=secrets.token_bytes(16)
        with (Path(directory)/'server-private.log').open('wb') as log:
            env={**environment,'XAUTHORITY':str(authority)};env.pop('DISPLAY',None)
            # stdin keeps the ephemeral cookie out of argv/process listings.
            def authenticate(number):owned_command([xauth,'-q','-f',str(authority)],environment=env,log=log,
                input_bytes=f'add :{number} MIT-MAGIC-COOKIE-1 {cookie.hex()}\n'.encode(),cancelled=lambda:cancelled)
            authenticate(0)
            readfd,writefd=os.pipe()
            try:
                server=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parent/'owned-exec.py'),str(os.getpid()),xvfb,
                    '-displayfd',str(writefd),'-screen','0','1280x900x24','-nolisten','tcp','-auth',str(authority),'-noreset'],
                    pass_fds=(writefd,),env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
                os.close(writefd);writefd=None
                deadline=time.monotonic()+10
                number=display_number(server,readfd,deadline,lambda:cancelled)
                authenticated_setup(Path('/tmp/.X11-unix')/f'X{number}',server,cookie,deadline)
                authenticate(number)
            finally:
                os.close(readfd)
                if writefd is not None:os.close(writefd)
            gate=subprocess.Popen([sys.executable,str(Path(__file__).resolve().parent/'owned-exec.py'),str(os.getpid()),*command],
                env={**env,'DISPLAY':f':{number}'},start_new_session=True)
            while gate.poll() is None:
                if cancelled:raise RuntimeError('owned-xvfb-cancelled')
                if server.poll() is not None:raise RuntimeError('owned-xvfb-exited-during-headed-gate')
                if os.fstat(log.fileno()).st_size>1024*1024:raise RuntimeError('owned-xvfb-private-log-size-limit')
                time.sleep(.05)
            return gate.returncode
    finally:
        # Browsers finish before their display disappears. Signal only the exact
        # recorded private Popen process groups, with the existing checked bound.
        try:stop_owned(gate)
        finally:
            try:stop_owned(server)
            finally:
                for number,handler in old.items():signal.signal(number,handler)
                if temporary is not None:temporary.cleanup()


def main():
    from gates import isolated_identity
    isolated_identity()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lab-root',type=Path,required=True)
    parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command:raise RuntimeError('owned-xvfb-headed-command-required')
    runtime=args.runtime.resolve(strict=True)
    if runtime!=Path('/tmp/overte-ci-runtime') or runtime.stat().st_uid!=os.getuid() or runtime.stat().st_mode&0o077:raise RuntimeError('owned-xvfb-requires-private-job-runtime')
    root=args.lab_root.resolve(strict=True)
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'lab'))
    from host_tools import load_tools
    tools=load_tools(root)
    return run_gate(tools['xvfb'],checked_executable('xauth'),[checked_executable(command[0]),*command[1:]],runtime,dict(os.environ))


if __name__=='__main__':
    try:raise SystemExit(main())
    except (RuntimeError,OSError,ValueError,subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error,RuntimeError) else 'owned-xvfb-system-failure',file=sys.stderr)
        raise SystemExit(1)
