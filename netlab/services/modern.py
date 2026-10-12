"""Mature-library HTTP/3, WebSocket and SSH experiments; no custom crypto."""
from __future__ import annotations

import asyncio
import json
import threading

from .common import host, port, result, timeout, url


def _h3_protocols():
    from aioquic.asyncio.protocol import QuicConnectionProtocol
    from aioquic.h3.connection import H3Connection
    from aioquic.h3.events import HeadersReceived, DataReceived
    from aioquic.quic.events import ConnectionTerminated, ProtocolNegotiated

    class Client(QuicConnectionProtocol):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.http = H3Connection(self._quic)
            self.headers, self.body, self.waiter = [], bytearray(), None
            self.negotiated_alpn = None

        def quic_event_received(self, event):
            if isinstance(event, ProtocolNegotiated):
                self.negotiated_alpn = event.alpn_protocol
            if isinstance(event, ConnectionTerminated) and self.waiter and not self.waiter.done():
                self.waiter.set_exception(ConnectionError(f"QUIC {event.error_code}: {event.reason_phrase}"))
            for http_event in self.http.handle_event(event):
                if isinstance(http_event, HeadersReceived):
                    self.headers.extend([(a.decode("ascii", "replace"), b.decode("utf-8", "replace")) for a,b in http_event.headers])
                elif isinstance(http_event, DataReceived):
                    self.body.extend(http_event.data)
                    if len(self.body) > 1024*1024:
                        if self.waiter and not self.waiter.done():
                            self.waiter.set_exception(ValueError("HTTP/3 响应超过 1 MiB"))
                        self.close()
                if isinstance(http_event, (HeadersReceived, DataReceived)) and http_event.stream_ended and self.waiter and not self.waiter.done():
                    self.waiter.set_result({"http_version": "HTTP/3", "headers": dict(self.headers), "body_preview": bytes(self.body[:65536]).decode("utf-8", "replace"),
                                            "body_bytes_read": len(self.body), "alpn": self.negotiated_alpn, "certificate_verified": True})

        async def get(self, parsed):
            self.waiter = asyncio.get_running_loop().create_future()
            stream_id = self._quic.get_next_available_stream_id()
            path = (parsed.path or "/")+("?"+parsed.query if parsed.query else "")
            self.http.send_headers(stream_id, [(b":method", b"GET"), (b":scheme", b"https"), (b":authority", parsed.netloc.encode("ascii")), (b":path", path.encode("utf-8")), (b"user-agent", b"NetLab-Studio")], end_stream=True)
            self.transmit()
            return await self.waiter

    class Server(QuicConnectionProtocol):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.http = H3Connection(self._quic)
            self.replied = set()

        def quic_event_received(self, event):
            for http_event in self.http.handle_event(event):
                if isinstance(http_event, HeadersReceived) and http_event.stream_id not in self.replied:
                    self.replied.add(http_event.stream_id)
                    headers = dict(http_event.headers)
                    body = json.dumps({"service": "NetLab HTTP/3", "kind": "measured", "method": headers.get(b":method", b"").decode(), "path": headers.get(b":path", b"").decode()}, ensure_ascii=False).encode()
                    self.http.send_headers(http_event.stream_id, [(b":status", b"200"), (b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(body)).encode())])
                    self.http.send_data(http_event.stream_id, body, end_stream=True)
                    self.transmit()
    return Client, Server


def http3_probe(target, seconds=5, cafile=None):
    parsed, seconds = url(target, ("https",)), timeout(seconds)
    def perform():
        from aioquic.asyncio.client import connect
        from aioquic.h3.connection import H3_ALPN
        from aioquic.quic.configuration import QuicConfiguration
        Client, _ = _h3_protocols()
        config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN, idle_timeout=seconds)
        if cafile:
            config.load_verify_locations(cafile=cafile)
        async def fetch():
            async with connect(parsed.hostname, parsed.port or 443, configuration=config, create_protocol=Client) as client:
                return await client.get(parsed)
        return asyncio.run(asyncio.wait_for(fetch(), seconds))
    return result("HTTP/3 / QUIC", target, perform)


def websocket_probe(target, message="你好 WebSocket", seconds=5):
    url(target, ("ws", "wss"))
    seconds = timeout(seconds)
    def perform():
        from websockets.sync.client import connect
        with connect(target, open_timeout=seconds, close_timeout=seconds, proxy=None, max_size=1024*1024) as connection:
            connection.send(message)
            answer = connection.recv(timeout=seconds)
        return {"sent": message, "received": answer if isinstance(answer, str) else answer.hex(), "matches": answer == message}
    return result("WebSocket", target, perform)


