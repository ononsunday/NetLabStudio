"""Real loopback test servers, with explicit lifecycle and bounded messages."""
from __future__ import annotations

import contextlib
import datetime
import hashlib
import http.server
import ipaddress
import json
import os
from pathlib import Path
import socket
import socketserver
import ssl
import struct
import tempfile
import threading
import time
import uuid

from .common import connect_socket,host as validate_host, port as validate_port, timeout as validate_timeout, result

MAX_MESSAGE = 1024*1024


def make_certificate(directory: str) -> dict:
    """Ephemeral self-signed teaching certificate; never change Windows trust."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "NetLab localhost teaching certificate")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-datetime.timedelta(minutes=5))
            .not_valid_after(now+datetime.timedelta(days=7))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1")), x509.IPAddress(ipaddress.ip_address("::1"))]), critical=False)
            .sign(key, hashes.SHA256()))
    key_path, cert_path = path/"localhost-key.pem", path/"localhost-cert.pem"
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return {"keyfile": str(key_path), "cafile": str(cert_path), "certificate": str(cert_path), "fingerprint_sha256": cert.fingerprint(hashes.SHA256()).hex(),
            "note": "仅供本机教学使用的自签名证书；请显式把该 PEM 传给测试客户端，未安装到系统信任库。"}


def _read_exact(conn, length):
    if not 0 <= length <= MAX_MESSAGE:
        raise ValueError("消息长度超过 1 MiB")
    chunks = bytearray()
    while len(chunks) < length:
        fragment = conn.recv(min(65536, length-len(chunks)))
        if not fragment:
            raise EOFError("连接在消息接收完成前关闭")
        chunks.extend(fragment)
    return bytes(chunks)


def _send_frame(conn, data):
    conn.sendall(struct.pack("!I", len(data))+data)


def _read_frame(conn):
    return _read_exact(conn, struct.unpack("!I", _read_exact(conn, 4))[0])


class _ThreadedTCP(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


class _ThreadedUDP(socketserver.ThreadingUDPServer):
    allow_reuse_address = True
    daemon_threads = True
    block_on_close = False


class _TLSAccept:
    def get_request(self):
        connection,address = super().get_request()
        connection.settimeout(3)
        # Handshake in a handler thread, never the server's accept loop.
        connection = self.tls_context.wrap_socket(connection,server_side=True,do_handshake_on_connect=False)
        return connection,address


class _EchoTCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(2)
        self.server.manager._track(self.request, True)
        try:
            while not self.server.manager._closing:
                data = self.request.recv(65536)
                if not data:
                    break
                self.server.manager._record(self.server.lab_id, "TCP echo", len(data), self.client_address)
                self.request.sendall(data)
        except (OSError, TimeoutError):
            pass
        finally:
            self.server.manager._track(self.request, False)


class _EchoUDP(socketserver.BaseRequestHandler):
    def handle(self):
        data, sock = self.request
        self.server.manager._record(self.server.lab_id, "UDP echo", len(data), self.client_address)
        sock.sendto(data, self.client_address)


def _dns_answer(data):
    """Local lab.local teaching zone, never forwards to public DNS."""
    import dns.message
    import dns.rdatatype
    import dns.rcode
    import dns.rrset
    request = dns.message.from_wire(data)
    response = dns.message.make_response(request)
    zone = {"A":"127.0.0.1","AAAA":"::1","TXT":'"NetLab local example"',"MX":"10 mail.lab.local.","NS":"ns.lab.local.","SOA":"ns.lab.local. student.lab.local. 1 3600 600 86400 60","CNAME":"lab.local.","SRV":"0 5 25565 lab.local."}
    for question in request.question:
        name, record_type = str(question.name).lower(), dns.rdatatype.to_text(question.rdtype)
        if name not in {"lab.local.","alias.lab.local.","mail.lab.local.","ns.lab.local.","_minecraft._tcp.lab.local."}:
            response.set_rcode(dns.rcode.NXDOMAIN)
        elif record_type in zone:
            response.answer.append(dns.rrset.from_text(name,60,"IN",record_type,zone[record_type]))
    return response.to_wire()


class _DNSUDP(socketserver.BaseRequestHandler):
    def handle(self):
        data, connection = self.request
        with contextlib.suppress(Exception):
            response = _dns_answer(data)
            connection.sendto(response,self.client_address)
            self.server.manager._record(self.server.lab_id,"本机 DNS",len(response),self.client_address)


class _DNSTCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        self.server.manager._track(self.request,True)
        try:
            size = struct.unpack("!H",_read_exact(self.request,2))[0]
            data = _read_exact(self.request,size)
            response = _dns_answer(data)
            self.request.sendall(struct.pack("!H",len(response))+response)
            self.server.manager._record(self.server.lab_id,"本机 DoT",len(response),self.client_address)
        except Exception:
            pass
        finally:
            self.server.manager._track(self.request,False)


class _HTTP2(socketserver.BaseRequestHandler):
    def handle(self):
        from h2.connection import H2Connection
        from h2.config import H2Configuration
        from h2.events import RequestReceived,DataReceived,StreamEnded
        self.request.settimeout(3)
        self.server.manager._track(self.request,True)
        connection=H2Connection(config=H2Configuration(client_side=False,header_encoding="utf-8"))
        streams={}
        try:
            connection.initiate_connection()
            self.request.sendall(connection.data_to_send())
            while not self.server.manager._closing:
                incoming=self.request.recv(65536)
                if not incoming:break
                for event in connection.receive_data(incoming):
                    if isinstance(event,RequestReceived):
                        streams[event.stream_id]={"headers":dict(event.headers),"body":bytearray()}
                    elif isinstance(event,DataReceived):
                        stream=streams[event.stream_id]
                        stream["body"].extend(event.data[:max(0,32769-len(stream["body"]))])
                        connection.acknowledge_received_data(event.flow_controlled_length,event.stream_id)
                    elif isinstance(event,StreamEnded):
                        stream=streams.pop(event.stream_id)
                        oversized=len(stream["body"])>32768
                        body=json.dumps({"service":"NetLab HTTP/2","kind":"measured","method":stream["headers"].get(":method"),
                                         "path":stream["headers"].get(":path"),"body":stream["body"].decode("utf-8","replace") if not oversized else None,
                                         "error":"本机 HTTP/2 教学请求体限 32 KiB" if oversized else None},ensure_ascii=False).encode()
                        connection.send_headers(event.stream_id,[(":status","413" if oversized else "200"),("content-type","application/json; charset=utf-8"),("content-length",str(len(body)))])
                        for offset in range(0,len(body),connection.max_outbound_frame_size):
                            fragment=body[offset:offset+connection.max_outbound_frame_size]
                            connection.send_data(event.stream_id,fragment,end_stream=offset+len(fragment)==len(body))
                        self.request.sendall(connection.data_to_send())
                        self.server.manager._record(self.server.lab_id,"本机 HTTP/2",len(body),self.client_address)
                        # Continue reading until the client closes. An immediate
                        # close with unread H2 control frames can cause a TCP RST
                        # on Windows before the peer consumes the response.
                outgoing=connection.data_to_send()
                if outgoing:self.request.sendall(outgoing)
        except (OSError,ValueError):
            pass
        finally:
            self.server.manager._track(self.request,False)


class _STUN(socketserver.BaseRequestHandler):
    def handle(self):
        from .p2p import COOKIE
        data, connection = self.request
        if len(data)<20 or data[:2]!=b"\x00\x01" or data[4:8]!=struct.pack("!I",COOKIE):
            return
        transaction = data[8:20]
        ipv6 = ":" in self.client_address[0]
        encoded = socket.inet_pton(socket.AF_INET6 if ipv6 else socket.AF_INET,self.client_address[0])
        mask = struct.pack("!I",COOKIE)+transaction
        encoded = bytes(a^b for a,b in zip(encoded,mask))
        value = struct.pack("!BBH",0,2 if ipv6 else 1,self.client_address[1]^(COOKIE>>16))+encoded
        attribute = struct.pack("!HH",0x0020,len(value))+value
        connection.sendto(struct.pack("!HHI",0x0101,len(attribute),COOKIE)+transaction+attribute,self.client_address)
        self.server.manager._record(self.server.lab_id,"本机 STUN",len(attribute)+20,self.client_address)


class _FileTCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        self.server.manager._track(self.request, True)
        try:
            data = _read_frame(self.request)
            digest = hashlib.sha256(data).hexdigest()
            path = Path(self.server.directory)/(digest+".bin")
            path.write_bytes(data)
            _send_frame(self.request, json.dumps({"bytes": len(data), "sha256": digest}).encode())
            self.server.manager._record(self.server.lab_id, "文件接收", len(data), self.client_address)
        except (OSError, ValueError, EOFError):
            pass
        finally:
            self.server.manager._track(self.request, False)


class _ChatTCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(0.5)
        self.server.manager._track(self.request, True)
        with self.server.clients_lock:
            self.server.clients.add(self.request)
        buffer = bytearray()
        try:
            while not self.server.manager._closing:
                try:
                    chunk = self.request.recv(4096)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer.extend(chunk)
                if len(buffer) > 65536:
                    break
                while b"\n" in buffer:
                    line, _, remainder = buffer.partition(b"\n")
                    buffer = bytearray(remainder)
                    with self.server.clients_lock:
                        peers = list(self.server.clients)
                    for conn in peers:
                        with contextlib.suppress(OSError):
                            conn.sendall(line+b"\n")
                    self.server.manager._record(self.server.lab_id, "聊天广播", len(line), self.client_address)
        except OSError:
            pass
        finally:
            with self.server.clients_lock:
                self.server.clients.discard(self.request)
            self.server.manager._track(self.request, False)


class _HTTP(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def handle(self):
        # TLS certificate probes close after the handshake without sending an
        # HTTP request. A peer reset is a normal connection lifecycle outcome.
        try:
            super().handle()
        except OSError:
            self.close_connection = True
    def _response(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_MESSAGE:
                self.send_error(413)
                return
            body = self.rfile.read(length).decode("utf-8", "replace") if length else ""
            content = json.dumps({"service": "NetLab Studio 本机测试服务器", "method": self.command, "path": self.path,
                                  "body": body, "headers": dict(self.headers), "kind": "measured"}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)
            self.server.manager._record(self.server.lab_id, self.command, length, self.client_address)
            self.close_connection = True
        except (OSError, ValueError):
            self.close_connection = True
    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _response
    def setup(self):
        super().setup()
        self.connection.settimeout(5)
        self.server.manager._track(self.connection, True)
    def finish(self):
        try:
            super().finish()
        finally:
            self.server.manager._track(self.connection, False)
    def log_message(self, *args):
        pass


class _DoH(_HTTP):
    def _response(self):
        try:
            if self.command=="GET":
                import base64
                from urllib.parse import urlsplit,parse_qs
                encoded = parse_qs(urlsplit(self.path).query).get("dns",[""])[0]
                data = base64.urlsafe_b64decode(encoded+"="*((-len(encoded))%4))
            elif self.command=="POST":
                size = int(self.headers.get("Content-Length","0"))
                if not 0<size<=65535:
                    self.send_error(413)
                    return
                data = self.rfile.read(size)
            else:
                self.send_error(405)
                return
            response = _dns_answer(data)
            self.send_response(200)
            self.send_header("Content-Type","application/dns-message")
            self.send_header("Content-Length",str(len(response)))
            self.send_header("Connection","close")
            self.end_headers()
            self.wfile.write(response)
            self.server.manager._record(self.server.lab_id,"本机 DoH",len(response),self.client_address)
        except Exception:
            self.close_connection = True
    do_GET = do_POST = _response


class LocalServerManager:
    """Only loopback bindings. Public listen is intentionally a separate code exercise."""
    def __init__(self, workdir: Path | None = None):
        self._servers = {}
        self._sockets = set()
        self._events = []
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._closing = False
        if workdir is not None:
            workdir = Path(workdir)
            workdir.mkdir(parents=True, exist_ok=True)
        self._temp = tempfile.TemporaryDirectory(prefix="netlab-servers-", dir=workdir)
        self._certificate = None

    def certificate(self):
        with self._lifecycle_lock:
            if self._certificate is None:
                self._certificate = make_certificate(str(Path(self._temp.name)/"tls"))
            return dict(self._certificate)

    def _track(self, conn, add):
        with self._lock:
            if add:
                self._sockets.add(conn)
            else:
                self._sockets.discard(conn)

    def _record(self, lab_id, operation, size, address):
        with self._lock:
            self._events.append({"id": lab_id, "time": time.time(), "operation": operation, "bytes": size, "peer": list(address), "kind": "measured"})
            self._events = self._events[-1000:]

    def events(self):
        with self._lock:
            return list(self._events)

    def start(self, kind="tcp", host="127.0.0.1", port=0):
        with self._lifecycle_lock:
            return self._start(kind,host,port)

    def _start(self, kind="tcp", host="127.0.0.1", port=0):
        if self._closing:
            raise RuntimeError("服务器管理器已关闭")
        host = validate_host(host)
        if host == "localhost":
            host = "127.0.0.1"
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("内置教学服务器只允许绑定本机回环地址")
        port = int(port)
        if port:
            validate_port(port)
        kind, lab_id = kind.lower(), uuid.uuid4().hex[:12]
        cert = None
        if kind in {"websocket", "http3", "ssh"}:
            from .modern import AsyncLabServer
            if kind in {"http3", "ssh"}:
                cert = self.certificate() if kind == "http3" else None
            server = AsyncLabServer(kind, host, port, certificate=cert, event_callback=lambda operation,size,peer:self._record(lab_id, operation, size, peer))
            actual_port = server.start()
            thread = None
        else:
            server_type = _ThreadedUDP if kind in {"udp","dns","stun"} else http.server.ThreadingHTTPServer if kind in {"http", "https","doh"} else _ThreadedTCP
            handler = {"tcp": _EchoTCP, "udp": _EchoUDP, "chat": _ChatTCP, "file": _FileTCP, "http": _HTTP, "https": _HTTP,"http2":_HTTP2,"dns":_DNSUDP,"dot":_DNSTCP,"doh":_DoH,"stun":_STUN}.get(kind)
            if not handler:
                raise ValueError("支持 tcp/udp/http/https/http2/chat/file/websocket/http3/ssh/dns/dot/doh/stun")
            if ":" in host:
                server_type = type("IPv6Server", (server_type,), {"address_family": socket.AF_INET6})
            if kind in {"https","http2","dot","doh"}:
                server_type = type("TLSLabServer",(_TLSAccept,server_type),{})
            server = server_type((host, port), handler)
            server.manager, server.lab_id = self, lab_id
            server.clients, server.clients_lock = set(), threading.Lock()
            server.directory = str(Path(self._temp.name)/lab_id)
            Path(server.directory).mkdir(exist_ok=True)
            if kind in {"https","http2","dot","doh"}:
                cert = self.certificate()
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                context.load_cert_chain(cert["certificate"], cert["keyfile"])
                if kind != "dot":
                    context.set_alpn_protocols(["h2"] if kind=="http2" else ["http/1.1"])
                server.tls_context = context
            actual_port = server.server_address[1]
            thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True, name=f"netlab-{kind}-{lab_id}")
            thread.start()
        bracket_host = f"[{host}]" if ":" in host else host
        scheme = {"https": "https", "http2":"https", "doh":"https", "dot":"tls", "http3": "https", "websocket": "ws"}.get(kind, kind)
        info = {"ok": True, "id": lab_id, "kind": kind, "host": host, "port": actual_port, "url": f"{scheme}://{bracket_host}:{actual_port}/", "data_kind": "measured",
                "cafile": cert["cafile"] if cert else None, "certificate": cert}
        if kind == "ssh":
            info["trusted_public_key"] = server.public_key
        self._servers[lab_id] = {"server": server, "thread": thread, "info": info}
        return dict(info)

    def list(self):
        with self._lifecycle_lock:
            return [dict(entry["info"]) for entry in self._servers.values()]

    def stop(self, server_id):
        with self._lifecycle_lock:
            return self._stop(server_id)

    def _stop(self, server_id):
        entry = self._servers.pop(server_id, None)
        if not entry:
            return {"ok": False, "error": "服务器不存在"}
        server = entry["server"]
        if entry["thread"]:
            server.shutdown()
            server.server_close()
            entry["thread"].join(2)
        else:
            server.close()
        # Close connections belonging to a stopped server (all are loopback labs).
        with self._lock:
            active = list(self._sockets)
        for conn in active:
            with contextlib.suppress(OSError):
                local_port = conn.getsockname()[1]
                if local_port == entry["info"]["port"]:
                    conn.shutdown(socket.SHUT_RDWR)
                    conn.close()
        return {"ok": True, "id": server_id, "stopped": True}

    def close(self):
        with self._lifecycle_lock:
            self._closing = True
            self.stop_all()
            with self._lock:
                for conn in list(self._sockets):
                    with contextlib.suppress(OSError):
                        conn.shutdown(socket.SHUT_RDWR)
                        conn.close()
                self._sockets.clear()
            self._temp.cleanup()

    def stop_all(self):
        with self._lifecycle_lock:
            for server_id in list(self._servers):
                self.stop(server_id)
            return {"ok":True,"stopped":True,"servers":self.list()}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def echo_client(kind, host, port, message="你好 NetLab", seconds=3):
    target, target_port = validate_host(host), validate_port(port)
    seconds = validate_timeout(seconds)
    if kind not in {"tcp","udp"}:
        raise ValueError("回显协议应为 tcp 或 udp")
    data = message.encode("utf-8")
    if not data or len(data) > 65507:
        raise ValueError("回显消息必须为 1–65507 字节")
    def perform():
        family = socket.AF_INET6 if ":" in target else socket.AF_INET
        if kind == "udp":
            with socket.socket(family, socket.SOCK_DGRAM) as conn:
                conn.settimeout(seconds)
                conn.connect((target, target_port))
                conn.send(data)
                answer = conn.recv(65536)
        else:
            with connect_socket(target,target_port,seconds) as conn:
                conn.sendall(data)
                answer = _read_exact(conn, len(data))
        return {"sent": message, "received": answer.decode("utf-8", "replace"), "matches": answer == data, "bytes": len(answer)}
    return result(kind.upper()+" 回显", f"{target}:{target_port}", perform)


def file_client(host, port, data: bytes, seconds=3):
    target, target_port = validate_host(host), validate_port(port)
    seconds = validate_timeout(seconds)
    if len(data) > MAX_MESSAGE:
        raise ValueError("教学文件限 1 MiB")
    def perform():
        with connect_socket(target,target_port,seconds) as conn:
            _send_frame(conn, data)
            reply = json.loads(_read_frame(conn))
        reply["verified"] = reply["sha256"] == hashlib.sha256(data).hexdigest()
        return reply
    return result("文件传输", f"{target}:{target_port}", perform)


def chat_client(host, port, message="hello", seconds=3):
    target, target_port = validate_host(host), validate_port(port)
    seconds = validate_timeout(seconds)
    if len(message.encode("utf-8"))>65535:
        raise ValueError("聊天室单条消息限 65535 字节")
    def perform():
        with connect_socket(target,target_port,seconds) as conn:
            conn.sendall(message.encode()+b"\n")
            reply = bytearray()
            while not reply.endswith(b"\n") and len(reply)<65536:
                fragment = conn.recv(4096)
                if not fragment:
                    break
                reply.extend(fragment)
        return {"sent": message, "received": reply.decode("utf-8", "replace").rstrip("\n"), "note": "聊天室向所有已连接客户端广播，包括发送者。"}
    return result("聊天", f"{target}:{target_port}", perform)
