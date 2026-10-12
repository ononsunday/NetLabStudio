"""Explicit code execution and self-contained loopback programming exercises.

This is a bounded child-process runner, NOT a security sandbox. The UI must make
that fact visible and invoke execution only when the user presses Run.
"""
from __future__ import annotations

import contextlib
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


class _WindowsJob:
    def __init__(self, process):
        self.handle = None
        if os.name != "nt":
            return
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit",ctypes.c_longlong),("PerJobUserTimeLimit",ctypes.c_longlong),
                        ("LimitFlags",wintypes.DWORD),("MinimumWorkingSetSize",ctypes.c_size_t),("MaximumWorkingSetSize",ctypes.c_size_t),
                        ("ActiveProcessLimit",wintypes.DWORD),("Affinity",ctypes.c_size_t),("PriorityClass",wintypes.DWORD),("SchedulingClass",wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name,ctypes.c_ulonglong) for name in ("ReadOperationCount","WriteOperationCount","OtherOperationCount","ReadTransferCount","WriteTransferCount","OtherTransferCount")]
        class Extended(ctypes.Structure):
            _fields_ = [("BasicLimitInformation",Basic),("IoInfo",IO),("ProcessMemoryLimit",ctypes.c_size_t),("JobMemoryLimit",ctypes.c_size_t),("PeakProcessMemoryUsed",ctypes.c_size_t),("PeakJobMemoryUsed",ctypes.c_size_t)]
        kernel = ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateJobObjectW(None,None)
        info = Extended()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if handle and kernel.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)) and kernel.AssignProcessToJobObject(handle,wintypes.HANDLE(process._handle)):
            self.handle, self.kernel = handle,kernel
        elif handle:
            kernel.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None


def _terminate(process):
    import psutil
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        children = []
    for child in children:
        with contextlib.suppress(psutil.Error):
            child.kill()
    with contextlib.suppress(OSError):
        process.kill()


def _run(args, directory, seconds, output_limit=262144):
    start = time.perf_counter()
    with open(Path(directory)/"stdout.log","wb") as stdout, open(Path(directory)/"stderr.log","wb") as stderr:
        process = subprocess.Popen(args,cwd=directory,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,
                                   creationflags=0x08000000 if os.name=="nt" else 0)
        job = _WindowsJob(process)
        reason = None
        try:
            while process.poll() is None:
                if time.perf_counter()-start > seconds:
                    reason = "执行超过时间限制"
                    _terminate(process)
                    break
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > output_limit:
                    reason = "输出超过 256 KiB 限制"
                    _terminate(process)
                    break
                time.sleep(0.02)
            process.wait(timeout=3)
        finally:
            job.close()
            if process.poll() is None:
                _terminate(process)
    out = (Path(directory)/"stdout.log").read_bytes()[:output_limit].decode("utf-8","replace")
    err = (Path(directory)/"stderr.log").read_bytes()[:output_limit].decode("utf-8","replace")
    return {"ok": process.returncode==0 and reason is None,"returncode":process.returncode,"stdout":out,"stderr":err,
            "error":reason,"elapsed_ms":round((time.perf_counter()-start)*1000,3),"kind":"measured","sandboxed":False}


def _python_interpreter(interpreter=None):
    if interpreter:
        if not Path(interpreter).is_file():
            raise ValueError("指定的 Python 可执行程序不存在")
        return [str(interpreter)]
    return [sys.executable]


def run_python(code, timeout=5, interpreter=None, workdir=None):
    if not 0.1 <= float(timeout) <= 30:
        raise ValueError("运行时间限制应为 0.1–30 秒")
    if len(code.encode("utf-8")) > 1024*1024:
        raise ValueError("代码限 1 MiB")
    try:
        if workdir is not None:
            workdir=Path(workdir)
            workdir.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="netlab-code-",dir=workdir) as directory:
            source = Path(directory)/"exercise.py"
            source.write_text(code,encoding="utf-8")
            if getattr(sys,"frozen",False) and interpreter is None:
                args=[sys.executable,"--run-exercise",str(source),str(Path(directory)/"stdout.log"),str(Path(directory)/"stderr.log")]
            else:
                args=_python_interpreter(interpreter)+["-I","-X","utf8","-u",str(source)]
            return _run(args,directory,float(timeout))
    except Exception as exc:
        return {"ok":False,"returncode":None,"stdout":"","stderr":"","error":f"{type(exc).__name__}: {exc}","kind":"measured","sandboxed":False}


