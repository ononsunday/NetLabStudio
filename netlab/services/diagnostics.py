"""Bounded single-target diagnostics. No configuration mutation or range scan."""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import ssl
import statistics
import time
from urllib.parse import urlsplit

from .common import command, connect_socket, host, dns_name, port, result, timeout, url


class _Budget:
    def __init__(self,seconds=45,cancel_event=None):
        if not 0.05<=float(seconds)<=45:
            raise ValueError("总时间限制必须为 0.05–45 秒")
        self.expires=time.monotonic()+float(seconds)
        self.cancel_event=cancel_event
    def remaining(self,maximum=30,minimum=0.05):
        if self.cancel_event is not None and self.cancel_event.is_set():
            raise TimeoutError("用户取消了任务，保留已收集的部分证据")
        remaining=self.expires-time.monotonic()
        if remaining<=minimum:
            raise TimeoutError("任务达到总时间限制，保留已收集的部分证据")
        return min(float(maximum),remaining)


def _certificate_fields(der):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import ExtensionOID
    certificate=x509.load_der_x509_certificate(der)
    dns_names,ip_addresses=[],[]
    try:
        names=certificate.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
        dns_names=names.get_values_for_type(x509.DNSName)
        ip_addresses=[str(ip) for ip in names.get_values_for_type(x509.IPAddress)]
    except x509.ExtensionNotFound:
        pass
    try:
        ca=certificate.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value.ca
    except x509.ExtensionNotFound:
        ca=None
    return {"subject":certificate.subject.rfc4514_string(),"issuer":certificate.issuer.rfc4514_string(),
            "serial_number":str(certificate.serial_number),"dns_names":dns_names,"ip_addresses":ip_addresses,
            "not_before_utc":certificate.not_valid_before_utc.isoformat(),"not_after_utc":certificate.not_valid_after_utc.isoformat(),
            "sha256_fingerprint":certificate.fingerprint(hashes.SHA256()).hex(),"is_ca":ca}


def tcp_probe(target, target_port=443, seconds=5):
    target, target_port, seconds = host(target), port(target_port), timeout(seconds)
    def perform():
        with connect_socket(target,target_port,seconds) as conn:
            return {"peer": list(conn.getpeername()), "local": list(conn.getsockname()), "connected": True}
    return result("TCP", f"{target}:{target_port}", perform)


def ping(target, count=4, seconds=2,overall_budget=45,cancel_event=None):
    target, seconds = host(target), timeout(seconds)
    count = int(count)
    if not 1 <= count <= 50:
        raise ValueError("探测次数必须为 1–50")
    args = ["ping", "-n", str(count), "-w", str(int(seconds*1000)), target] if os.name == "nt" else ["ping", "-c", str(count), "-W", str(max(1, int(seconds))), target]
    budget=_Budget(overall_budget,cancel_event)
    completed = command(args,min(budget.remaining(45,0),count*(seconds+1)+2),cancel_event)
    matches=re.findall(r"(?:time|时间)\s*([=<])\s*([\d.,]+)\s*(?:ms|毫秒)",completed["stdout"],re.I)
    samples=[float(value.replace(",",".")) for relation,value in matches]
    # A localized command's raw result remains authoritative if fields cannot be extracted.
    partial=bool(completed.get("partial"))
    details = {"stdout": completed["stdout"], "stderr": completed["stderr"], "sent": None if partial else count,"requested_count":count,
               "parsed_replies": len(samples), "rtt_ms": samples,"complete":not partial,
               "rtt_observations":[{"value_ms":float(value.replace(",",".")),"relation":relation} for relation,value in matches],
               "precision_note":"取自系统命令文本；小于 1 ms 的回复按 1 ms 上界绘图，不能解释为精确 1 ms。",
               "loss_percent": (count-len(samples))*100/count if samples and not partial else None,
               "mean_ms": statistics.mean(samples) if samples else None,
               "jitter_ms": statistics.mean(abs(b-a) for a,b in zip(samples,samples[1:])) if len(samples)>1 else None}
    return {"ok": completed["ok"], "kind": "measured", "operation": "Ping", "target": target, "details": details,
            "complete":not partial,"elapsed_ms": completed["elapsed_ms"], "error": None if completed["ok"] else completed.get("error") or completed["stderr"] or "目标无响应；不能据此单独判断网页不可用"}


