"""Input validation and JSON-compatible results for worker-thread services."""
from __future__ import annotations

import ipaddress
import re
import socket
import subprocess
import time
from urllib.parse import urlsplit


def host(value: str) -> str:
    value = str(value).strip()
    if not value or len(value) > 253 or any(c.isspace() for c in value):
        raise ValueError("请输入一个有效的 IP 地址或主机名")
    try:
        ipaddress.ip_address(value.split("%", 1)[0])
        return value
    except ValueError:
        ascii_name = value.rstrip(".").encode("idna").decode("ascii")
        if not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in ascii_name.split(".")):
            raise ValueError("主机名不能包含命令、路径或特殊符号")
        return ascii_name


def port(value: int) -> int:
    number = int(value)
    if not 1 <= number <= 65535:
        raise ValueError("端口必须为 1–65535")
    return number


def dns_name(value: str) -> str:
    name = str(value).strip().rstrip(".").encode("idna").decode("ascii")
    if not name or len(name)>253 or not all(re.fullmatch(r"[A-Za-z0-9_](?:[A-Za-z0-9_-]{0,61}[A-Za-z0-9_])?",part) for part in name.split(".")):
        raise ValueError("请输入有效的 DNS 名称；SRV 记录允许下划线标签")
    return name


def timeout(value: float) -> float:
    number = float(value)
    if not 0.05 <= number <= 30:
        raise ValueError("超时必须为 0.05–30 秒")
    return number


def url(value: str, schemes=("http", "https")):
    parsed = urlsplit(str(value).strip())
    if parsed.scheme not in schemes or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("请输入无内嵌密码的 http:// 或 https:// URL")
    host(parsed.hostname)
    if parsed.port:
        port(parsed.port)
    return parsed


def connect_socket(target: str,target_port: int,seconds: float):
    """Bound DNS and connection attempts under one deadline (no LLMNR lookup)."""
    target,target_port,seconds=host(target),port(target_port),timeout(seconds)
    deadline=time.monotonic()+seconds
    try:
        ipaddress.ip_address(target.split("%",1)[0])
        addresses=[target]
    except ValueError:
        if target.lower()=="localhost":
            addresses=["127.0.0.1","::1"]
        else:
            import dns.resolver
            resolved=dns.resolver.Resolver().resolve_name(target,lifetime=seconds)
            addresses=list(resolved.addresses())
    error=None
    for address in addresses:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            raise TimeoutError("DNS 或连接达到总时间限制")
        try:
            return socket.create_connection((address,target_port),remaining)
        except OSError as exc:
            error=exc
    if error:
        raise error
    raise OSError("DNS 未返回可连接的地址")


def command(args: list[str], limit: float = 10, cancel_event=None) -> dict:
    """No shell, bounded execution, hide the Windows console window."""
    import os
    start = time.perf_counter()
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=0x08000000 if os.name == "nt" else 0)
        cancelled = False
        reason = None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                reason, cancelled = "用户取消了任务",True
                proc.kill()
                out,err = proc.communicate()
                break
            remaining = limit-(time.perf_counter()-start)
            if remaining <= 0:
                reason = "操作达到总时间限制，保留已收集的部分证据"
                proc.kill()
                out,err = proc.communicate()
                break
            try:
                out,err = proc.communicate(timeout=min(0.1,remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        import locale
        encoding = locale.getpreferredencoding(False)
        def decode(data):
            try:
                return data.decode("utf-8-sig")
            except UnicodeDecodeError:
                return data.decode(encoding,"replace")
        return {"ok": proc.returncode == 0 and reason is None, "returncode": proc.returncode,
                "stdout": decode(out), "stderr": decode(err),"error":reason,"cancelled":cancelled,"partial":reason is not None,
                "elapsed_ms": round((time.perf_counter()-start)*1000, 3)}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc),
                "elapsed_ms": round((time.perf_counter()-start)*1000, 3)}


def result(operation: str, target: str, function) -> dict:
    start = time.perf_counter()
    try:
        details = function()
        return {"ok": True, "kind": "measured", "operation": operation, "target": target,
                "details": details, "error": None, "elapsed_ms": round((time.perf_counter()-start)*1000, 3)}
    except Exception as exc:
        return {"ok": False, "kind": "measured", "operation": operation, "target": target,
                "details": {}, "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": round((time.perf_counter()-start)*1000, 3)}