def ssh_probe(target, target_port=22, seconds=5):
    """Key exchange only. A discovered fingerprint is not authenticated identity."""
    target, target_port, seconds = host(target), port(target_port), timeout(seconds)
    def perform():
        import asyncssh
        async def fetch():
            key = await asyncssh.get_server_host_key(target, target_port, config=None)
            if key is None:
                raise ValueError("服务器未返回主机公钥")
            return {"algorithm": key.get_algorithm(), "fingerprint": key.get_fingerprint(), "public_key": key.export_public_key().decode(),
                    "identity_verified": False, "note": "只执行 SSH 密钥交换并读取公钥；需与可信来源核对指纹才能确认身份，没有登录或执行远程命令。"}
        return asyncio.run(asyncio.wait_for(fetch(), seconds))
    return result("SSH 主机公钥", f"{target}:{target_port}", perform)


def ssh_local_client(target, target_port, trusted_public_key, seconds=5):
    """Only the loopback teaching command, with explicitly pinned host key."""
    import ipaddress
    target, target_port, seconds = host(target), port(target_port), timeout(seconds)
    if not ipaddress.ip_address(target).is_loopback:
        raise ValueError("此实验仅允许本机回环 SSH 服务器")
    def perform():
        import asyncssh
        key = asyncssh.import_public_key(trusted_public_key)
        async def execute():
            async with asyncssh.connect(target, target_port, username="student", known_hosts=([key], [], []), config=None, client_keys=[]) as connection:
                response = await connection.run("netlab-info", check=True)
                return {"stdout": response.stdout, "returncode": response.exit_status, "host_key_verified": True}
        return asyncio.run(asyncio.wait_for(execute(), seconds))
    return result("本机 SSH 实验", f"{target}:{target_port}", perform)


class AsyncLabServer:
    """Own asyncio loop in one daemon thread; lifecycle managed by desktop."""
    def __init__(self, kind, host, port, certificate=None, event_callback=None):
        self.kind, self.host, self.port, self.certificate = kind, host, port, certificate
        self.callback = event_callback or (lambda *args: None)
        self.loop = None
        self.server = None
        self.public_key = None
        self.error = None
        self._ready = threading.Event()
        self._connections = set()
        self.thread = threading.Thread(target=self._run, name="netlab-"+kind, daemon=True)

    async def _start(self):
        if self.kind == "websocket":
            from websockets.asyncio.server import serve
            async def echo(connection):
                async for message in connection:
                    await connection.send(message)
                    self.callback("WebSocket echo", len(message), connection.remote_address)
            self.server = await serve(echo, self.host, self.port, max_size=1024*1024, close_timeout=1)
            self.port = self.server.sockets[0].getsockname()[1]
        elif self.kind == "http3":
            from aioquic.asyncio import serve
            from aioquic.h3.connection import H3_ALPN
            from aioquic.quic.configuration import QuicConfiguration
            _, Server = _h3_protocols()
            config = QuicConfiguration(is_client=False, alpn_protocols=H3_ALPN, idle_timeout=5)
            config.load_cert_chain(self.certificate["certificate"], self.certificate["keyfile"])
            self.server = await serve(self.host, self.port, configuration=config, create_protocol=Server)
            # aioquic's datagram server exposes no public port accessor (1.3.0).
            self.port = self.server._transport.get_extra_info("sockname")[1]
        elif self.kind == "ssh":
            import asyncssh
            owner = self
            class LabSSH(asyncssh.SSHServer):
                def connection_made(self, connection):
                    self.connection = connection
                    owner._connections.add(connection)
                def connection_lost(self, exc):
                    owner._connections.discard(self.connection)
                def begin_auth(self, username):
                    return False  # Ephemeral loopback only, no operating-system account.
            def process(process):
                if process.command == "netlab-info":
                    process.stdout.write("NetLab 本机 SSH 加密连接实验\n")
                    process.exit(0)
                else:
                    process.stderr.write("此教学服务器只接受 netlab-info，不执行系统命令。\n")
                    process.exit(127)
            key = asyncssh.generate_private_key("ssh-ed25519")
            self.public_key = key.export_public_key().decode()
            self.server = await asyncssh.create_server(LabSSH, self.host, self.port, server_host_keys=[key], process_factory=process)
            self.port = self.server.get_port()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._start())
        except BaseException as exc:
            self.error = exc
        self._ready.set()
        if not self.error:
            self.loop.run_forever()
        pending = asyncio.all_tasks(self.loop)
        for task in pending:
            task.cancel()
        if pending:
            self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        self.loop.close()

    def start(self):
        self.thread.start()
        if not self._ready.wait(10):
            raise TimeoutError("启动本机异步服务器超时")
        if self.error:
            raise self.error
        return self.port

    def close(self):
        if not self.loop or self.loop.is_closed():
            return
        async def cleanup():
            for conn in list(self._connections):
                conn.close()
            self.server.close()
            if hasattr(self.server, "wait_closed"):
                await self.server.wait_closed()
            for conn in list(self._connections):
                await conn.wait_closed()
        future = asyncio.run_coroutine_threadsafe(cleanup(), self.loop)
        try:
            future.result(5)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