def traceroute(target, max_hops=16, seconds=1,overall_budget=45,cancel_event=None):
    target, seconds, max_hops = host(target), timeout(seconds), int(max_hops)
    if not 1 <= max_hops <= 32:
        raise ValueError("最大跳数必须为 1–32")
    args = ["tracert", "-d", "-h", str(max_hops), "-w", str(int(seconds*1000)), target] if os.name == "nt" else ["traceroute", "-n", "-m", str(max_hops), "-w", str(seconds), target]
    budget=_Budget(overall_budget,cancel_event)
    completed = command(args,min(budget.remaining(45,0),max_hops*seconds*3+5),cancel_event)
    return {"ok": completed["ok"], "kind": "measured", "operation": "Traceroute", "target": target, "details": completed,
            "complete":not completed.get("partial",False),"error": None if completed["ok"] else completed.get("error") or completed["stderr"] or "探测失败或未在跳数上限内到达目标", "elapsed_ms": completed["elapsed_ms"]}


def dns_probe(target, record_type="A", seconds=5, resolver=None, resolver_port=53):
    target, seconds = dns_name(target), timeout(seconds)
    record_type = str(record_type).upper()
    if record_type not in {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SOA", "CAA", "SRV", "PTR", "DNSKEY", "DS"}:
        raise ValueError("不支持的 DNS 记录类型")
    def perform():
        import dns.resolver
        client = dns.resolver.Resolver()
        if resolver:
            client.nameservers = [str(ipaddress.ip_address(resolver))]
            client.port = port(resolver_port)
        answer = client.resolve(target, record_type, lifetime=seconds)
        return {"records": [item.to_text() for item in answer], "ttl": answer.rrset.ttl, "canonical_name": str(answer.canonical_name),
                "resolver": client.nameservers, "record_type": record_type,
                "note": "这是通过递归解析器完成的实测查询，不代表程序观察了根服务器的迭代过程。"}
    return result("DNS", target, perform)


def encrypted_dns(target, mode="doh", server="https://cloudflare-dns.com/dns-query", record_type="A", seconds=5, cafile=None):
    target, seconds = dns_name(target), timeout(seconds)
    def perform():
        import dns.message
        import dns.query
        request = dns.message.make_query(target, record_type)
        if mode == "doh":
            url(server, ("https",))
            import httpx
            context = ssl.create_default_context(cafile=cafile)
            with httpx.Client(verify=context,timeout=seconds,trust_env=False) as session:
                response = dns.query.https(request, server, timeout=seconds, session=session)
        elif mode == "dot":
            parsed_server = url(server, ("tls",)) if "://" in server else None
            hostname = host(parsed_server.hostname if parsed_server else server)
            server_port = parsed_server.port or 853 if parsed_server else 853
            address = socket.getaddrinfo(hostname, server_port, type=socket.SOCK_STREAM)[0][4][0]
            response = dns.query.tls(request, address, port=server_port, timeout=seconds, server_hostname=hostname, ssl_context=ssl.create_default_context(cafile=cafile))
        else:
            raise ValueError("加密 DNS 模式应为 doh 或 dot")
        return {"rcode": response.rcode(), "answers": [entry.to_text() for entry in response.answer], "transport": mode, "certificate_verified": True}
    return result(mode.upper(), target, perform)


def tls_probe(target, target_port=443, seconds=5, cafile=None):
    target, target_port, seconds = host(target), port(target_port), timeout(seconds)
    def perform():
        context = ssl.create_default_context(cafile=cafile)
        deadline=time.monotonic()+seconds
        with connect_socket(target,target_port,seconds) as raw:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError("TLS 连接达到总时间限制")
            raw.settimeout(remaining)
            with context.wrap_socket(raw, server_hostname=target) as secure:
                cert = secure.getpeercert()
                get_chain=getattr(secure,"get_verified_chain",None)
                chain=[_certificate_fields(der) for der in get_chain()] if get_chain else []
                return {"tls_version": secure.version(), "cipher": secure.cipher(), "certificate": cert,
                        "leaf_certificate_details":_certificate_fields(secure.getpeercert(binary_form=True)),"verified_chain":chain,
                        "verified_chain_available":bool(get_chain),"verified_chain_note":None if get_chain else "当前 Python/SSL API 不提供完整已验证链；握手仍执行了正常证书路径验证。",
                        "trust_context":{"source":"explicit_CA_pem" if cafile else "system_and_OpenSSL_defaults","verify_mode":"CERT_REQUIRED","check_hostname":context.check_hostname,"certificate_store":context.cert_store_stats()},
                        "certificate_verified": True, "hostname_verified": True,
                        "peer": list(secure.getpeername()), "note": "证书路径与主机名由系统信任库/指定 CA 和 OpenSSL 验证；没有解密其他连接。"}
    return result("TLS", f"{target}:{target_port}", perform)


def http_probe(target, method="GET", seconds=5, body="", headers=None, cafile=None):
    url(target)
    seconds = timeout(seconds)
    method = method.upper()
    if method not in {"GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"}:
        raise ValueError("不支持的 HTTP 方法")
    if len(body.encode("utf-8")) > 1024*1024:
        raise ValueError("请求体限 1 MiB")
    def perform():
        import httpx
        from .http_deadline import DeadlineTransport
        verify=ssl.create_default_context(cafile=cafile)
        transport=DeadlineTransport(verify,seconds)
        with httpx.Client(transport=transport,http2=True,timeout=seconds,follow_redirects=False,trust_env=False) as client:
            # Stream and bound bodies to protect the desktop against giant responses.
            with client.stream(method, target, content=body.encode(), headers=headers or {}) as response:
                data = bytearray()
                truncated = False
                for chunk in response.iter_bytes():
                    data.extend(chunk[:max(0, 1024*1024-len(data))])
                    if len(data) >= 1024*1024:
                        truncated = True
                        break
                return {"status": response.status_code, "http_version": response.http_version, "headers": dict(response.headers),
                        "body_preview": bytes(data[:65536]).decode(response.encoding or "utf-8", "replace"), "body_bytes_read": len(data),
                        "truncated": truncated, "redirect_followed": False, "url": str(response.url)}
    return result("HTTP", target, perform)


def website_probe(target, seconds=5,overall_budget=45,cancel_event=None):
    parsed, seconds = url(target), timeout(seconds)
    target_port = parsed.port or (443 if parsed.scheme == "https" else 80)
    stages = []
    budget,error=_Budget(overall_budget,cancel_event),None
    try:
        for record in ("A", "AAAA"):
            try:
                ipaddress.ip_address(parsed.hostname)
                break
            except ValueError:
                stages.append(dns_probe(parsed.hostname, record,budget.remaining(seconds)))
        stages.append(tcp_probe(parsed.hostname,target_port,budget.remaining(seconds)))
        if parsed.scheme=="https":
            stages.append(tls_probe(parsed.hostname,target_port,budget.remaining(seconds)))
        stages.append(http_probe(target,seconds=budget.remaining(seconds)))
    except TimeoutError as exc:
        error=str(exc)
    return {"kind": "measured", "operation": "访问网站", "target": target, "ok": bool(stages) and stages[-1]["ok"] and error is None,
            "complete":error is None,"error":error,"stages":stages,
            "note": "各阶段为独立连接的实测探测，不是浏览器同一会话的抓包；HTTP/3 请使用专用探测。"}


def latency_probe(target, target_port=443, count=10, seconds=1,overall_budget=45,cancel_event=None):
    target, target_port, seconds, count = host(target), port(target_port), timeout(seconds), int(count)
    if not 1 <= count <= 50:
        raise ValueError("采样次数应为 1–50")
    budget,probes,error=_Budget(overall_budget,cancel_event),[],None
    try:
        for _ in range(count):
            probes.append(tcp_probe(target,target_port,budget.remaining(seconds)))
    except TimeoutError as exc:
        error=str(exc)
    samples = [p["elapsed_ms"] for p in probes if p["ok"]]
    return {"kind": "measured", "operation": "TCP 连接稳定性", "target": target,"ok":bool(samples) and error is None,"complete":error is None,"error":error,
            "samples":probes,"requested_count":count,"completed_count":len(probes),"mean_ms":statistics.mean(samples) if samples else None,
            "failure_percent":100*(len(probes)-len(samples))/len(probes) if probes else None,
            "jitter_ms": statistics.mean(abs(b-a) for a,b in zip(samples,samples[1:])) if len(samples)>1 else None,
            "note": "连接建立耗时包含系统调度；失败率不是 UDP 丢包率，也不是第三方游戏服务器 Ping。"}


def diagnose(target, seconds=3,overall_budget=45,cancel_event=None):
    from .observe import system_snapshot
    parsed = url(target if "://" in target else "https://"+target)
    budget,error=_Budget(overall_budget,cancel_event),None
    snapshot = system_snapshot(seconds=budget.remaining(30,0))
    checks = [{"operation": "适配器与地址", "ok": any(a["status"] == "up" and (a["ipv4"] or a["ipv6"]) for a in snapshot["adapters"]),
               "kind": "measured", "details": snapshot["adapters"]}]
    default_routes=sorted((row for row in snapshot.get("routes",{}).get("rows",[]) if row.get("DestinationPrefix")=="0.0.0.0/0" and row.get("NextHop") not in {None,"0.0.0.0"}),
                          key=lambda row:float(row.get("RouteMetric") or 0)+float(row.get("InterfaceMetric") or 0))
    gateways = [default_routes[0]["NextHop"]] if default_routes else [a["gateway"].split(",")[0] for a in snapshot["adapters"] if a.get("gateway") and a["status"] == "up"]
    try:
        if gateways:
            checks.append(ping(gateways[0],1,budget.remaining(seconds),budget.remaining(45),cancel_event))
        try:
            ipaddress.ip_address(parsed.hostname)
        except ValueError:
            checks.append(dns_probe(parsed.hostname,"A",budget.remaining(seconds)))
        checks.append(tcp_probe(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),budget.remaining(seconds)))
        if parsed.scheme=="https":
            checks.append(tls_probe(parsed.hostname,parsed.port or 443,budget.remaining(seconds)))
        checks.append(http_probe(target if "://" in target else "https://"+target,seconds=budget.remaining(seconds)))
    except TimeoutError as exc:
        error=str(exc)
    suggestions = []
    for item in checks:
        if not item["ok"]:
            name = item["operation"]
            suggestions.append({"check": name, "evidence": item.get("error") or item.get("details"),
                                "suggestion": {"DNS": "检查域名拼写、当前 DNS 配置和 DNS 服务可用性。", "TCP": "确认目标端口有监听服务，并检查路径或防火墙规则。", "TLS": "检查系统时间、主机名和证书信任链。", "Ping": "网关可能过滤 ICMP；结合 TCP/HTTPS 结果判断。"}.get(name, "检查对应配置和错误证据；工具不会自动修改系统设置。")})
    return {"kind":"measured","target":target,"checks":checks,"suggestions":suggestions,"ok":checks[-1]["ok"] and error is None,"complete":error is None,"error":error}