def run_c(code, timeout=5, compiler=None):
    if not 0.1 <= float(timeout) <= 30:
        raise ValueError("运行时间限制应为 0.1–30 秒")
    if len(code.encode("utf-8")) > 1024*1024:
        raise ValueError("代码限 1 MiB")
    compiler = compiler or discover_c_compiler()
    if not compiler:
        return {"ok":False,"returncode":None,"stdout":"","stderr":"","error":"C 编译器不可用，请安装 GCC/Clang 并配置 PATH；Python 实验仍可运行。","kind":"measured","sandboxed":False}
    try:
        with tempfile.TemporaryDirectory(prefix="netlab-c-") as directory:
            source = Path(directory)/"exercise.c"
            binary = Path(directory)/("exercise.exe" if os.name=="nt" else "exercise")
            source.write_text(code,encoding="utf-8")
            args = [str(compiler),str(source),"-Wall","-Wextra","-O0","-o",str(binary)]
            if os.name=="nt":
                args.append("-lws2_32")
            compiled = _run(args,directory,15)
            if not compiled["ok"]:
                return {**compiled,"stage":"compile"}
            executed = _run([str(binary)],directory,float(timeout))
            return {**executed,"stage":"run","compiler_output":compiled["stderr"]}
    except Exception as exc:
        return {"ok":False,"returncode":None,"stdout":"","stderr":"","error":f"{type(exc).__name__}: {exc}","kind":"measured","sandboxed":False}


def discover_c_compiler():
    found = shutil.which("gcc") or shutil.which("clang")
    if found:
        return found
    if os.name=="nt":
        for candidate in (r"C:\Tools\w64devkit\bin\gcc.exe",r"C:\msys64\ucrt64\bin\gcc.exe",r"C:\msys64\mingw64\bin\gcc.exe",r"C:\mingw64\bin\gcc.exe",r"D:\mingw64\bin\gcc.exe",r"C:\Program Files\LLVM\bin\clang.exe"):
            if Path(candidate).is_file():
                return candidate
    return None


