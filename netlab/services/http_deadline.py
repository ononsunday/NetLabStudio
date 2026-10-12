"""HTTPX / HTTPcore transport with one deadline across DNS, TLS and reads.

HTTP/1.1 and HTTP/2 framing remain implemented by HTTPcore. This adapter only
supplies bounded synchronous I/O, and preserves normal certificate verification.
"""
from __future__ import annotations

import select
import socket
import time

import httpcore
import httpx

from .common import connect_socket


class Deadline:
    def __init__(self,seconds,cancel_event=None):
        self.expires=time.monotonic()+seconds
        self.cancel_event=cancel_event
    def remaining(self,maximum=None):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise TimeoutError("用户取消了 HTTP 请求")
        remaining=self.expires-time.monotonic()
        if remaining<=0:
            raise TimeoutError("HTTP 请求达到总时间限制")
        return min(remaining,maximum) if maximum is not None else remaining


class Stream:
    def __init__(self,connection,deadline):
        self.connection,self.deadline=connection,deadline
    def read(self,max_bytes,timeout=None):
        self.connection.settimeout(self.deadline.remaining(timeout))
        try:
            return self.connection.recv(max_bytes)
        except socket.timeout as exc:
            raise httpcore.ReadTimeout("HTTP 读取达到总时间限制") from exc
    def write(self,buffer,timeout=None):
        self.connection.settimeout(self.deadline.remaining(timeout))
        try:
            self.connection.sendall(buffer)
        except socket.timeout as exc:
            raise httpcore.WriteTimeout("HTTP 写入达到总时间限制") from exc
    def start_tls(self,ssl_context,server_hostname=None,timeout=None):
        self.connection.settimeout(self.deadline.remaining(timeout))
        try:
            secured=ssl_context.wrap_socket(self.connection,server_hostname=server_hostname)
        except Exception:
            self.connection.close()
            raise
        return Stream(secured,self.deadline)
    def get_extra_info(self,info):
        if info=="ssl_object":return self.connection if isinstance(self.connection,__import__('ssl').SSLSocket) else None
        if info=="socket":return self.connection
        if info=="client_addr":return self.connection.getsockname()
        if info=="server_addr":return self.connection.getpeername()
        if info=="is_readable":return bool(select.select([self.connection],[],[],0)[0])
        return None
    def close(self):
        self.connection.close()


class Backend:
    def __init__(self,deadline):self.deadline=deadline
    def connect_tcp(self,host,port,timeout=None,local_address=None,socket_options=None):
        remaining=self.deadline.remaining(timeout)
        if remaining<0.05:
            raise TimeoutError("HTTP 连接达到总时间限制")
        if local_address is not None:
            raise ValueError("此诊断客户端不修改源接口绑定")
        connection=connect_socket(host,port,remaining)
        try:
            for option in socket_options or []:connection.setsockopt(*option)
            return Stream(connection,self.deadline)
        except Exception:
            connection.close()
            raise
    def connect_unix_socket(self,*args,**kwargs):
        raise ValueError("此实验只接受 TCP 的 HTTP/HTTPS URL")
    def sleep(self,seconds):time.sleep(self.deadline.remaining(seconds))


class ResponseStream(httpx.SyncByteStream):
    def __init__(self,stream):self.stream=stream
    def __iter__(self):yield from self.stream
    def close(self):self.stream.close()


class DeadlineTransport(httpx.BaseTransport):
    def __init__(self,ssl_context,seconds,cancel_event=None):
        self.deadline=Deadline(seconds,cancel_event)
        self.pool=httpcore.ConnectionPool(ssl_context=ssl_context,http1=True,http2=True,retries=0,max_connections=1,
                                         network_backend=Backend(self.deadline))
    def handle_request(self,request):
        url=httpcore.URL(scheme=request.url.raw_scheme,host=request.url.raw_host,port=request.url.port,target=request.url.raw_path)
        incoming=httpcore.Request(method=request.method,url=url,headers=request.headers.raw,content=request.stream,extensions=request.extensions)
        response=self.pool.handle_request(incoming)
        return httpx.Response(response.status,headers=response.headers,stream=ResponseStream(response.stream),extensions=response.extensions)
    def close(self):self.pool.close()