def run_probe(kind, target, port=443, timeout=5, count=4, record_type="A", method="GET", **kwargs):
    """UI dispatch. Validation failures are returned rather than crashing a worker."""
    try:
        key = kind.lower()
        budget,cancel=kwargs.get("overall_budget",45),kwargs.get("cancel_event")
        if key in {"ping", "icmp"}: return ping(target,count,timeout,budget,cancel)
        if key in {"traceroute", "tracert"}: return traceroute(target,seconds=timeout,overall_budget=budget,cancel_event=cancel)
        if key == "tcp": return tcp_probe(target, port, timeout)
        if key == "dns": return dns_probe(target, record_type, timeout, kwargs.get("resolver"),kwargs.get("resolver_port",53))
        if key in {"tls", "https"}: return tls_probe(target, port, timeout, kwargs.get("cafile"))
        if key in {"http", "http2"}: return http_probe(target, method, timeout, kwargs.get("body", ""), kwargs.get("headers"), kwargs.get("cafile"))
        if key in {"website", "web"}: return website_probe(target,timeout,budget,cancel)
        if key in {"doh", "dot"}: return encrypted_dns(target, key, kwargs.get("server", "https://cloudflare-dns.com/dns-query" if key=="doh" else "cloudflare-dns.com"), record_type, timeout, kwargs.get("cafile"))
        if key == "stun":
            from .p2p import stun_probe
            return stun_probe(target,port,timeout)
        if key == "latency": return latency_probe(target,port,count,timeout,budget,cancel)
        if key in {"diagnose", "wizard"}: return diagnose(target,timeout,budget,cancel)
        if key in {"http3", "quic"}:
            from .modern import http3_probe
            return http3_probe(target, timeout, kwargs.get("cafile"))
        if key == "ssh":
            from .modern import ssh_probe
            return ssh_probe(target, port, timeout)
        if key == "websocket":
            from .modern import websocket_probe
            return websocket_probe(target, kwargs.get("message", "你好 WebSocket"), timeout)
        raise ValueError("未知诊断类型")
    except Exception as exc:
        return {"ok": False, "kind": "measured", "operation": str(kind), "target": str(target), "details": {}, "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": 0}