TCP_CODE = '''import socket, threading
def serve(listener):
    conn, _ = listener.accept()
    with conn:
        conn.sendall(conn.recv(4096))
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=serve, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.sendall("你好 TCP".encode()); print(client.recv(4096).decode())
    thread.join(2)
'''
UDP_CODE = '''import socket
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server, socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    server.bind(("127.0.0.1", 0)); server.settimeout(2); client.settimeout(2)
    client.sendto(b"hello UDP", server.getsockname())
    data, peer = server.recvfrom(4096); server.sendto(data, peer)
    print(client.recvfrom(4096)[0].decode())
'''
ASYNC_CODE = '''import asyncio
async def echo(reader, writer):
    data = await reader.read(4096); writer.write(data); await writer.drain()
    writer.close(); await writer.wait_closed()
async def main():
    server = await asyncio.start_server(echo, "127.0.0.1", 0)
    async with server:
        reader, writer = await asyncio.open_connection("127.0.0.1", server.sockets[0].getsockname()[1])
        writer.write(b"asyncio echo"); await writer.drain()
        print((await asyncio.wait_for(reader.read(4096), 2)).decode())
        writer.close(); await writer.wait_closed()
asyncio.run(main())
'''
SELECT_CODE = '''import socket, selectors
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        conn, _ = listener.accept()
        with conn, selectors.DefaultSelector() as selector:
            conn.setblocking(False); selector.register(conn, selectors.EVENT_READ)
            client.sendall(b"select event")
            for key, event in selector.select(timeout=2):
                data = key.fileobj.recv(4096); key.fileobj.sendall(data)
            print(client.recv(4096).decode())
'''
FILE_CODE = '''import socket, threading, hashlib, struct
def exact(conn, n):
    data = bytearray()
    while len(data) < n:
        part = conn.recv(n-len(data))
        if not part: raise EOFError("truncated")
        data.extend(part)
    return bytes(data)
def receive(listener):
    conn, _ = listener.accept()
    with conn:
        n = struct.unpack("!I", exact(conn, 4))[0]
        if n > 1048576: return
        data = exact(conn, n); conn.sendall(hashlib.sha256(data).hexdigest().encode())
payload = b"NetLab file transfer" * 4096
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=receive, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.sendall(struct.pack("!I", len(payload)) + payload)
        actual = exact(client, 64).decode(); print("SHA256:", actual)
        print("verified:", actual == hashlib.sha256(payload).hexdigest())
    thread.join(2)
'''
HTTP_CODE = '''import http.server, threading, urllib.request
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"local HTTP response"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def log_message(self, *args): pass
server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
try:
    with urllib.request.urlopen("http://127.0.0.1:%d/" % server.server_port, timeout=2) as response:
        print("status:", response.status); print(response.read().decode())
finally:
    server.shutdown(); server.server_close(); thread.join(2)
'''
MULTI_CODE = '''import socket, threading
def handle(conn):
    with conn: conn.sendall(conn.recv(4096))
def serve(listener):
    workers = []
    for _ in range(3):
        conn, _ = listener.accept(); t = threading.Thread(target=handle, args=(conn,)); t.start(); workers.append(t)
    for t in workers: t.join(2)
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    worker = threading.Thread(target=serve, args=(listener,)); worker.start()
    for i in range(3):
        with socket.create_connection(listener.getsockname(), timeout=2) as client:
            client.sendall(("client %d" % i).encode()); print(client.recv(4096).decode())
    worker.join(2)
'''
BUFFER_CODE = '''import socket, threading, time
payload = b"x" * 262144
def serve(listener):
    conn, _ = listener.accept(); total = 0
    with conn:
        while True:
            data = conn.recv(4096)
            if not data: break
            total += len(data)
        conn.sendall(str(total).encode())
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=serve, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        start = time.perf_counter(); client.sendall(payload); client.shutdown(socket.SHUT_WR)
        total = int(client.recv(100)); elapsed = time.perf_counter()-start
        print("received bytes:", total); print("loopback MiB/s:", round(total/1048576/elapsed, 2))
    thread.join(2)
'''
TIMEOUT_CODE = '''import socket
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    with socket.create_connection(listener.getsockname(), timeout=2) as client:
        conn, _ = listener.accept()
        with conn:
            client.settimeout(0.1)
            try: client.recv(4096)
            except socket.timeout: print("timeout handled: server sent no data")
'''
CHAT_CODE = '''import socket, threading
def chat(listener):
    peers = [listener.accept()[0] for _ in range(2)]
    try:
        message = peers[0].recv(4096)
        for peer in peers: peer.sendall(message)
    finally:
        for peer in peers: peer.close()
with socket.socket() as listener:
    listener.bind(("127.0.0.1", 0)); listener.listen()
    thread = threading.Thread(target=chat, args=(listener,)); thread.start()
    with socket.create_connection(listener.getsockname(), timeout=2) as alice, socket.create_connection(listener.getsockname(), timeout=2) as bob:
        alice.sendall(b"Alice: hello Bob")
        print("Alice received:", alice.recv(4096).decode()); print("Bob received:", bob.recv(4096).decode())
    thread.join(2)
'''
WEBSOCKET_CODE = '''import asyncio
from websockets.asyncio.server import serve
from websockets.asyncio.client import connect
async def echo(websocket):
    async for message in websocket: await websocket.send(message)
async def main():
    async with serve(echo, "127.0.0.1", 0) as server:
        async with connect("ws://127.0.0.1:%d/" % server.sockets[0].getsockname()[1], proxy=None) as client:
            await client.send("WebSocket frame"); print(await client.recv())
asyncio.run(main())
'''
C_TCP_CODE = '''#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#define closesocket close
#define SOCKET int
#define INVALID_SOCKET -1
#endif
int main(void) {
#ifdef _WIN32
    WSADATA w; if (WSAStartup(MAKEWORD(2,2), &w)) return 1;
#endif
    SOCKET listener=socket(AF_INET, SOCK_STREAM, 0), client=socket(AF_INET, SOCK_STREAM, 0);
    struct sockaddr_in addr; memset(&addr,0,sizeof addr); addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if (bind(listener,(struct sockaddr*)&addr,sizeof addr) || listen(listener,2)) return 2;
#ifdef _WIN32
    int len=sizeof addr;
#else
    socklen_t len=sizeof addr;
#endif
    getsockname(listener,(struct sockaddr*)&addr,&len);
    if (connect(client,(struct sockaddr*)&addr,sizeof addr)) return 3;
    SOCKET peer=accept(listener,NULL,NULL); char data[128]={0};
    if (peer==INVALID_SOCKET) return 4;
    const char *message="C Winsock TCP echo"; send(client,message,(int)strlen(message),0);
    int n=recv(peer,data,sizeof(data)-1,0); if(n<=0) return 5; send(peer,data,n,0);
    memset(data,0,sizeof data); n=recv(client,data,sizeof(data)-1,0); if(n<=0) return 6;
    printf("%s\\n",data); closesocket(peer); closesocket(client); closesocket(listener);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
'''
C_UDP_CODE = '''#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <winsock2.h>
#else
#include <unistd.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#define closesocket close
#define SOCKET int
#endif
int main(void) {
#ifdef _WIN32
    WSADATA w; if (WSAStartup(MAKEWORD(2,2),&w)) return 1;
#endif
    SOCKET server=socket(AF_INET,SOCK_DGRAM,0), client=socket(AF_INET,SOCK_DGRAM,0);
    struct sockaddr_in addr,peer; memset(&addr,0,sizeof addr); addr.sin_family=AF_INET; addr.sin_addr.s_addr=htonl(INADDR_LOOPBACK);
    if(bind(server,(struct sockaddr*)&addr,sizeof addr)) return 2;
#ifdef _WIN32
    int len=sizeof addr,peerlen=sizeof peer;
#else
    socklen_t len=sizeof addr,peerlen=sizeof peer;
#endif
    getsockname(server,(struct sockaddr*)&addr,&len); char data[128]={0};
    const char *message="C UDP datagram"; sendto(client,message,(int)strlen(message),0,(struct sockaddr*)&addr,sizeof addr);
    int n=recvfrom(server,data,sizeof(data)-1,0,(struct sockaddr*)&peer,&peerlen); if(n<=0) return 3;
    sendto(server,data,n,0,(struct sockaddr*)&peer,peerlen); memset(data,0,sizeof data);
    n=recvfrom(client,data,sizeof(data)-1,0,NULL,NULL); if(n<=0) return 4;
    printf("%s\\n",data); closesocket(client); closesocket(server);
#ifdef _WIN32
    WSACleanup();
#endif
    return 0;
}
'''


def templates():
    rows = [
        ("tcp_echo","TCP 客户端与服务器","python",TCP_CODE,"本机回环 TCP 连接、accept、sendall、recv。"),
        ("udp_echo","UDP 客户端与服务器","python",UDP_CODE,"UDP 保留数据报边界；这里不人为制造丢包。"),
        ("asyncio","异步 I/O","python",ASYNC_CODE,"使用协程读取和写入，drain 处理写缓冲区背压。"),
        ("select","非阻塞 Socket 与 select","python",SELECT_CODE,"selector 等待就绪事件，避免空循环忙等。"),
        ("file_transfer","长度前缀与文件传输","python",FILE_CODE,"TCP 是字节流；循环接收完整长度，使用 SHA-256 校验。"),
        ("http","简易 HTTP 服务器","python",HTTP_CODE,"真正发送本机 HTTP 请求并查看状态与响应。"),
        ("multithread","多客户端线程服务器","python",MULTI_CODE,"独立工作线程处理不同连接，最终 join 与关闭 Socket。"),
        ("buffers","缓冲区与本机性能测试","python",BUFFER_CODE,"吞吐量是实测回环传输结果，不能代表互联网带宽。"),
        ("timeout","超时和异常处理","python",TIMEOUT_CODE,"连接成功但服务器未发送数据时，读取仍会超时。"),
        ("chat","双客户端聊天室","python",CHAT_CODE,"两个本机客户端连接同一服务器，向双方广播一条消息。"),
        ("websocket","WebSocket","python",WEBSOCKET_CODE,"使用成熟 websockets 库进行真实握手及消息回显。"),
        ("c_tcp","C / Winsock TCP","c",C_TCP_CODE,"Windows 编译时链接 ws2_32；一个进程内测试监听端与客户端。"),
        ("c_udp","C / Winsock UDP","c",C_UDP_CODE,"真实 UDP 数据报回显；客户端和服务器均绑定本机。"),
    ]
    return [{"id":id,"name":name,"language":language,"code":code,"explanation":explanation,"scope":"loopback","kind":"example"} for id,name,language,code,explanation in rows]


def write_examples(directory):
    path = Path(directory)
    path.mkdir(parents=True,exist_ok=True)
    for exercise in templates():
        suffix = ".py" if exercise["language"]=="python" else ".c"
        (path/(exercise["id"]+suffix)).write_text(exercise["code"],encoding="utf-8")
